"""Tests for the B5 ``IngestionCycleJob`` (scheduler-driven async ingestion).

B5 acceptance criteria (from handoffs/b5-plan-2026-06-02.md):

The job implements the B4 anti-flood / transition-only pattern
(``first-run seed`` + ``transition-diff`` + ``_failing`` reset
on success) on a 2-field state tuple — ``(incidents_present,
freshness_state_transitions)`` — plus the B5-specific skip / busy
paths that come from the ``asyncio.Lock`` guard on
``IngestionCycleService``.

1. ``test_run_calls_run_once_emit_false_and_commits`` — the scheduler
   path: ``run_once(session, emit=False)`` + commit (DB writes
   persist; emit skipped at the service level).
2. ``test_first_run_seeds_cache_no_emit`` — first tick seeds the
   ``(incidents, transitions)`` cache, emits nothing.
3. ``test_steady_state_no_emit`` — same state across 3 ticks →
   0 audit, 0 bus.
4. ``test_transition_emits_audit_and_bus`` — state change → 1 audit
   + 1 bus via ``IngestionCycleService.emit_cycle_events``.
5. ``test_on_error_audits_once`` — B4 #10 anti-flood: 2 consecutive
   failures → 1 ``ingestion.cycle_failed`` audit.
6. ``test_on_error_does_not_mutate_session_scheduler`` — B4 #9:
   ingestion failure is isolated, ``session-scheduler`` stays
   ``HEALTHY``.
7. ``test_on_error_does_not_re_raise`` — B4 #9 caller-safe contract.
8. ``test_failure_success_failure_audits_twice`` — B4 #11 (Emma fix):
   ``fail → success → fail`` → 2 audit entries (the ``_failing``
   reset on success).
9. ``test_skip_when_service_running`` — B5-specific: when
   ``service.is_running`` is ``True`` at the start of the tick,
   the job skips the call entirely (no DB writes, no audit).
10. ``test_race_concurrent_ingestion_raises_busy`` — B5-specific:
    if ``run_once`` raises ``IngestionCycleBusy`` (a second
    caller started between the ``is_running`` check and the
    ``run_once`` call), the job logs and skips without re-raising.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.ingestion.service import IngestionCycleBusy, IngestionRunSummary
from clay.scheduler.jobs import IngestionCycleJob
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry


def _read_audit_events(audit_writer: AuditWriter) -> list[dict[str, Any]]:
    """Read the JSONL audit log. Returns ``[]`` if the file does not exist."""
    if not audit_writer.path.exists():
        return []
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


def _make_summary(
    *,
    incidents: int = 0,
    freshness_state_transitions: int = 0,
    market_records_inserted: int = 0,
    market_records_updated: int = 0,
) -> IngestionRunSummary:
    """Build a minimal ``IngestionRunSummary`` for diff/emit assertions.

    B5 split the pre-B5 ``market_records_written`` total into
    ``market_records_inserted`` + ``market_records_updated``
    (the property ``market_records_written`` is now
    ``= inserted + updated``). Test fixtures use the
    fields directly.
    """
    started = datetime.now(UTC)
    return IngestionRunSummary(
        started_at=started,
        finished_at=started,
        market_records_inserted=market_records_inserted,
        market_records_updated=market_records_updated,
        incidents=[{"source_name": "x", "severity": "error", "message": "y"}] * incidents,
        freshness_state_transitions=freshness_state_transitions,
    )


class FakeIngestionService:
    """Duck-typed fake matching ``_IngestionCycleRunnable``.

    Holds the 2-tuple ``(incidents_present, freshness_state_transitions)``
    in ``_current_state`` so tests can flip it between runs and
    observe the transition-only emit.

    ``is_running`` defaults to ``False``; flip it manually to drive
    the skip-when-busy path. ``raise_busy_once`` flips ``is_running``
    inside the next ``run_once`` call to simulate a TOCTOU race.

    C3: ``run_once`` no longer takes a ``session`` parameter — the
    real service owns the session lifecycle inside ``_persist``.
    """

    def __init__(
        self,
        *,
        audit_writer: AuditWriter,
        event_bus: EventBus,
    ) -> None:
        self._audit_writer = audit_writer
        self._event_bus = event_bus
        self._incidents = 0
        self._transitions = 0
        self._is_running = False
        self.run_once_calls: list[bool] = []
        self.emit_calls: list[IngestionRunSummary] = []
        self._raise_busy_once = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def set_running(self, value: bool) -> None:
        self._is_running = value

    def set_state(self, *, incidents: int, transitions: int) -> None:
        """Flip the 2-tuple the job's transition-diff watches."""
        self._incidents = incidents
        self._transitions = transitions

    def arm_race(self) -> None:
        """Arm a one-shot ``IngestionCycleBusy`` raise on the next ``run_once``.

        Used to simulate a TOCTOU race: between the job's
        ``is_running`` check and the ``run_once`` call, a second
        caller acquires the service's lock.
        """
        self._raise_busy_once = True

    async def run_once(self, *, emit: bool = True) -> IngestionRunSummary:
        self.run_once_calls.append(emit)
        if self._raise_busy_once:
            self._raise_busy_once = False
            raise IngestionCycleBusy("test race")
        summary = _make_summary(
            incidents=self._incidents,
            freshness_state_transitions=self._transitions,
        )
        return summary

    def emit_cycle_events(self, summary: IngestionRunSummary) -> None:
        self.emit_calls.append(summary)
        payload = {
            "market_records_written": summary.market_records_written,
            "freshness_state_transitions": summary.freshness_state_transitions,
            "incidents": len(summary.incidents),
        }
        self._audit_writer.write("ingestion.run", payload)
        self._event_bus.publish(
            "ingestion.updated",
            {"event_type": "ingestion.run", **payload},
        )


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
    IngestionCycleJob,
    FakeIngestionService,
    AuditWriter,
    EventBus,
]:
    """Build an ``IngestionCycleJob`` with fakes for service + deps.

    C3: job no longer holds ``session_factory`` — session lifecycle
    lives inside ``IngestionCycleService._persist``.
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()
    service = FakeIngestionService(
        audit_writer=audit_writer, event_bus=event_bus,
    )
    job = IngestionCycleJob(
        ingestion_service=service,  # type: ignore[arg-type]
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    return job, service, audit_writer, event_bus


# === Tests ===


@pytest.mark.anyio
async def test_run_calls_run_once_emit_false_and_commits(tmp_path: Path) -> None:
    """``run()`` calls ``run_once(session, emit=False)`` and the commit
    happens inside ``_do_run_once`` (B6 cleanup).

    The job owns the session lifecycle: opens a session from
    ``session_factory`` and calls the service with ``emit=False`` (the
    scheduler-driven path). The actual commit happens inside
    ``IngestionCycleService._do_run_once`` under the service's
    ``asyncio.Lock`` (``ingestion/service.py:177``) — the prior
    explicit ``session.commit()`` here was a harmless no-op and is
    removed (B6 cleanup).
    """
    job, service, _, _ = _make_job(tmp_path)

    await job.run()

    assert len(service.run_once_calls) == 1
    assert service.run_once_calls[0] is False


@pytest.mark.anyio
async def test_first_run_seeds_cache_no_emit(tmp_path: Path) -> None:
    """Acceptance: first run seeds the cache, no audit, no bus."""
    job, service, audit_writer, event_bus = _make_job(tmp_path)

    await job.run()

    assert len(service.run_once_calls) == 1
    assert service.emit_calls == []
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


@pytest.mark.anyio
async def test_steady_state_no_emit(tmp_path: Path) -> None:
    """Acceptance: same state across 3 ticks → 0 audit, 0 bus."""
    job, service, audit_writer, event_bus = _make_job(tmp_path)

    await job.run()  # first run — seed
    await job.run()  # steady
    await job.run()  # steady

    assert len(service.run_once_calls) == 3
    assert all(call is False for call in service.run_once_calls)
    assert service.emit_calls == []
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


@pytest.mark.anyio
async def test_transition_emits_audit_and_bus(tmp_path: Path) -> None:
    """Acceptance: state change → 1 audit + 1 bus via ``emit_cycle_events``."""
    job, service, audit_writer, event_bus = _make_job(tmp_path)

    await job.run()  # first run — seed (0 incidents, 0 transitions)
    service.set_state(incidents=1, transitions=4)
    await job.run()  # transition

    # One emit (transition only).
    assert len(service.emit_calls) == 1

    # audit: ingestion.run
    events = _read_audit_events(audit_writer)
    run_events = [e for e in events if e["event_type"] == "ingestion.run"]
    assert len(run_events) == 1
    assert run_events[0]["payload"]["freshness_state_transitions"] == 4
    assert run_events[0]["payload"]["incidents"] == 1

    # bus: ingestion.updated
    drained = _drain_event_bus(event_bus)
    updated = [t for t, _ in drained if t == "ingestion.updated"]
    assert len(updated) == 1


@pytest.mark.anyio
async def test_on_error_audits_once(tmp_path: Path) -> None:
    """Acceptance: 2 consecutive failures → 1 ``ingestion.cycle_failed`` audit.

    B4 #10 anti-flood: the ``_failing`` guard emits the audit only
    on the transition into the failing episode, not on every
    consecutive failure.
    """
    job, _, audit_writer, _ = _make_job(tmp_path)
    boom = RuntimeError("boom")

    job.on_error(boom)
    job.on_error(boom)

    failed_audits = [
        e for e in _read_audit_events(audit_writer)
        if e["event_type"] == "ingestion.cycle_failed"
    ]
    assert len(failed_audits) == 1
    assert failed_audits[0]["payload"]["error"] == "boom"


@pytest.mark.anyio
async def test_on_error_does_not_mutate_session_scheduler(tmp_path: Path) -> None:
    """Acceptance: ingestion failure is isolated, ``session-scheduler`` stays HEALTHY.

    B4 #9 carries over: a scheduler-driven ingestion failure does
    not flip ``session-scheduler`` to ``ERROR``. The scheduler
    keeps running; only the failing job is signalled via
    ``ingestion.cycle_failed`` audit + a transient ``_failing`` flag.
    """
    registry = _make_registry_with_session_scheduler()
    registry.update_status("session-scheduler", ServiceStatus.HEALTHY)
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    service = FakeIngestionService(
        audit_writer=audit_writer, event_bus=event_bus,
    )
    job = IngestionCycleJob(
        ingestion_service=service,  # type: ignore[arg-type]
        audit_writer=audit_writer,
        event_bus=event_bus,
    )

    job.on_error(RuntimeError("ingestion boom"))

    assert registry.get("session-scheduler").status is ServiceStatus.HEALTHY


@pytest.mark.anyio
async def test_on_error_does_not_re_raise(tmp_path: Path) -> None:
    """Acceptance: ``on_error`` swallows any inner exception (caller-safe)."""
    job, _, _, _ = _make_job(tmp_path)
    # Direct call — must not raise.
    job.on_error(RuntimeError("boom"))


@pytest.mark.anyio
async def test_failure_success_failure_audits_twice(tmp_path: Path) -> None:
    """Acceptance: ``fail → success → fail`` → 2 audit entries (Emma's #11).

    The ``_failing`` flag is reset on a **successful** ``run()``
    (after the service returns + ``commit()`` runs), so a new
    failing episode re-emits the audit. Without the reset, the
    second failing episode would be silently swallowed.

    Pattern mirrors ``test_reliability_recheck_job`` #8 — B4 #11
    is a mandatory carry-forward for every B4-pattern job.
    """
    job, service, audit_writer, _ = _make_job(tmp_path)
    boom = RuntimeError("boom")

    async def _raise(*args: Any, **kwargs: Any) -> Any:
        raise boom

    # Episode 1: first tick fails.
    service.run_once = _raise  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="boom"):
        await job.run()
    job.on_error(boom)

    # Tick 2: success — run() reaches ``self._failing = False`` and
    # seeds/updates the cache.
    async def _ok(*args: Any, **kwargs: Any) -> IngestionRunSummary:
        return _make_summary()

    service.run_once = _ok  # type: ignore[method-assign]
    await job.run()

    # Episode 2: third tick fails again.
    service.run_once = _raise  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="boom"):
        await job.run()
    job.on_error(boom)

    failed_audits = [
        e for e in _read_audit_events(audit_writer)
        if e["event_type"] == "ingestion.cycle_failed"
    ]
    assert len(failed_audits) == 2, (
        f"expected 2 audit entries (one per failing episode), "
        f"got {len(failed_audits)}"
    )


@pytest.mark.anyio
async def test_skip_when_service_running(tmp_path: Path) -> None:
    """B5-specific: ``is_running=True`` at tick start → skip without emit.

    The scheduler-driven tick sees the lock held and short-circuits
    to a quiet log line — no ``run_once`` call, no DB write, no
    audit. ``max_instances=1`` + ``coalesce=True`` cover the
    worst-case back-pressure; this branch is the explicit
    observability of the TOCTOU path.
    """
    job, service, audit_writer, event_bus = _make_job(tmp_path)
    service.set_running(True)

    await job.run()

    assert service.run_once_calls == []
    assert service.emit_calls == []
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []


@pytest.mark.anyio
async def test_race_concurrent_ingestion_raises_busy(tmp_path: Path) -> None:
    """B5-specific: race between ``is_running`` check and ``run_once`` call.

    If a second caller acquires the service's lock between the
    job's ``is_running`` snapshot and the ``run_once`` call, the
    service raises ``IngestionCycleBusy``. The job catches it,
    logs, and skips — it does **not** propagate (the
    ``_run_safely`` wrapper is the caller's caller, and
    ``on_error`` is the dedicated error-policy path).

    After the race, the cache is still ``None`` (the race
    short-circuited before step 3's seed path). The next normal
    call seeds the cache; the third call with a different state
    emits once — proving the race is a one-shot and the job is
    reusable across real ticks.
    """
    job, service, audit_writer, event_bus = _make_job(tmp_path)

    # Seed the cache with a baseline state.
    service.set_state(incidents=0, transitions=0)
    await job.run()  # first run — seed, no emit

    # Arm the race: next ``run_once`` raises ``IngestionCycleBusy``.
    service.arm_race()
    # Does NOT raise (job catches ``IngestionCycleBusy`` internally).
    await job.run()

    # The race short-circuited — no emit, no audit.
    assert service.emit_calls == []
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []

    # Now flip the state and run again. Cache is (False, 0); new
    # state is (False, 4) → transition → 1 emit.
    service.set_state(incidents=0, transitions=4)
    await job.run()
    assert len(service.emit_calls) == 1
