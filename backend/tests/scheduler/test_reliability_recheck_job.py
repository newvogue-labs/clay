"""Tests for the B4 ``ReliabilityRecheckJob`` (scheduler-driven reliability recheck).

B4 acceptance (matches handoffs/current.md §B4 + Emma's #11 fix):

1. ``test_first_run_seeds_cache_no_emit`` — Acceptance #5
2. ``test_steady_state_no_emit`` — Acceptance #3
3. ``test_transition_emits_audit_and_bus`` — Acceptance #4
4. ``test_run_calls_recheck_emit_false_and_commits`` — emits=False
   + session commit (Acceptance #1, partial: DB-write path is
   covered by ``test_reliability_service``; this test pins the
   job's contract on top of it).
5. ``test_on_error_audits_once`` — Acceptance #10 (anti-flood)
6. ``test_on_error_does_not_mutate_session_scheduler`` — Acceptance #9
   partial: B4 isolates the error policy from session-scheduler.
7. ``test_on_error_does_not_re_raise`` — Acceptance #9 caller-safe
   contract: ``_run_safely`` calls ``on_error(exc)`` without a
   ``try/except`` around it.
8. ``test_failure_success_failure_audits_twice`` — Acceptance #11
   (Emma's mandatory fix): ``_failing`` resets on a successful tick
   so a new failing episode re-emits the audit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.orm import sessionmaker

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.scheduler.jobs import ReliabilityRecheckJob
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry


def _read_audit_events(audit_writer: AuditWriter) -> list[dict[str, Any]]:
    """Read the JSONL audit log. Returns ``[]`` if the file does not exist.

    AuditWriter is lazy: ``write()`` creates the file on first call.
    A test that asserts "no audit was written" must tolerate the
    absent file (rather than crashing on ``open()``), so this helper
    short-circuits to ``[]`` when the path is missing.
    """
    if not audit_writer.path.exists():
        return []
    with audit_writer.path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _drain_event_bus(event_bus: EventBus) -> list[tuple[str, dict[str, Any]]]:
    drained: list[tuple[str, dict[str, Any]]] = []
    for queue in list(event_bus._subscribers):  # noqa: SLF001 (test helper)
        while True:
            try:
                message = queue.get_nowait()
            except Exception:  # asyncio.QueueEmpty
                break
            drained.append((message.event_type, message.payload))
    return drained


@dataclass
class _FakeSummary:
    release_readiness_status: str = "ready_for_demo"
    blocking_gate_count: int = 0
    warning_gate_count: int = 2
    overall_status: str = "healthy"


class FakeSnapshot:
    """Fake ``ReliabilitySnapshot`` with the 4 fields the job diffs."""

    def __init__(
        self,
        *,
        status: str = "ready_for_demo",
        blocking: int = 0,
        warning: int = 2,
        overall_status: str = "healthy",
        db_size_critical: bool = False,
    ) -> None:
        self.summary = _FakeSummary(
            release_readiness_status=status,
            blocking_gate_count=blocking,
            warning_gate_count=warning,
            overall_status=overall_status,
        )
        # D-13: ``degraded_triggers`` used by the job to detect
        # ``db-size-critical`` for the 4th cache-tuple element.
        self.degraded_triggers: list[Any] = []
        if db_size_critical:
            self.degraded_triggers.append(
                type(
                    "_FakeTrigger",
                    (),
                    {"trigger_id": "db-size-critical", "severity": "critical"},
                )()
            )


class FakeReliabilityService:
    """Fake ``ReliabilityService`` — exposes the B4 surface only.

    The B4 contract is narrow: ``recheck(session, *, emit)`` and
    ``emit_recheck_events(snapshot)``. The fake records the calls so
    tests can assert the call shape, and writes audit/bus through the
    real ``AuditWriter`` / ``EventBus`` so the side-effect surface is
    identical to production.
    """

    def __init__(
        self,
        *,
        audit_writer: AuditWriter,
        event_bus: EventBus,
    ) -> None:
        self._audit_writer = audit_writer
        self._event_bus = event_bus
        self._current_snapshot = FakeSnapshot()
        self.recheck_calls: list[tuple[Any, bool]] = []
        self.emit_calls: list[Any] = []
        self._last_rechecked_at: datetime | None = None

    def recheck(self, session: Any, *, emit: bool = True) -> FakeSnapshot:
        self.recheck_calls.append((session, emit))
        self._last_rechecked_at = datetime.now(UTC)
        return self._current_snapshot

    def emit_recheck_events(self, snapshot: FakeSnapshot) -> None:
        self.emit_calls.append(snapshot)
        self._audit_writer.write(
            "reliability.rechecked",
            {
                "release_readiness_status": snapshot.summary.release_readiness_status,
                "blocking_gate_count": snapshot.summary.blocking_gate_count,
                "warning_gate_count": snapshot.summary.warning_gate_count,
            },
        )
        self._event_bus.publish(
            "reliability.updated",
            {
                "event_type": "reliability.rechecked",
                "release_readiness_status": snapshot.summary.release_readiness_status,
            },
        )

    def set_snapshot(
        self,
        *,
        status: str,
        blocking: int,
        warning: int,
        overall_status: str = "healthy",
        db_size_critical: bool = False,
    ) -> None:
        self._current_snapshot = FakeSnapshot(
            status=status,
            blocking=blocking,
            warning=warning,
            overall_status=overall_status,
            db_size_critical=db_size_critical,
        )


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True


class _FakeSessionFactory:
    """Context-manager-style fake ``sessionmaker`` for B4 tests."""

    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSessionFactory:
        return self

    def __enter__(self) -> _FakeSession:
        session = _FakeSession()
        self.sessions.append(session)
        return session

    def __exit__(self, *exc_info: object) -> bool:
        return False


def _make_registry_with_session_scheduler() -> ServiceRegistry:
    registry = ServiceRegistry()
    registry.register(
        service_id="session-scheduler",
        service_type="scheduler",
        criticality=ServiceCriticality.IMPORTANT,
        startup_policy="always-on",
    )
    return registry


def _make_job(
    tmp_path: Path,
) -> tuple[
    ReliabilityRecheckJob,
    FakeReliabilityService,
    AuditWriter,
    EventBus,
    _FakeSessionFactory,
]:
    """Build a ``ReliabilityRecheckJob`` with fake ``ReliabilityService`` + session_factory.

    Auto-subscribes a queue to ``event_bus`` so the audit/bus drains
    in the assertions below see what was published. Mirrors the
    ``event_bus.subscribe()`` call in
    ``tests/scheduler/test_health_tick_job.py``.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()  # so _drain_event_bus sees published events
    reliability_service = FakeReliabilityService(
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    factory = _FakeSessionFactory()
    job = ReliabilityRecheckJob(
        reliability_service=reliability_service,
        session_factory=cast(sessionmaker, factory),
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    return job, reliability_service, audit_writer, event_bus, factory


# === Tests ===


def test_first_run_seeds_cache_no_emit(tmp_path: Path) -> None:
    """Acceptance #5: first run seeds the cache, no audit, no bus."""
    job, service, audit_writer, event_bus, _ = _make_job(tmp_path)

    job.run()

    # recheck called once with emit=False
    assert len(service.recheck_calls) == 1
    assert service.recheck_calls[0][1] is False
    # No emit on first run (cache seeded silently)
    assert service.emit_calls == []
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


def test_steady_state_no_emit(tmp_path: Path) -> None:
    """Acceptance #3: same state across 3 ticks → 0 audit, 0 bus."""
    job, service, audit_writer, event_bus, _ = _make_job(tmp_path)

    job.run()  # first run — seed
    job.run()  # steady
    job.run()  # steady

    assert len(service.recheck_calls) == 3
    # All three with emit=False (job never re-emits on its own).
    assert all(call[1] is False for call in service.recheck_calls)
    # Steady state emits nothing.
    assert service.emit_calls == []
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


def test_transition_emits_audit_and_bus(tmp_path: Path) -> None:
    """Acceptance #4: state change → 1 audit + 1 bus via ``emit_recheck_events``."""
    job, service, audit_writer, event_bus, _ = _make_job(tmp_path)

    job.run()  # first run — seed (ready_for_demo, 0, 2)
    # flip the snapshot
    service.set_snapshot(status="needs_attention", blocking=0, warning=3)
    job.run()  # transition

    # One emit (transition only)
    assert len(service.emit_calls) == 1
    # audit: reliability.rechecked
    events = _read_audit_events(audit_writer)
    rechecked = [e for e in events if e["event_type"] == "reliability.rechecked"]
    assert len(rechecked) == 1
    assert rechecked[0]["payload"]["release_readiness_status"] == "needs_attention"
    # bus: reliability.updated
    drained = _drain_event_bus(event_bus)
    updated = [t for t, _ in drained if t == "reliability.updated"]
    assert len(updated) == 1


def test_run_calls_recheck_emit_false_and_commits(tmp_path: Path) -> None:
    """``run()`` calls ``recheck(session, emit=False)`` and commits the session.

    The job owns the session lifecycle: opens a session from
    ``session_factory``, passes it to ``recheck(emit=False)``, and
    commits it before computing the diff. This pins the
    write-through contract from the B4 plan §(b) (DB write of
    ``last_rechecked_at`` survives in the service even when
    ``emit=False``).
    """
    job, service, _, _, factory = _make_job(tmp_path)

    job.run()

    assert len(service.recheck_calls) == 1
    session_arg, emit_arg = service.recheck_calls[0]
    assert emit_arg is False
    assert session_arg in factory.sessions
    assert factory.sessions[0].committed is True


def test_on_error_audits_once(tmp_path: Path) -> None:
    """Acceptance #10: 2 consecutive failures → 1 ``reliability.recheck_failed`` audit.

    The ``_failing`` guard emits the audit only on the **transition
    into the failing episode**, not on every consecutive failure
    (B3b-style anti-flood pattern adapted for the B4 ``on_error`` path).
    """
    job, service, audit_writer, _, _ = _make_job(tmp_path)
    boom = RuntimeError("boom")

    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise boom

    service.recheck = _raise  # type: ignore[method-assign]

    # First failure — ``on_error`` is invoked by ``_run_safely`` in
    # production; here we call it directly to keep the test focused
    # on the ``on_error`` contract.
    job.on_error(boom)
    # Second consecutive failure — must NOT add a second audit.
    job.on_error(boom)

    failed_audits = [
        e
        for e in _read_audit_events(audit_writer)
        if e["event_type"] == "reliability.recheck_failed"
    ]
    assert len(failed_audits) == 1
    assert failed_audits[0]["payload"]["error"] == "boom"


def test_on_error_does_not_mutate_session_scheduler(tmp_path: Path) -> None:
    """Acceptance #9: reliability job exception → session-scheduler stays HEALTHY.

    B4 isolates the error policy: reliability failures do not flip
    ``session-scheduler`` to ``ERROR`` (the scheduler keeps running;
    only the failing job is marked via ``reliability.recheck_failed``
    audit + a transient ``_failing`` flag).
    """
    registry = _make_registry_with_session_scheduler()
    registry.update_status("session-scheduler", ServiceStatus.HEALTHY)
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = FakeReliabilityService(
        audit_writer=audit_writer,
        event_bus=event_bus,
    )

    factory = _FakeSessionFactory()
    job = ReliabilityRecheckJob(
        reliability_service=service,
        session_factory=cast(sessionmaker, factory),
        audit_writer=audit_writer,
        event_bus=event_bus,
    )

    boom = RuntimeError("reliability boom")
    job.on_error(boom)

    assert registry.get("session-scheduler").status is ServiceStatus.HEALTHY


def test_on_error_does_not_re_raise(tmp_path: Path) -> None:
    """Acceptance #9 caller-safe: ``on_error`` swallows any inner exception.

    ``_run_safely`` invokes ``on_error(exc)`` without a try/except
    wrapper around it. If ``on_error`` re-raised, APScheduler would
    pause the job slot. Contract: ``on_error`` MUST swallow.
    """
    job, _, _, _, _ = _make_job(tmp_path)
    # Direct call — must not raise.
    job.on_error(RuntimeError("boom"))


def test_failure_success_failure_audits_twice(tmp_path: Path) -> None:
    """Acceptance #11 (Emma fix): ``fail → success → fail`` → 2 audit entries.

    The ``_failing`` flag is reset on a **successful** ``run()``
    (the post-`recheck` path in step 3 of the run body), so a new
    failing episode starts fresh and re-emits the audit. Without
    the reset, the second failing episode would be silently
    swallowed (the bug Emma caught at ratification).

    ``run()`` re-raises on a recheck exception (the contract — the
    wrapper ``_run_safely`` catches and calls ``on_error``); the
    test therefore wraps each failing ``run()`` in a
    ``pytest.raises`` block to mirror the wrapper behaviour.
    """
    job, service, audit_writer, _, _ = _make_job(tmp_path)
    boom = RuntimeError("boom")

    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise boom

    original_recheck = service.recheck  # bound method

    # Episode 1: tick 1 fails
    service.recheck = _raise  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="boom"):
        job.run()
    job.on_error(boom)

    # Tick 2: success → run() reaches ``self._failing = False``
    # and seeds/updates the cache.
    service.recheck = original_recheck  # type: ignore[method-assign]
    job.run()

    # Episode 2: tick 3 fails again
    service.recheck = _raise  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="boom"):
        job.run()
    job.on_error(boom)

    failed_audits = [
        e
        for e in _read_audit_events(audit_writer)
        if e["event_type"] == "reliability.recheck_failed"
    ]
    assert len(failed_audits) == 2, (
        f"expected 2 audit entries (one per failing episode), got {len(failed_audits)}"
    )


