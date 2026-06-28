"""Tests for the B3b ``HealthTickJob`` and ``ClayScheduler._run_safely``.

Covers the B3b acceptance criteria spelled out in the task-packet:

1. ``test_tick_heartbeats_only_scheduler`` — heartbeat scope is
   **only** ``session-scheduler`` (Emma fix, recorded in
   ``handoffs/current.md`` §41-50 of Wave B). Other services keep
   ``last_heartbeat_at == None``.
2. ``test_refresh_marks_stale_service`` — a service with a stale
   ``last_heartbeat_at`` is marked ``STALE`` by the same tick;
   ``FakeDatetime`` is monkey-patched into **both**
   ``clay.services.models`` (the ``heartbeat()`` set-site) and
   ``clay.health.monitor`` (the ``refresh()`` read-site). No
   freezegun per spec.
3. ``test_audit_only_on_transition`` — steady-state ticks write
   **zero** audit records; a tick that flips a status writes
   **exactly one** per changed service.
4. ``test_recovery_error_to_healthy`` — successful tick after a
   previous ``ERROR`` recovers the ``session-scheduler`` to
   ``HEALTHY`` and audits the ``ERROR → HEALTHY`` transition.
5. ``test_exception_marks_scheduler_error_no_audit_on_repeat`` —
   an exception in the tick (forced via ``monkeypatch`` on
   ``HealthMonitor.refresh``) is caught by ``_run_safely``,
   ``session-scheduler`` goes ``HEALTHY → ERROR``, an audit
   ``service.status_changed`` is written on the **first** failure.
   A **second** consecutive failed tick does **not** add another
   audit entry (anti-flood rule).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

import pytest

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.health.monitor import HealthMonitor
from clay.scheduler.jobs import HealthTickJob
from clay.scheduler.service import ClayScheduler
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.settings.scheduler import SchedulerSettings


def _read_audit_events(audit_writer: AuditWriter) -> list[dict[str, Any]]:
    """Read the JSONL audit log and return parsed events (test helper)."""
    with audit_writer.path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _drain_event_bus(event_bus: EventBus) -> list[tuple[str, dict[str, Any]]]:
    """Drain every currently-subscribed queue and return published events."""
    drained: list[tuple[str, dict[str, Any]]] = []
    for queue in list(event_bus._subscribers):  # noqa: SLF001 (test helper)
        while True:
            try:
                message = queue.get_nowait()
            except Exception:  # asyncio.QueueEmpty
                break
            drained.append((message.event_type, message.payload))
    return drained


class FakeDatetime:
    """Minimal ``datetime`` stub for monkey-patching.

    Replaces ``clay.services.models.datetime`` and
    ``clay.health.monitor.datetime`` so the tick can be driven
    against a controlled "now" without freezegun (per spec).

    The test sets ``FakeDatetime.current`` to a tz-aware
    ``datetime``; ``now(tz)`` returns it astimezone-converted to
    the requested tz (matching real ``datetime.now(UTC)`` semantics).
    """

    current: datetime | None = None

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        assert cls.current is not None, "FakeDatetime.current must be set"
        if tz is None:
            return cls.current
        return cls.current.astimezone(tz)


@pytest.fixture
def fake_clock() -> Iterator[datetime]:
    """Return a fixed "now" and reset ``FakeDatetime.current`` after the test."""
    now = datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC)
    FakeDatetime.current = now
    yield now
    FakeDatetime.current = None


def _make_registry(
    *service_ids: str,
    criticality: ServiceCriticality = ServiceCriticality.IMPORTANT,
) -> ServiceRegistry:
    """Build a registry with the given ``service_ids`` (all default-criticality)."""
    registry = ServiceRegistry()
    for service_id in service_ids:
        registry.register(
            service_id=service_id,
            service_type="worker" if service_id != "session-scheduler" else "scheduler",
            criticality=criticality,
            startup_policy="always-on"
            if service_id == "session-scheduler"
            else "on-demand",
        )
    return registry


def _make_tick(
    tmp_path: Path,
    registry: ServiceRegistry,
    *,
    stale_after_seconds: int = 60,
) -> tuple[HealthTickJob, AuditWriter, EventBus, HealthMonitor]:
    """Build a ``HealthTickJob`` with a fresh ``AuditWriter`` / ``EventBus``."""
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    health_monitor = HealthMonitor(
        registry=registry,
        stale_after_seconds=stale_after_seconds,
    )
    tick = HealthTickJob(
        registry=registry,
        health_monitor=health_monitor,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    return tick, audit_writer, event_bus, health_monitor


def test_tick_heartbeats_only_scheduler(tmp_path: Path) -> None:
    """Heartbeat scope is **only** ``session-scheduler`` (Emma fix).

    Other services keep ``last_heartbeat_at == None`` and never
    appear in a ``service.status_changed`` event. The initial
    tick re-asserts ``session-scheduler`` to ``HEALTHY`` (the
    steady-state re-assertion + recovery path); the only audit
    transition on the bus is that one for ``session-scheduler``.
    """
    registry = _make_registry(
        "session-scheduler",
        "fake-A",
        "fake-B",
    )
    assert registry.get("session-scheduler").last_heartbeat_at is None
    assert registry.get("fake-A").last_heartbeat_at is None
    assert registry.get("fake-B").last_heartbeat_at is None

    tick, audit_writer, event_bus, _ = _make_tick(tmp_path, registry)
    event_bus.subscribe()  # one subscriber so publish() can fan out

    tick.run()

    # session-scheduler heartbeat stamped + status re-asserted HEALTHY.
    scheduler_rec = registry.get("session-scheduler")
    assert scheduler_rec.last_heartbeat_at is not None
    assert scheduler_rec.status is ServiceStatus.HEALTHY
    # Other services were NOT touched (heartbeat-scope fix).
    assert registry.get("fake-A").last_heartbeat_at is None
    assert registry.get("fake-B").last_heartbeat_at is None

    # event_bus: 1 health.tick + exactly 1 service.status_changed
    # (session-scheduler STOPPED→HEALTHY); the other two services
    # do NOT generate any transitions.
    drained = _drain_event_bus(event_bus)
    assert [t for t, _ in drained].count("health.tick") == 1
    status_changed = [
        payload for evt_type, payload in drained if evt_type == "service.status_changed"
    ]
    assert len(status_changed) == 1
    assert status_changed[0]["service_id"] == "session-scheduler"
    assert status_changed[0]["from"] == "stopped"
    assert status_changed[0]["to"] == "healthy"

    # audit log mirrors the same single transition.
    events = _read_audit_events(audit_writer)
    assert len(events) == 1
    assert events[0]["event_type"] == "service.status_changed"
    assert events[0]["payload"]["service_id"] == "session-scheduler"


def test_refresh_marks_stale_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_clock: datetime,
) -> None:
    """Stale service → ``STALE`` on the same tick (FakeDatetime driven).

    ``FakeDatetime`` is monkey-patched into both
    ``clay.services.models`` (the ``heartbeat()`` set-site) and
    ``clay.health.monitor`` (the ``refresh()`` read-site) so the
    test does not depend on wall-clock time. No freezegun per spec.
    """
    monkeypatch.setattr("clay.services.models.datetime", FakeDatetime)
    monkeypatch.setattr("clay.health.monitor.datetime", FakeDatetime)

    registry = _make_registry("session-scheduler", "stale-worker")
    # session-scheduler's last_heartbeat_at stays None initially;
    # `refresh()` will skip it (None-guard).
    # stale-worker had a heartbeat 2 hours ago — well past the 60s
    # stale threshold. The None-guard does NOT save it.
    registry.get("stale-worker").last_heartbeat_at = fake_clock - timedelta(hours=2)

    tick, audit_writer, event_bus, _ = _make_tick(
        tmp_path,
        registry,
        stale_after_seconds=60,
    )
    event_bus.subscribe()

    tick.run()

    # session-scheduler is HEALTHY (re-asserted in step 3 of run()).
    assert registry.get("session-scheduler").status is ServiceStatus.HEALTHY
    # stale-worker was marked STALE.
    assert registry.get("stale-worker").status is ServiceStatus.STALE

    # Audit: 2 transitions (session-scheduler STOPPED→HEALTHY,
    # stale-worker STOPPED→STALE). Both are service.status_changed.
    events = _read_audit_events(audit_writer)
    changed = [e for e in events if e["event_type"] == "service.status_changed"]
    assert len(changed) == 2

    by_id = {e["payload"]["service_id"]: e["payload"] for e in changed}
    assert by_id["session-scheduler"] == {
        "service_id": "session-scheduler",
        "from": "stopped",
        "to": "healthy",
    }
    assert by_id["stale-worker"] == {
        "service_id": "stale-worker",
        "from": "stopped",
        "to": "stale",
    }

    # event_bus: 1 health.tick + 2 service.status_changed = 3 publishes.
    drained = _drain_event_bus(event_bus)
    assert len(drained) == 3
    assert [t for t, _ in drained].count("health.tick") == 1
    assert [t for t, _ in drained].count("service.status_changed") == 2


def test_audit_only_on_transition(tmp_path: Path) -> None:
    """Steady-state tick → 0 audit. Status change → exactly 1 audit.

    First tick flips ``session-scheduler`` STOPPED → HEALTHY (1
    audit). Second tick is steady-state (0 audit). Third tick is
    still steady-state (0 audit). Total: exactly 1 audit.
    """
    registry = _make_registry("session-scheduler")
    tick, audit_writer, _, _ = _make_tick(tmp_path, registry)

    tick.run()
    assert registry.get("session-scheduler").status is ServiceStatus.HEALTHY
    assert len(_read_audit_events(audit_writer)) == 1

    tick.run()
    tick.run()
    # Steady state — no further audit entries.
    assert len(_read_audit_events(audit_writer)) == 1


def test_recovery_error_to_healthy(tmp_path: Path) -> None:
    """Successful tick after ``ERROR`` recovers ``session-scheduler``.

    Step 3 of ``HealthTickJob.run()`` re-asserts ``HEALTHY`` after
    the heartbeat, so the ``before`` snapshot sees ``ERROR`` and
    the ``after`` snapshot sees ``HEALTHY``; the diff writes the
    ``service.status_changed`` audit. ``last_error`` is overwritten
    to ``None`` by the no-arg ``update_status(HEALTHY)`` call (per
    the ``ServiceRegistry.update_status`` contract: ``error``
    defaults to ``None`` on every call).
    """
    registry = _make_registry("session-scheduler")
    registry.update_status(
        "session-scheduler",
        ServiceStatus.ERROR,
        error="previous boom",
    )
    assert registry.get("session-scheduler").status is ServiceStatus.ERROR
    assert registry.get("session-scheduler").last_error == "previous boom"

    tick, audit_writer, _, _ = _make_tick(tmp_path, registry)

    tick.run()

    rec = registry.get("session-scheduler")
    assert rec.status is ServiceStatus.HEALTHY
    # recovery: last_error reset to None by update_status(HEALTHY)
    # (ServiceRegistry.update_status default).
    assert rec.last_error is None

    # Audit: exactly 1 service.status_changed (ERROR → HEALTHY).
    events = _read_audit_events(audit_writer)
    changed = [e for e in events if e["event_type"] == "service.status_changed"]
    assert len(changed) == 1
    assert changed[0]["payload"] == {
        "service_id": "session-scheduler",
        "from": "error",
        "to": "healthy",
    }


def test_exception_marks_scheduler_error_no_audit_on_repeat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exception in tick → ``ERROR`` + 1 audit; second failure → 0 new audit.

    ``HealthMonitor.refresh`` is forced to raise; ``_run_safely``
    catches the exception, transitions ``session-scheduler``
    ``HEALTHY → ERROR``, and writes **one** audit record (the
    transition into ``ERROR``). A second consecutive failed tick
    keeps the status in ``ERROR`` and writes **no** new audit
    record — anti-flood rule. The exception is **not** re-raised
    (the test only passes if control returns to the test body).
    """
    registry = _make_registry("session-scheduler")
    registry.update_status("session-scheduler", ServiceStatus.HEALTHY)
    tick, audit_writer, _, health_monitor = _make_tick(tmp_path, registry)

    boom = RuntimeError("boom")

    def _raise_boom() -> None:
        raise boom

    monkeypatch.setattr(health_monitor, "refresh", _raise_boom)

    scheduler = ClayScheduler(
        settings=SchedulerSettings(enabled=True),
        registry=registry,
        health_monitor=health_monitor,
        audit_writer=audit_writer,
        event_bus=EventBus(),
    )

    # First failure.
    scheduler._run_safely(tick.run)  # noqa: SLF001 (intentional — wrapper unit test)
    rec = registry.get("session-scheduler")
    assert rec.status is ServiceStatus.ERROR
    assert rec.last_error == "boom"

    error_audits = [
        e
        for e in _read_audit_events(audit_writer)
        if e["event_type"] == "service.status_changed"
        and e["payload"].get("to") == "error"
    ]
    assert len(error_audits) == 1
    assert error_audits[0]["payload"] == {
        "service_id": "session-scheduler",
        "from": "healthy",
        "to": "error",
        "error": "boom",
    }

    # Second consecutive failure: status already ERROR → 0 new audit.
    scheduler._run_safely(tick.run)  # noqa: SLF001
    rec = registry.get("session-scheduler")
    assert rec.status is ServiceStatus.ERROR
    assert rec.last_error == "boom"  # last_error refreshed (still "boom")

    error_audits_after = [
        e
        for e in _read_audit_events(audit_writer)
        if e["event_type"] == "service.status_changed"
        and e["payload"].get("to") == "error"
    ]
    # Anti-flood: still exactly 1 audit entry across 2 failures.
    assert len(error_audits_after) == 1
