"""Scheduled jobs for ``ClayScheduler``.

B3b: the first useful scheduler job — ``HealthTickJob``.

Each tick:

1. Snapshots the current statuses of all services (``before``).
2. Heartbeats **only** ``session-scheduler`` (proof the loop is alive).
3. Re-asserts ``session-scheduler`` as ``HEALTHY`` — in steady state this
   is a no-op, but it is the recovery path from ``ERROR`` (when a
   previous tick raised). The diff-then-audit step (6) catches the
   ``ERROR → HEALTHY`` transition and audits it like any other
   transition.
4. Runs ``HealthMonitor.refresh()`` — the ``None``-guard on
   ``last_heartbeat_at`` already exempts services that don't heartbeat
   themselves (so this can't false-positive ``STALE`` on services whose
   ``last_heartbeat_at`` is still ``None``).
5. Publishes ``health.tick`` to ``event_bus`` (live observability;
   **not** written to audit to keep ``audit.jsonl`` from being flooded
   with per-tick noise).
6. Diffs ``before`` → ``after``; for every service whose status
   changed, writes ``service.status_changed`` to audit **and**
   publishes the same event on the bus.

Heartbeat-scope is **only** ``session-scheduler`` by design (Emma fix,
captured in ``.context/handoffs/current.md`` §41-50 of Wave B): a tick
that heartbeats every registered service would defeat
``HealthMonitor.refresh()``'s stale-detection by always keeping
``last_heartbeat_at = now`` for everyone — the refresh's
``now - last_heartbeat_at`` comparison would always come out
``≈ 0 < stale_after``, and **no service would ever be flagged
``STALE``**.

The self-heartbeating tick is **itself** incapable of detecting its
own death (if the tick thread hangs, no new ``last_heartbeat_at``
will be written, but there is no external reader doing the
comparison). That is an **out-of-scope v1 limitation**; an external
watchdog is the proper mitigation and is left for a future slice.

B4: the second job — ``ReliabilityRecheckJob``. Scheduler-driven
reliability recheck with **transition-only** audit/bus emission
(B3b anti-flood pattern) and an **isolated error policy** (a
reliability-recheck exception is **not** propagated to
``session-scheduler`` — it lives in this job's own
``_failing`` flag and ``reliability.recheck_failed`` audit).

B5: the third job — ``IngestionCycleJob``. Async coroutine
registered with ``ClayScheduler._arun_safely`` (NOT ``_run_safely``
— sync wrapper would never await ``run()``'s coroutine, silent
no-op; Emma's fragment D mandatory code fix). The 2-tuple
``(incidents_present, freshness_state_transitions)`` is the
**transition signal** the job diffs; the B4 anti-flood /
first-run / ``_failing`` reset / isolated-error pattern carries
over verbatim.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from clay.ingestion.service import IngestionCycleBusy, IngestionRunSummary
from clay.services.models import ServiceStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from clay.audit.writer import AuditWriter
    from clay.events.bus import EventBus
    from clay.health.monitor import HealthMonitor
    from clay.services.registry import ServiceRegistry

logger = logging.getLogger(__name__)


class _ReliabilityRecheckable(Protocol):
    """Duck-typed surface the B4 job depends on.

    Matches the real ``ReliabilityService`` (production wiring) and
    the test fakes — both expose ``recheck(session, *, emit)`` and
    ``emit_recheck_events(snapshot)``. Kept as a ``Protocol`` (not
    an ABC) so production does not need to inherit from it.
    """

    def recheck(self, session: Any, *, emit: bool = True) -> Any: ...

    def emit_recheck_events(self, snapshot: Any) -> None: ...


class _IngestionCycleRunnable(Protocol):
    """Duck-typed surface the B5 job depends on.

    Matches the real ``IngestionCycleService`` (production wiring)
    and the test fakes — both expose ``is_running`` (property),
    ``run_once(session, *, emit)`` (async coroutine), and
    ``emit_cycle_events(summary)`` (public, single source of
    payload shape — the manual route and the scheduler-driven
    job anti-flood diff both go through it).

    Kept as a ``Protocol`` (not an ABC) so production does not
    need to inherit from it.
    """

    @property
    def is_running(self) -> bool: ...

    async def run_once(
        self, *, emit: bool = ...,
    ) -> IngestionRunSummary: ...

    def emit_cycle_events(self, summary: IngestionRunSummary) -> None: ...


class HealthTickJob:
    """B3b health-tick job — sync callable for the APScheduler thread-pool.

    ``run()`` is intentionally **synchronous**. APScheduler's
    ``interval`` trigger dispatches the callable in the
    ``ThreadPoolExecutor`` named ``"default"`` (B3a / B0 §11.1
    mitigation), so blocking calls here (DB, file, etc.) do **not**
    stall the asyncio loop serving the request handlers.

    Constructor dependencies are explicit; ``jobs.py`` does **not**
    import ``clay.bootstrap`` (A6 lesson: production wiring is the
    same wiring as the test wiring).
    """

    _SERVICE_ID = "session-scheduler"

    def __init__(
        self,
        registry: ServiceRegistry,
        health_monitor: HealthMonitor,
        audit_writer: AuditWriter,
        event_bus: EventBus,
    ) -> None:
        self._registry = registry
        self._health_monitor = health_monitor
        self._audit_writer = audit_writer
        self._event_bus = event_bus

    def run(self) -> None:
        """Execute one health tick. See module docstring for the rationale."""
        before: dict[str, ServiceStatus] = {
            record.service_id: record.status
            for record in self._registry.list_services()
        }
        self._registry.get(self._SERVICE_ID).heartbeat()
        self._registry.update_status(self._SERVICE_ID, ServiceStatus.HEALTHY)
        self._health_monitor.refresh()
        self._event_bus.publish(
            "health.tick",
            {
                "tick_at": datetime.now(UTC).isoformat(),
                "services": [
                    {
                        "id": record.service_id,
                        "status": record.status.value,
                    }
                    for record in self._registry.list_services()
                ],
            },
        )
        after: dict[str, ServiceStatus] = {
            record.service_id: record.status
            for record in self._registry.list_services()
        }
        for service_id, prev_status in before.items():
            new_status = after[service_id]
            if prev_status == new_status:
                continue
            payload: dict[str, Any] = {
                "service_id": service_id,
                "from": prev_status.value,
                "to": new_status.value,
            }
            self._audit_writer.write("service.status_changed", payload)
            self._event_bus.publish("service.status_changed", payload)


class ReliabilityRecheckJob:
    """B4 scheduler-driven reliability recheck — sync callable for APScheduler's thread-pool.

    Each tick:

    1. Opens a transient ``Session`` from ``session_factory`` (the
       scheduler-owned factory; the job owns the session lifecycle so
       the operator-trusted ``last_rechecked_at`` write-through
       happens even when the service is not in a real request
       handler).
    2. Calls ``reliability_service.recheck(session, emit=False)`` —
       ``emit=False`` skips the A6 audit/bus emission (the B4 plan
       ratified Option B from
       ``obs-2026-06-02-002-b4-recon-side-effect-concern.md``);
       ``recheck`` still persists ``last_rechecked_at`` in-memory
       and in the DB, so the A5 contract holds.
    3. Commits the session (so the durable write survives
       ``apscheduler`` crashes mid-tick) and **resets the
       ``_failing`` episode** — a successful run closes the
       failing episode so the next failure re-emits the audit
       (Emma's mandatory fix from the B4 ratification).
    4. Computes the new state tuple ``(release_readiness_status,
       blocking_gate_count, warning_gate_count)``. If ``_cache`` is
       ``None`` (first run after process start), **seed it and
       return** — no audit, no bus, the operator does not need to
       know the job came up.
    5. If the new state equals the cached state, **return** — a
       steady state emits nothing (B3b anti-flood pattern).
    6. If the new state differs, **invoke
       ``reliability_service.emit_recheck_events(snapshot)``** (the
       public method that owns the audit + bus payload shape) and
       update ``_cache``.

    Error policy (isolated from ``HealthTickJob`` — B4 (a)):

    The job is registered with APScheduler ``kwargs={"on_error":
    job.on_error}`` so ``ClayScheduler._run_safely`` invokes
    ``on_error(exc)`` on the first raised exception per failing
    episode (B3b-style anti-flood). The reliability job's error
    policy is **isolated**: it does not flip ``session-scheduler``
    to ``ERROR`` and does not write ``service.status_changed`` —
    it writes ``reliability.recheck_failed`` (the dedicated
    verb) and sets a transient ``_failing`` flag. The flag is
    **reset on the next successful ``run()``** (step 3), so a
    new failing episode re-emits the audit. Without the reset,
    a second failing episode would be silently swallowed (the
    bug Emma caught at ratification — see
    ``handoffs/current.md`` §B4 (b) + Acceptance #11).
    """

    def __init__(
        self,
        *,
        reliability_service: _ReliabilityRecheckable,
        session_factory: sessionmaker,
        audit_writer: AuditWriter,
        event_bus: EventBus,  # reserved (v2: reliability.tick)
    ) -> None:
        self._reliability_service = reliability_service
        self._session_factory = session_factory
        self._audit_writer = audit_writer
        self._event_bus = event_bus
        # First-run seed; cleared on the first successful run().
        self._cache: tuple[str, int, int] | None = None
        # Episode flag for the on_error anti-flood; reset on success.
        self._failing: bool = False

    def run(self) -> None:
        """Execute one reliability recheck tick. See class docstring."""
        with self._session_factory() as session:
            snapshot = self._reliability_service.recheck(session, emit=False)
            session.commit()
        # Step 3: a successful tick closes the failing episode so a
        # later failure re-emits ``reliability.recheck_failed``
        # (Acceptance #11, Emma's mandatory fix). Reaches this line
        # only if ``recheck`` and ``commit`` did not raise.
        self._failing = False
        new_state = (
            snapshot.summary.release_readiness_status,
            snapshot.summary.blocking_gate_count,
            snapshot.summary.warning_gate_count,
        )
        if self._cache is None:
            # First run after process start — seed the cache, do not
            # emit (the operator does not need a flood of "we came
            # up" events).
            self._cache = new_state
            return
        if new_state == self._cache:
            # Steady state — nothing changed since the last emit.
            return
        # Transition — emit through the public method (single source
        # of payload shape, shared with the manual route).
        self._reliability_service.emit_recheck_events(snapshot)
        self._cache = new_state

    def on_error(self, exc: Exception) -> None:
        """Isolated error policy for the reliability recheck job.

        Called by ``ClayScheduler._run_safely`` on a tick exception
        (per the B4 (a) ``on_error`` parameter). Writes
        ``reliability.recheck_failed`` **once per failing episode**
        (B3b-style anti-flood: consecutive failures do **not** add
        a second audit entry). Sets ``_failing = True`` so the
        next failed ``on_error`` is silent. The flag is reset on
        the next successful ``run()`` (step 3 of that method) so a
        new failing episode re-emits the audit (Acceptance #11).

        Does **not** mutate ``session-scheduler`` status (the
        scheduler keeps running; only the failing job is
        signalled). Does **not** re-raise — APScheduler must not
        pause the job slot indefinitely.
        """
        if not self._failing:
            self._audit_writer.write(
                "reliability.recheck_failed", {"error": str(exc)},
            )
        self._failing = True
        logger.exception(
            "clay.scheduler: reliability recheck failed; "
            "session-scheduler NOT marked ERROR (isolated policy)",
        )


class IngestionCycleJob:
    """B5 scheduler-driven ingestion cycle — async coroutine for the event loop.

    **Routing:** ``run()`` is an ``async def`` coroutine. The job is
    registered with ``ClayScheduler._arun_safely`` (NOT
    ``_run_safely`` — sync wrapper would not await the coroutine,
    silent no-op). See ``scheduler/service.py`` for the routing
    matrix and ``ClayScheduler.add_ingestion_cycle_job``.

    Each tick:

    1. Checks ``service.is_running`` — if ``True`` (a manual
       route call is in flight), the tick short-circuits to a
       ``logger.info`` line and returns. ``max_instances=1`` and
       ``coalesce=True`` cover the worst-case back-pressure;
       this branch is the explicit observability of the
       TOCTOU path. **TOCTOU race** is then closed by the
       service's own ``asyncio.Lock``; a race that gets past
       the pre-tick check raises ``IngestionCycleBusy`` inside
       ``run_once``, which the job catches and treats as a
       skip (no audit, no emit).
    2. Opens a transient ``Session`` from ``session_factory``,
       calls ``service.run_once(session, emit=False)`` (the
       scheduler path — DB writes happen, observability is
       the job's own transition-only emit), and commits the
       session. **A successful tick closes the failing
       episode** (B4 #11 mandatory fix).
    3. Computes the 2-tuple state
       ``(bool(incidents), freshness_state_transitions)``.
       If ``_cache`` is ``None`` (first run after process
       start), **seed it and return** — no audit, no bus.
    4. If the new state equals the cached state, **return**
       (steady state emits nothing — B3b anti-flood pattern;
       16 upserts per tick × 1440 ticks/day = 0 audit/day
       in steady state, the Поправка 2 anti-flood
       correctness).
    5. If the new state differs, **invoke
       ``service.emit_cycle_events(summary)``** (the public
       method, single source of payload shape shared with
       the manual route) and update ``_cache``.

    Error policy (isolated from ``HealthTickJob``, mirroring
    the B4 ``ReliabilityRecheckJob`` pattern):

    The job is registered with APScheduler
    ``kwargs={"on_error": job.on_error}`` so the new
    ``_arun_safely`` wrapper invokes ``on_error(exc)`` on
    a tick exception. The ingestion job's policy is
    **isolated**: it does not flip ``session-scheduler`` to
    ``ERROR`` and does not write ``service.status_changed``
    — it writes ``ingestion.cycle_failed`` (the dedicated
    verb) and sets a transient ``_failing`` flag. The flag
    is **reset on the next successful ``run()``** (step 2),
    so a new failing episode re-emits the audit (B4 #11).
    """

    def __init__(
        self,
        *,
        ingestion_service: _IngestionCycleRunnable,
        audit_writer: AuditWriter,
        event_bus: EventBus,  # reserved (v2: ingestion.tick)
    ) -> None:
        self._service = ingestion_service
        self._audit_writer = audit_writer
        self._event_bus = event_bus
        # First-run seed; cleared on the first successful run().
        # The 2-tuple is the transition signal the job diffs on.
        self._cache: tuple[bool, int] | None = None
        # Episode flag for the on_error anti-flood; reset on success.
        self._failing: bool = False

    async def run(self) -> None:
        """Execute one ingestion-cycle tick. See class docstring."""
        # Step 1: pre-tick ``is_running`` short-circuit. Closes the
        # common-case TOCTOU: a manual route call is in flight.
        if self._service.is_running:
            logger.info(
                "clay.scheduler: ingestion cycle already running, skip tick",
            )
            return
        # Step 2: C3 — session lifecycle is owned by
        # ``IngestionCycleService._persist`` inside ``to_thread``.
        # The job just calls ``run_once(emit=False)``.
        try:
            summary = await self._service.run_once(emit=False)
        except IngestionCycleBusy:
            logger.info(
                "clay.scheduler: ingestion cycle started mid-tick, skip",
            )
            return
        # B4 #11: a successful tick closes the failing episode so a
        # later failure re-emits ``ingestion.cycle_failed``.
        self._failing = False
        # Step 3-5: 2-tuple transition-diff.
        new_state = (
            bool(summary.incidents),
            summary.freshness_state_transitions,
        )
        if self._cache is None:
            # First run after process start — seed the cache, do
            # not emit (the operator does not need a flood of
            # "we came up" events).
            self._cache = new_state
            return
        if new_state == self._cache:
            # Steady state — nothing changed since the last emit.
            # This is the Поправка 2 anti-flood correctness:
            # timestamp-only freshness touches do NOT increment
            # the transition counter, so a steady 60-second tick
            # emits nothing.
            return
        # Transition — emit through the public method (single
        # source of payload shape, shared with the manual route).
        self._service.emit_cycle_events(summary)
        self._cache = new_state

    def on_error(self, exc: Exception) -> None:
        """Isolated error policy for the ingestion cycle job.

        Called by ``ClayScheduler._arun_safely`` on a tick
        exception. Writes ``ingestion.cycle_failed`` **once per
        failing episode** (B3b-style anti-flood). Sets
        ``_failing = True`` so the next failed ``on_error`` is
        silent. The flag is reset on the next successful
        ``run()`` (step 2 of that method) so a new failing
        episode re-emits the audit (B4 #11).

        Does **not** mutate ``session-scheduler`` status
        (the scheduler keeps running; only the failing job
        is signalled). Does **not** re-raise — APScheduler
        must not pause the job slot indefinitely.
        """
        if not self._failing:
            self._audit_writer.write(
                "ingestion.cycle_failed", {"error": str(exc)},
            )
        self._failing = True
        logger.exception(
            "clay.scheduler: ingestion cycle failed; "
            "session-scheduler NOT marked ERROR (isolated policy)",
        )


class OpsRetentionJob:
    """MP1 scheduler-driven ops.* retention prune-job — sync callable for thread-pool.

    Each tick opens a transient session, prunes the 3 ops.* telemetry
    tables (``ingest_runs``, ``connector_status_history``,
    ``source_health_events``) by their respective retention windows,
    commits, and logs per-table deletion counts.

    Construction: explicit ``session_factory`` DI (never imports
    ``clay.bootstrap``). The job owns its session lifecycle — the
    session is created, used, and closed entirely inside the worker
    thread (confirm (a): sync on threadpool).

    Error policy (isolated, mirroring ``ReliabilityRecheckJob``):
    exceptions are caught by ``ClayScheduler._run_safely``, which
    delegates to ``on_error`` (writes ``ops.retention_failed`` audit)
    and does **not** flip ``session-scheduler`` to ``ERROR``.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        audit_writer: AuditWriter,
    ) -> None:
        self._session_factory = session_factory
        self._audit_writer = audit_writer
        self._failing: bool = False

    def run(self) -> None:
        """Execute one ops-retention tick — prune all 3 tables, then commit."""
        from sqlalchemy import delete
        from clay.retention.jobs import RETENTION_WINDOWS_DAYS
        from clay.db.models_ops import AIAgentRun, IngestRun, ConnectorStatusHistory, SourceHealthEvent

        now = datetime.now(UTC)
        deleted_total = 0
        with self._session_factory() as session:
            for model_class, time_col_name, window_days in [
                (AIAgentRun, "created_at", RETENTION_WINDOWS_DAYS["ai_agent_runs"]),
                (IngestRun, "started_at", RETENTION_WINDOWS_DAYS["ingest_runs"]),
                (ConnectorStatusHistory, "observed_at", RETENTION_WINDOWS_DAYS["connector_status_history"]),
                (SourceHealthEvent, "recorded_at", RETENTION_WINDOWS_DAYS["source_health_events"]),
            ]:
                cutoff = now - timedelta(days=window_days)
                time_col = getattr(model_class, time_col_name)
                result = session.execute(
                    delete(model_class).where(time_col < cutoff)
                )
                deleted_total += result.rowcount
            session.commit()
        self._failing = False
        if deleted_total > 0:
            logger.info(
                "clay.scheduler: ops-retention pruned %d rows",
                deleted_total,
            )

    def on_error(self, exc: Exception) -> None:
        """Isolated error policy for the ops-retention job.

        Called by ``ClayScheduler._run_safely`` on a tick exception.
        Writes ``ops.retention_failed`` once per failing episode
        (B3b-style anti-flood). Does **not** mutate
        ``session-scheduler`` status — the scheduler keeps running.
        """
        if not self._failing:
            self._audit_writer.write(
                "ops.retention_failed", {"error": str(exc)},
            )
        self._failing = True
        logger.exception(
            "clay.scheduler: ops retention failed; "
            "session-scheduler NOT marked ERROR (isolated policy)",
        )