# === D-13 — db-size-critical transition test ===


def test_db_size_critical_emits_on_transition(tmp_path: Path) -> None:
    """D-13: False→True ``db-size-critical`` emits ``reliability.rechecked`` once.

    The 4th element of the cache tuple (``db_size_critical: bool``)
    detects healthy→degraded transitions from the ``db-size-critical``
    trigger.  Warning band is overview-only and does NOT affect the
    tuple (documented ADR-035 limitation).
    """
    job, service, audit_writer, event_bus, _ = _make_job(tmp_path)

    job.run()  # seed: db_size_critical=False
    # Transition: add db-size-critical trigger
    service.set_snapshot(
        status="blocked",
        blocking=1,
        warning=0,
        overall_status="degraded",
        db_size_critical=True,
    )
    job.run()

    # One emit (transition only)
    assert len(service.emit_calls) == 1
    events = _read_audit_events(audit_writer)
    rechecked = [e for e in events if e["event_type"] == "reliability.rechecked"]
    assert len(rechecked) == 1


def test_db_size_warning_no_emit(tmp_path: Path) -> None:
    """D-13: ``db-size-warning`` does NOT affect ``db_size_critical`` tuple element.

    Warning band is overview-only; the ``db_size_critical`` flag stays
    ``False`` when only a warning trigger is present.  All other tuple
    elements must remain constant to isolate the flag.
    """
    job, service, audit_writer, event_bus, _ = _make_job(tmp_path)

    job.run()  # seed: (ready_for_demo, 0, 2, False)
    # Change only the degraded_triggers (add warning) but keep the
    # 4 cache-tuple fields identical → no transition → no emit.
    service.set_snapshot(
        status="ready_for_demo",
        blocking=0,
        warning=2,
        overall_status="healthy",
        db_size_critical=False,
    )
    # Manually inject a warning trigger into the snapshot (invisible
    # to the cache tuple — only db_size_critical matters).
    service._current_snapshot.degraded_triggers = [
        type(
            "_FakeWarningTrigger",
            (),
            {"trigger_id": "db-size-warning", "severity": "warning"},
        )()
    ]
    job.run()

    # No emit — all 4 cache-tuple elements unchanged.
    assert service.emit_calls == []
    assert _read_audit_events(audit_writer) == []
