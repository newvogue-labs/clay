"""Clay scheduler — APScheduler wrapper for non-request background work.

B3a introduced the scaffold (``start()`` / ``shutdown(wait=True)`` plus
a real ``session-scheduler`` status replacing the pre-B3 fake
``HEALTHY`` stamp in ``bootstrap.py``). B3b adds the first useful job:
``HealthTickJob`` (heartbeat scope, stale sweep, transition-only audit)
plus an exception-safe wrapper (``_run_safely``) so an exception in
the tick never kills the schedule slot.

B4 added a second job (``ReliabilityRecheckJob``) + an
``on_error=`` parameter on ``_run_safely`` so the reliability job's
isolated error policy lives in the job (not in the scheduler
wrapper). The ``HealthTickJob`` keeps the B3b default
(``session-scheduler`` flips to ``ERROR``).

B5 adds a third job (``IngestionCycleJob``) — an **async**
coroutine, registered with a **new async wrapper
``_arun_safely``** (NOT the sync ``_run_safely``, which would
silently never await the coroutine — Emma's fragment D mandatory
code fix). Both wrappers share a common error-policy helper
``_handle_job_error`` so the B3b default / B4-on-error / B5-isolated
behaviours live in one place.

Design constraints (carry-forward from B0 / A6 / B1):

* **Explicit constructor DI.** Dependencies (``settings``, ``registry``,
  ``health_monitor``, ``audit_writer``, ``event_bus``) are passed by
  keyword argument. ``ClayScheduler`` never imports ``clay.bootstrap``
  — the A6 lesson holds: production wiring is the same wiring as the
  test wiring; tests construct ``ClayScheduler`` with the dependencies
  they want to observe.

* **ThreadPoolExecutor for sync work.** ``AsyncIOScheduler``'s default
  executor is the asyncio loop — synchronous DB or file I/O in a job
  would block the loop and freeze request handlers. We override with a
  ``concurrent.futures.ThreadPoolExecutor(max_workers=4)`` and route
  **sync** jobs through ``executor="default"`` (B0 §11.1 mitigation).
  Async jobs (``IngestionCycleJob``) are registered with the default
  executor (the asyncio loop itself) — this is the explicit
  ``async def`` registered-callable contract that determines
  APScheduler routing.

* **Single-worker assumption.** This scheduler runs **in-process**.
  Multi-worker deployments (e.g. uvicorn ``--workers N``) would start
  ``N`` schedulers; the operator must run Clay single-worker or accept
  that background jobs run multiple times. Out of scope for Wave B
  (would need leader-election).

* **Real ``session-scheduler`` status.** Pre-B3 the registry
  hard-stamped ``HEALTHY`` at import time (fake). After B3a the
  scheduler moves through ``STOPPED → HEALTHY → STOPPING → STOPPED``
  in lockstep with the underlying ``AsyncIOScheduler`` lifecycle, and
  B3b will add ``ERROR`` for tick exceptions and ``STALE`` for missed
  health ticks.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING
from datetime import UTC
from sqlalchemy.orm import sessionmaker

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.health.monitor import HealthMonitor
from clay.ingestion.service import IngestionCycleService
from clay.reliability.service import ReliabilityService
from clay.scheduler.ai_agent_job import AIAgentCycleJob
from clay.scheduler.jobs import (
    HealthTickJob,
    IngestionCycleJob,
    OpsRetentionJob,
    ReliabilityRecheckJob,
)
from clay.scheduler.provider_pool_reconcile_job import ProviderPoolReconcileJob
from clay.services.models import ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.settings.scheduler import SchedulerSettings

logger = logging.getLogger(__name__)


class ClayScheduler:
    """Synchronous facade over ``AsyncIOScheduler`` for the Clay backend.

    Public surface:

    * ``start()`` — bring up the underlying ``AsyncIOScheduler``,
      register the B3b ``health-tick`` job, the B4
      ``reliability-recheck`` job, and the B5 ``ingestion-cycle``
      job (when their respective flags + deps allow), and
      transition ``session-scheduler`` to ``HEALTHY``.
    * ``shutdown(wait=True)`` — graceful drain, transition through
      ``STOPPING`` to ``STOPPED``.
    * ``add_health_tick_job()`` — register the B3b
      ``HealthTickJob`` (idempotent thanks to
      ``replace_existing=True``). ``add_reliability_recheck_job()``
      is the B4 counterpart, ``add_ingestion_cycle_job()`` is the
      B5 counterpart — all flag-gated + dep-checked.
    * ``_run_safely()`` (sync) and ``_arun_safely()`` (async) —
      exception-safe wrappers applied to scheduled jobs. They
      share a common ``_handle_job_error()`` helper for the
      error-policy path (B3b default / B4-on-error / B5-isolated).
    """

    _SERVICE_ID = "session-scheduler"
    _HEALTH_TICK_JOB_ID = "health-tick"
    _RELIABILITY_RECHECK_JOB_ID = "reliability-recheck"
    _INGESTION_CYCLE_JOB_ID = "ingestion-cycle"
    _OPS_RETENTION_JOB_ID = "ops-retention"
    _AI_AGENT_CYCLE_JOB_ID = "ai-agent-cycle"
    _PROVIDER_POOL_RECONCILE_JOB_ID = "provider-pool-reconcile"

    def __init__(
        self,
        settings: SchedulerSettings,
        registry: ServiceRegistry,
        health_monitor: HealthMonitor,
        audit_writer: AuditWriter,
        event_bus: EventBus,
        *,
        reliability_service: ReliabilityService | None = None,
        session_factory: sessionmaker | None = None,
        ingestion_cycle_service: IngestionCycleService | None = None,
        ai_agent_cycle_job: AIAgentCycleJob | None = None,
        provider_pool_reconcile_job: ProviderPoolReconcileJob | None = None,
    ) -> None:
        """Construct the scheduler. B4 + B5 add optional kwargs.

        ``reliability_service`` + ``session_factory`` (B4),
        ``ingestion_cycle_service`` (B5), ``ai_agent_cycle_job``
        (5b-ii.2b-ii), and ``provider_pool_reconcile_job`` (S3d-2)
        are all **optional** (default ``None``) so existing tests
        that construct ``ClayScheduler`` without them keep passing
        — the flag-gated ``add_*_job()`` calls are no-ops when the
        matching dep is missing or the matching flag is ``False``.
        Production (``api/lifespan.py``) always passes when enabled.
        """
        self._settings = settings
        self._registry = registry
        self._health_monitor = health_monitor
        self._audit_writer = audit_writer
        self._event_bus = event_bus
        self._reliability_service = reliability_service
        self._session_factory = session_factory
        self._ingestion_cycle_service = ingestion_cycle_service
        self._ai_agent_cycle_job = ai_agent_cycle_job
        self._provider_pool_reconcile_job = provider_pool_reconcile_job
        self._apscheduler = AsyncIOScheduler(
            executors={
                "default": ThreadPoolExecutor(max_workers=4),
                "async": AsyncIOExecutor(),
            },
            timezone=UTC,
        )

    @property
    def is_running(self) -> bool:
        """Single source of truth: real state of the underlying
        ``AsyncIOScheduler`` (FIX-D, hardening #6).

        Returns ``True`` iff the inner scheduler's
        ``state == STATE_RUNNING`` — i.e. jobs are firing. STRICT
        equality on purpose: a paused scheduler is not ready (paused
        jobs do not run, and Clay has no legitimate pause path —
        ``.pause(`` / ``pause_job`` are not used anywhere in the
        repo). The MP2 plan recorded this property as a
        ``STATE_RUNNING`` mirror but the actual code shipped with
        a hand-maintained mirror flag, which drifted if the inner
        scheduler was stopped out of band (e.g. a crash in the
        asyncio loop, an exception in ``start()`` before the flag
        flipped, or a direct ``self._apscheduler.shutdown`` bypass).
        Drift showed as ``/health/ready`` reporting
        ``scheduler=running`` against a dead scheduler — a
        false-healthy failure of the readiness gate.
        """
        return self._apscheduler.state == STATE_RUNNING

    def start(self) -> None:
        """Start the underlying scheduler, register jobs, mark this service HEALTHY.

        B3b: ``add_health_tick_job()`` is called after
        ``apscheduler.start()`` so the first tick fires one interval
        later (B0 / B3a boot-order contract). B4:
        ``add_reliability_recheck_job()`` is called next, with its
        own flag + dep gates (Acceptance #6 / #7). B5:
        ``add_ingestion_cycle_job()`` is called last (after the
        sync jobs) — same flag + dep gates pattern, 4 deps
        (B5-specific, see Q1 in the B5 plan).

        Audit verb ``scheduler.started`` is past-tense (A6 verb-tense
        rule) and lists the **actually registered** job ids — the
        ``jobs`` list is derived from ``apscheduler.get_job()``
        lookups, not from the flag combination. This is the single
        source of truth (Q2, Emma): a misconfigured
        ``reliability_enabled=True`` + missing dep case will skip
        the registration and the audit payload will not lie about
        the missing job. B5 carries the same pattern over to the
        third job id.
        """
        self._apscheduler.start()
        self.add_health_tick_job()
        self.add_reliability_recheck_job()
        self.add_ops_retention_job()
        self.add_ingestion_cycle_job()
        self.add_ai_agent_cycle_job()
        self.add_provider_pool_reconcile_job()
        self._registry.update_status(self._SERVICE_ID, ServiceStatus.HEALTHY)
        jobs = [
            job_id
            for job_id in (
                self._HEALTH_TICK_JOB_ID,
                self._RELIABILITY_RECHECK_JOB_ID,
                self._OPS_RETENTION_JOB_ID,
                self._INGESTION_CYCLE_JOB_ID,
                self._AI_AGENT_CYCLE_JOB_ID,
                self._PROVIDER_POOL_RECONCILE_JOB_ID,
            )
            if self._apscheduler.get_job(job_id) is not None
        ]
        self._audit_writer.write(
            "scheduler.started",
            {"version": "3.11.2", "jobs": jobs},
        )

    def add_health_tick_job(self) -> None:
        """Register the B3b ``HealthTickJob`` with the underlying APScheduler.

        Job knobs (B3b acceptance):

        * ``executor="default"`` → routes through the
          ``ThreadPoolExecutor(max_workers=4)`` so the tick does not
          block the asyncio loop (B0 §11.1 / B3a).
        * ``max_instances=1`` — overlapping ticks are not allowed
          (audit-and-event ordering would become non-deterministic).
        * ``coalesce=True`` — if the scheduler falls behind (e.g.
          process suspended), missed ticks collapse into one catch-up
          tick on resume, instead of one audit flood per missed slot.
        * ``replace_existing=True`` — idempotent across
          ``start()``-after-``shutdown()`` cycles (B0 dev-mode path).
        """
        tick = HealthTickJob(
            registry=self._registry,
            health_monitor=self._health_monitor,
            audit_writer=self._audit_writer,
            event_bus=self._event_bus,
        )
        self._apscheduler.add_job(
            func=self._run_safely,
            args=[tick.run],
            trigger="interval",
            seconds=self._settings.health_tick_interval_seconds,
            id=self._HEALTH_TICK_JOB_ID,
            executor="default",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )

    def add_reliability_recheck_job(self) -> None:
        """Register the B4 ``ReliabilityRecheckJob`` (flag-gated + dep-checked).

        Three gates — in order — before registration:

        1. ``reliability_enabled`` flag (``False`` → silent skip,
           a documented operator opt-out, not a misconfiguration).
        2. ``reliability_service`` and ``session_factory`` both
           present. If either is ``None`` while the flag is ``True``,
           emit a **loud warning** (Q1, Emma) that **names the
           missing dep** — this is a misconfiguration: production
           (``lifespan.py``) always passes both, so the path is
           dev/test-only, and the log message must make the cause
           obvious without code-reading.
        3. The job is registered through ``_run_safely`` with
           ``on_error=job.on_error`` so the B4 (a) isolated error
           policy is wired in (no flip of ``session-scheduler`` to
           ``ERROR``; ``reliability.recheck_failed`` audit on the
           first failure of an episode; anti-flood via the job's
           ``_failing`` flag).
        """
        if not self._settings.reliability_enabled:
            return
        missing = [
            name
            for name, value in (
                ("reliability_service", self._reliability_service),
                ("session_factory", self._session_factory),
            )
            if value is None
        ]
        if missing:
            logger.warning(
                "clay.scheduler: reliability_enabled=True but %s is None — "
                "reliability-recheck job NOT registered (misconfiguration)",
                " and ".join(missing),
            )
            return
        job = ReliabilityRecheckJob(
            reliability_service=self._reliability_service,  # type: ignore[arg-type]
            session_factory=self._session_factory,  # type: ignore[arg-type]
            audit_writer=self._audit_writer,
            event_bus=self._event_bus,
        )
        self._apscheduler.add_job(
            func=self._run_safely,
            trigger="interval",
            seconds=self._settings.reliability_recheck_interval_seconds,
            id=self._RELIABILITY_RECHECK_JOB_ID,
            executor="default",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            args=[job.run],
            kwargs={"on_error": job.on_error},
        )

    def add_ingestion_cycle_job(self) -> None:
        """Register the B5 ``IngestionCycleJob`` (flag-gated + 3-dep-checked).

        Three gates — in order — before registration:

        1. ``ingestion_enabled`` flag (``False`` → silent skip, a
           documented operator opt-out, not a misconfiguration).
        2. All 3 C3 deps present: ``ingestion_cycle_service``,
           ``audit_writer``, ``event_bus``. ``session_factory``
           is no longer needed here — it lives inside
           ``IngestionCycleService`` (C3 refactor: session
           lifecycle is owned by the service's ``_persist``
           method, running in ``to_thread``). If any dep is
           ``None`` while the flag is ``True``, emit a **loud
           warning** (Q1) that **names the missing dep(s)**.
        3. The job is registered through ``_arun_safely``
           (NOT ``_run_safely`` — sync wrapper would not await
           the coroutine, silent no-op; Emma's fragment D
           mandatory code fix) with
           ``on_error=job.on_error`` so the B5 isolated error
           policy is wired in (no flip of ``session-scheduler``
           to ``ERROR``; ``ingestion.cycle_failed`` audit on
           the first failure of an episode; anti-flood via
           the job's ``_failing`` flag).

        Note on ``executor=`` — we **omit** it (B5 plan §Backlog
        #8). The default for ``AsyncIOScheduler`` is its own
        asyncio loop, which is what we want for the registered
        ``async def`` coroutine (the B5-specific async routing).
        """
        if not self._settings.ingestion_enabled:
            return
        missing = [
            name
            for name, value in (
                ("ingestion_cycle_service", self._ingestion_cycle_service),
                ("audit_writer", self._audit_writer),
                ("event_bus", self._event_bus),
            )
            if value is None
        ]
        if missing:
            logger.warning(
                "clay.scheduler: ingestion_enabled=True but %s is None — "
                "ingestion-cycle job NOT registered (misconfiguration)",
                " and ".join(missing),
            )
            return
        job = IngestionCycleJob(
            ingestion_service=self._ingestion_cycle_service,  # type: ignore[arg-type]
            audit_writer=self._audit_writer,
            event_bus=self._event_bus,
        )
        # 🔴 EMMA'S MANDATORY FRAGMENT D CODE FIX:
        # registered callable = ``self._arun_safely`` (async wrapper,
        # dispatches to event loop). The plan's fragment D contained
        # a stale ``self._run_safely`` (sync wrapper) which would
        # silently never await the coroutine — ingestion cycle
        # would never run. Routing matrix + text plan say
        # ``_arun_safely``; fragment D was the typo. Coding per
        # matrix, not per fragment D.
        self._apscheduler.add_job(
            func=self._arun_safely,
            trigger="interval",
            seconds=self._settings.ingestion_cycle_interval_seconds,
            id=self._INGESTION_CYCLE_JOB_ID,
            executor="async",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            args=[job.run],
            kwargs={"on_error": job.on_error},
        )

    def add_ops_retention_job(self) -> None:
        """Register the MP1 ``OpsRetentionJob`` (flag-gated + dep-checked).

        Two gates — in order — before registration:

        1. ``ops_retention_enabled`` flag (``False`` → silent skip,
           a documented operator opt-out, not a misconfiguration).
        2. ``session_factory`` present. If ``None`` while the flag
           is ``True``, emit a **loud warning** that names the
           missing dep — this is a misconfiguration in dev/test
           only; production (``lifespan.py``) always passes it.

        Registration: sync job through ``_run_safely`` →
        ``executor="default"`` (ThreadPoolExecutor). The DELETE
        operations are pure sync-DB, must NOT run on the event
        loop (C3 ruling). The session is created and closed
        entirely inside the worker thread (confirm (a)).
        """
        if not self._settings.ops_retention_enabled:
            return
        if self._session_factory is None:
            logger.warning(
                "clay.scheduler: ops_retention_enabled=True but "
                "session_factory is None — ops-retention job "
                "NOT registered (misconfiguration)",
            )
            return
        job = OpsRetentionJob(
            session_factory=self._session_factory,
            audit_writer=self._audit_writer,
        )
        self._apscheduler.add_job(
            func=self._run_safely,
            trigger="interval",
            seconds=self._settings.ops_retention_interval_seconds,
            id=self._OPS_RETENTION_JOB_ID,
            executor="default",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            args=[job.run],
            kwargs={"on_error": job.on_error},
        )

    def add_ai_agent_cycle_job(self) -> None:
        """Register the 5b-ii.2b-ii ``AIAgentCycleJob`` (flag-gated).

        Two gates:

        1. ``ai_agent_enabled`` flag (``False`` → silent skip).
           Default is ``False`` (opt-in only).
        2. ``ai_agent_cycle_job`` dep present. If ``None`` while the
           flag is ``True``, emit a loud warning naming the missing
           dep (dev/test misconfiguration; production always passes it).
        """
        if not self._settings.ai_agent_enabled:
            return
        if self._ai_agent_cycle_job is None:
            logger.warning(
                "clay.scheduler: ai_agent_enabled=True but "
                "ai_agent_cycle_job is None — ai-agent-cycle job "
                "NOT registered (misconfiguration)",
            )
            return
        job = self._ai_agent_cycle_job
        self._apscheduler.add_job(
            func=self._arun_safely,
            trigger="interval",
            seconds=self._settings.ai_agent_interval_seconds,
            id=self._AI_AGENT_CYCLE_JOB_ID,
            executor="async",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            args=[job.run_once],
        )

    def add_provider_pool_reconcile_job(self) -> None:
        """Register the S3d-2 ``ProviderPoolReconcileJob`` (flag-gated).

        Two gates:

        1. ``provider_pool_reconcile_enabled`` flag (``False`` → silent skip).
           Default is ``False`` (opt-in only).
        2. ``provider_pool_reconcile_job`` dep present. If ``None`` while the
           flag is ``True``, emit a loud warning naming the missing dep
           (dev/test misconfiguration; production passes it when enabled).
        """
        if not self._settings.provider_pool_reconcile_enabled:
            return
        if self._provider_pool_reconcile_job is None:
            logger.warning(
                "clay.scheduler: provider_pool_reconcile_enabled=True but "
                "provider_pool_reconcile_job is None — provider-pool-reconcile "
                "job NOT registered (misconfiguration)",
            )
            return
        job = self._provider_pool_reconcile_job
        self._apscheduler.add_job(
            func=self._run_safely,
            trigger="interval",
            seconds=self._settings.provider_pool_reconcile_interval_seconds,
            id=self._PROVIDER_POOL_RECONCILE_JOB_ID,
            executor="default",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            args=[job.run_once],
        )

    def _run_safely(
        self,
        job_callable: Callable[[], None],
        *,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Sync exception-safe wrapper — REGISTERED AS SYNC with APScheduler → ThreadPoolExecutor.

        Used by B3b ``HealthTickJob`` and B4
        ``ReliabilityRecheckJob``. Their sync DB-I/O MUST stay in
        the threadpool (B0 §11.1 mitigation). APScheduler routing
        is determined by the registered callable's **signature**
        (sync vs ``async def``), NOT by what it calls internally.

        On exception: delegates to ``_handle_job_error`` for the
        shared error-policy path (B3b default / B4 ``on_error``).
        The ``on_error=`` parameter (B4) lets a job swap in an
        isolated error policy without duplicating the wrapper.
        """
        pre_status = self._registry.get(self._SERVICE_ID).status
        try:
            job_callable()
        except Exception as exc:
            self._handle_job_error(exc, pre_status, on_error)

    async def _arun_safely(
        self,
        job_callable: Callable[[], Awaitable[None]],
        *,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Async exception-safe wrapper — REGISTERED AS COROUTINE with APScheduler → event loop.

        Used by B5 ``IngestionCycleJob``. The registered callable
        is an ``async def`` coroutine; APScheduler sees the
        coroutine function's signature and dispatches to its own
        event loop (the default executor for ``AsyncIOScheduler``).
        The body mirrors ``POST /ingestion/run`` 1:1 (same
        sync-DB on loop that the manual route does in production
        today, per Emma's [MED-A] ratification).

        On exception: delegates to ``_handle_job_error`` (the same
        helper ``_run_safely`` uses) so the B3b default /
        B4-on-error / B5-isolated error policies live in one
        place, with no duplication.

        Why a separate wrapper, not one shared wrapper with
        ``inspect.isawaitable``? The registered callable's
        signature is what determines APScheduler routing. A
        single ``async def`` wrapper would silently move the
        B3b/B4 sync jobs to the event loop (regression).
        """
        pre_status = self._registry.get(self._SERVICE_ID).status
        try:
            await job_callable()
        except Exception as exc:
            self._handle_job_error(exc, pre_status, on_error)

    def _handle_job_error(
        self,
        exc: Exception,
        pre_status: ServiceStatus,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Shared error-policy between ``_run_safely`` (sync) and ``_arun_safely`` (async).

        Three branches:

        * ``on_error`` is provided (B4/B5 pattern, e.g.
          ``ReliabilityRecheckJob.on_error`` /
          ``IngestionCycleJob.on_error``): delegated, no
          registry mutation, no re-raise.
        * Default (B3b pattern, e.g. ``HealthTickJob``):
          ``session-scheduler`` → ``ERROR`` + audit on the
          transition only + ``logger.exception``, no re-raise.

        The anti-flood check uses the **pre-tick** status
        (captured in the wrapper before ``job_callable()``
        runs), not the post-recovery status visible after the
        exception. ``HealthTickJob.run()`` re-asserts ``HEALTHY``
        in step 3 — successful ticks would otherwise mask the
        ``ERROR → ERROR`` (anti-flood) and turn repeated
        failures into ``HEALTHY → ERROR → HEALTHY → ERROR``
        pseudo-transitions that flood the audit log.
        """
        if on_error is not None:
            # B4/B5: the job owns its error policy. We do not
            # touch ``session-scheduler`` or audit; we delegate
            # the entire path (write the job-specific audit,
            # set the job-specific ``_failing`` flag, log). The
            # exception is **not** re-raised so APScheduler
            # keeps the slot alive.
            on_error(exc)
            return
        # Default B3b path: session-scheduler goes to ERROR,
        # audit on the transition only, anti-flood.
        self._registry.update_status(
            self._SERVICE_ID,
            ServiceStatus.ERROR,
            error=str(exc),
        )
        if pre_status != ServiceStatus.ERROR:
            self._audit_writer.write(
                "service.status_changed",
                {
                    "service_id": self._SERVICE_ID,
                    "from": pre_status.value,
                    "to": ServiceStatus.ERROR.value,
                    "error": str(exc),
                },
            )
        logger.exception(
            "clay.scheduler: scheduled job raised; session-scheduler marked ERROR",
        )

    def shutdown(self, wait: bool = True) -> None:
        """Graceful shutdown — transition through STOPPING to STOPPED.

        ``wait=True`` (default) blocks until in-flight jobs complete
        (B0 / B3a invariant: no orphan tasks).
        """
        self._registry.update_status(self._SERVICE_ID, ServiceStatus.STOPPING)
        self._apscheduler.shutdown(wait=wait)
        self._registry.update_status(self._SERVICE_ID, ServiceStatus.STOPPED)
        self._audit_writer.write(
            "scheduler.stopped",
            {"wait": wait, "jobs_cleared": 0},
        )
