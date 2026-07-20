"""Tests for ClayScheduler (B3a scaffold + B3b health-tick registration).

APScheduler 3.x ``AsyncIOScheduler.start()`` calls
``asyncio.get_running_loop()`` and crashes if there is no running
event loop in the current thread. All scheduler-lifecycle tests
must therefore be ``@pytest.mark.anyio async def`` so the loop is
present.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.health.monitor import HealthMonitor
from clay.reliability.service import ReliabilityService
from clay.scheduler.provider_pool_reconcile_job import ProviderPoolReconcileJob
from clay.scheduler.service import ClayScheduler
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.settings.scheduler import SchedulerSettings


def _read_audit_events(audit_writer: AuditWriter) -> list[dict[str, Any]]:
    """Read the JSONL audit log and return parsed events (test helper)."""
    with audit_writer.path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _make_registry_with_session_scheduler() -> ServiceRegistry:
    """Minimal registry with ``session-scheduler`` registered as
    ``STOPPED`` (the B3a real initial state — pre-B3 used to be a
    fake ``HEALTHY`` stamp).
    """
    registry = ServiceRegistry()
    registry.register(
        service_id="session-scheduler",
        service_type="scheduler",
        criticality=ServiceCriticality.IMPORTANT,
        startup_policy="always-on",
    )
    return registry


def _make_scheduler(
    tmp_path: Path,
    *,
    settings: SchedulerSettings | None = None,
    reliability_service: ReliabilityService | None = None,
    session_factory: Any = None,
    ingestion_cycle_service: Any = None,
    provider_pool_reconcile_job: ProviderPoolReconcileJob | None = None,
    reconcile_job: Any = None,
) -> tuple[
    ClayScheduler,
    ServiceRegistry,
    AuditWriter,
    EventBus,
    HealthMonitor,
    ReliabilityService | None,
    Any,
]:
    """Build a ``ClayScheduler`` for B3a/B3b + B4 + B5 + S3d-2 tests.

    Returns a 7-tuple. The first 5 elements are the legacy B3a/B3b
    shape (so the existing tests can keep their 5-unpack); the last
    two are the B4 ``reliability_service`` and ``session_factory``
    dependencies (default ``None`` — B4 will skip registering the
    reliability-recheck job when they are missing). The B5
    ``ingestion_cycle_service`` is a constructor-only kwarg (also
    ``None`` by default for B3a/B3b/B4 tests); the B5 tests pass a
    ``MagicMock`` to drive the registration path.
    ``provider_pool_reconcile_job`` (S3d-2) follows the same pattern.
    """
    registry = _make_registry_with_session_scheduler()
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    health_monitor = HealthMonitor(registry, stale_after_seconds=60)
    if settings is None:
        settings = SchedulerSettings(
            enabled=True,
            ops_retention_enabled=False,
        )
    scheduler = ClayScheduler(
        settings=settings,
        registry=registry,
        health_monitor=health_monitor,
        audit_writer=audit_writer,
        event_bus=event_bus,
        reliability_service=reliability_service,
        session_factory=session_factory,
        ingestion_cycle_service=ingestion_cycle_service,
        provider_pool_reconcile_job=provider_pool_reconcile_job,
        reconcile_job=reconcile_job,
    )
    return (
        scheduler,
        registry,
        audit_writer,
        event_bus,
        health_monitor,
        reliability_service,
        session_factory,
    )


@pytest.mark.anyio
async def test_lifecycle_start_stop(tmp_path: Path) -> None:
    """start() → HEALTHY + audit; shutdown(wait=True) → STOPPED + audit.

    Asserts the B3a real-status contract: ``session-scheduler`` walks
    through ``STOPPED → HEALTHY → STOPPING → STOPPED`` in lockstep
    with the underlying ``AsyncIOScheduler`` lifecycle (not the
    pre-B3 fake-HEALTHY stamp). Two audit events with past-tense
    verbs (A6 verb-tense rule).
    """
    scheduler, registry, audit_writer, _event_bus, *_ = _make_scheduler(tmp_path)
    assert registry.get("session-scheduler").status is ServiceStatus.STOPPED

    scheduler.start()
    assert registry.get("session-scheduler").status is ServiceStatus.HEALTHY

    scheduler.shutdown(wait=True)
    assert registry.get("session-scheduler").status is ServiceStatus.STOPPED

    events = _read_audit_events(audit_writer)
    verbs = [e["event_type"] for e in events]
    assert "scheduler.started" in verbs
    assert "scheduler.stopped" in verbs
    started = next(e for e in events if e["event_type"] == "scheduler.started")
    # B3b: ``add_health_tick_job()`` is called by ``start()`` after
    # ``apscheduler.start()``, so the ``jobs`` list is no longer
    # empty — it contains the registered health-tick job id.
    assert started["payload"]["jobs"] == ["health-tick"]


@pytest.mark.anyio
async def test_constructor_accepts_disabled_settings(tmp_path: Path) -> None:
    """``SchedulerSettings(enabled=False)`` is a constructor-level
    no-op — ``ClayScheduler`` is built successfully, the gate lives
    in ``lifespan.py``, not in the scheduler. The corresponding
    "skip-start" behavior is tested in
    ``tests/api/test_lifespan.py::test_lifespan_skips_scheduler_when_disabled``.
    """
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=SchedulerSettings(enabled=False),
    )
    assert scheduler is not None
    assert scheduler._settings.enabled is False


@pytest.mark.anyio
async def test_session_scheduler_real_status_walks_lifecycle(tmp_path: Path) -> None:
    """Full lifecycle walk: STOPPED → HEALTHY → STOPPING → STOPPED.

    Replaces the pre-B3 fake-HEALTHY at-import stamp with a real
    status that mirrors the ``AsyncIOScheduler`` lifecycle.
    """
    scheduler, registry, *_ = _make_scheduler(tmp_path)
    history: list[ServiceStatus] = [registry.get("session-scheduler").status]

    scheduler.start()
    history.append(registry.get("session-scheduler").status)

    scheduler.shutdown(wait=True)
    history.append(registry.get("session-scheduler").status)

    assert history == [
        ServiceStatus.STOPPED,
        ServiceStatus.HEALTHY,
        ServiceStatus.STOPPED,
    ]


@pytest.mark.anyio
async def test_health_tick_job_registered(tmp_path: Path) -> None:
    """B3b: ``start()`` registers ``health-tick`` with the right knobs.

    Acceptance: ``apscheduler.get_job("health-tick")`` exists, the
    executor is ``"default"`` (ThreadPoolExecutor, B0 §11.1
    mitigation), ``max_instances == 1`` (no overlapping ticks),
    ``coalesce is True`` (catch-up ticks collapse), and the
    trigger interval matches ``health_tick_interval_seconds``.
    """
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=SchedulerSettings(health_tick_interval_seconds=15),
    )
    scheduler.start()

    try:
        job = scheduler._apscheduler.get_job("health-tick")
        assert job is not None
        assert job.executor == "default"
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.trigger.interval.total_seconds() == 15
    finally:
        scheduler.shutdown(wait=True)


# === B4 — reliability-recheck job registration + scheduler.started payload ===
#
# Q1 (Emma): ``reliability_enabled=True`` with ``reliability_service`` or
# ``session_factory`` set to ``None`` is a misconfiguration. The scheduler
# must log a warning that **names the missing dep** and skip registration.
#
# Q2 (Emma): the ``scheduler.started`` payload must list jobs that are
# actually registered (via ``apscheduler.get_job()``), not jobs that
# would have been registered by the flag combination. Single source of
# truth = APScheduler's ``get_job()`` lookup.


@pytest.mark.anyio
async def test_reliability_recheck_registered_when_enabled(tmp_path: Path) -> None:
    """``reliability_enabled=True`` + deps present → ``reliability-recheck`` job registered.

    Acceptance #6 / #7. The job is registered with the same knobs as
    ``health-tick`` (B3b acceptance): ``executor="default"``,
    ``max_instances=1``, ``coalesce=True``, ``replace_existing=True``,
    plus the B4 ``on_error`` policy passed via APScheduler ``kwargs``.
    """
    settings = SchedulerSettings(
        enabled=True,
        reliability_enabled=True,
        reliability_recheck_interval_seconds=120,
    )
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        reliability_service=MagicMock(),
        session_factory=MagicMock(),
    )
    scheduler.start()

    try:
        job = scheduler._apscheduler.get_job("reliability-recheck")
        assert job is not None
        assert job.executor == "default"
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.trigger.interval.total_seconds() == 120
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_reliability_recheck_not_registered_when_disabled(
    tmp_path: Path,
) -> None:
    """``reliability_enabled=False`` → no ``reliability-recheck``; ``health-tick`` still there.

    Acceptance #6 partial: the disable flag is honoured even when
    the dependencies are wired in (the test passes
    ``MagicMock`` for both — the flag is the deciding factor).
    """
    settings = SchedulerSettings(enabled=True, reliability_enabled=False)
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        reliability_service=MagicMock(),
        session_factory=MagicMock(),
    )
    scheduler.start()

    try:
        assert scheduler._apscheduler.get_job("reliability-recheck") is None
        assert scheduler._apscheduler.get_job("health-tick") is not None
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_scheduler_started_jobs_reflects_actual_registration(
    tmp_path: Path,
) -> None:
    """``scheduler.started.jobs`` mirrors APScheduler's actual registrations, not flag intent.

    Q2 (Emma): single source of truth = ``apscheduler.get_job()`` lookup.
    This prevents the "loud-warning + skip" case from emitting a
    ``scheduler.started`` payload that *claims*
    ``reliability-recheck`` is registered when it is not.
    """
    settings = SchedulerSettings(
        enabled=True,
        reliability_enabled=True,
        ops_retention_enabled=False,
    )
    scheduler, _, audit_writer, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        reliability_service=MagicMock(),
        session_factory=MagicMock(),
    )
    scheduler.start()

    try:
        started = next(
            e
            for e in _read_audit_events(audit_writer)
            if e["event_type"] == "scheduler.started"
        )
        assert started["payload"]["jobs"] == [
            "health-tick",
            "reliability-recheck",
        ]
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_scheduler_started_jobs_omits_reliability_when_disabled(
    tmp_path: Path,
) -> None:
    """``reliability_enabled=False`` → ``scheduler.started.jobs`` = ``["health-tick"]``."""
    settings = SchedulerSettings(enabled=True, reliability_enabled=False)
    scheduler, _, audit_writer, *_ = _make_scheduler(tmp_path, settings=settings)
    scheduler.start()

    try:
        started = next(
            e
            for e in _read_audit_events(audit_writer)
            if e["event_type"] == "scheduler.started"
        )
        assert started["payload"]["jobs"] == ["health-tick"]
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_loud_warning_when_reliability_enabled_but_deps_missing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``reliability_enabled=True`` + ``reliability_service is None`` → warning names dep + skip.

    Q1 (Emma): the warning is **loud** (``logging.WARNING``) and
    **names the missing dep** so an operator can diagnose the
    misconfiguration from the log alone. In production ``lifespan``
    always passes both deps, so this path is dev/test-only.
    """
    settings = SchedulerSettings(enabled=True, reliability_enabled=True)
    # reliability_service and session_factory default to None — the
    # misconfiguration Q1 targets.
    scheduler, *_ = _make_scheduler(tmp_path, settings=settings)
    _logger = logging.getLogger("clay.scheduler.service")
    _logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="clay.scheduler.service"):
            scheduler.start()

        # Job not registered.
        assert scheduler._apscheduler.get_job("reliability-recheck") is None
        # Loud warning present.
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and r.name == "clay.scheduler.service"
        ]
        assert len(warnings) >= 1
        # Names at least one of the missing deps.
        warning_text = " ".join(r.getMessage() for r in warnings)
        assert (
            "session_factory" in warning_text or "reliability_service" in warning_text
        )
        # And signals it is a misconfiguration, not a normal skip.
        assert "NOT registered" in warning_text or "misconfiguration" in warning_text
    finally:
        _logger.removeHandler(caplog.handler)
        scheduler.shutdown(wait=True)


# === B5 — ingestion-cycle job registration + scheduler.started payload (3 ids) ===
#
# B5 adds the third scheduler-driven job, registered through the
# **async** wrapper ``_arun_safely`` (not ``_run_safely`` — sync
# wrapper would NOT await ``IngestionCycleJob.run()``'s coroutine,
# silent no-op, Emma's mandatory fragment D fix). The flag is
# ``ingestion_enabled`` (env ``CLAY_SCHEDULER_INGESTION_ENABLED``),
# independent from ``enabled`` and ``reliability_enabled``.


@pytest.mark.anyio
async def test_ingestion_cycle_registered_when_enabled(tmp_path: Path) -> None:
    """``ingestion_enabled=True`` + 4 deps → ``ingestion-cycle`` job registered.

    The job is registered with the B3b knobs (``max_instances=1``,
    ``coalesce=True``, ``replace_existing=True``) and the B5-specific
    async routing: APScheduler sees the registered callable's
    ``async def`` signature and dispatches to the event loop
    (``executor=None`` is the default; we omit it to make the
    intent explicit in the diff).
    """
    settings = SchedulerSettings(
        enabled=True,
        ingestion_enabled=True,
        ingestion_cycle_interval_seconds=120,
    )
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        ingestion_cycle_service=MagicMock(),
        session_factory=MagicMock(),
    )
    scheduler.start()

    try:
        job = scheduler._apscheduler.get_job("ingestion-cycle")
        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.trigger.interval.total_seconds() == 120
        # The async wrapper is the registered callable — this is the
        # routing contract (B5 plan §"Routing matrix"). Without
        # ``async def`` APScheduler would route to the threadpool
        # and ``IngestionCycleJob.run()``'s coroutine would never
        # be awaited. Compare by qualified name (bound method
        # identity is fragile across APScheduler's internal
        # ``Job`` wrappers — the wrapped function reference is
        # the same name even if the bound-method object differs).
        assert job.func.__qualname__ == scheduler._arun_safely.__qualname__  # noqa: SLF001
        assert job.func.__name__ == "_arun_safely"
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_ingestion_cycle_not_registered_when_disabled(
    tmp_path: Path,
) -> None:
    """``ingestion_enabled=False`` → no ``ingestion-cycle``; health-tick stays."""
    settings = SchedulerSettings(
        enabled=True,
        ingestion_enabled=False,
        ops_retention_enabled=False,
    )
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        ingestion_cycle_service=MagicMock(),
        session_factory=MagicMock(),
    )
    scheduler.start()

    try:
        assert scheduler._apscheduler.get_job("ingestion-cycle") is None
        assert scheduler._apscheduler.get_job("health-tick") is not None
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_scheduler_started_jobs_3_ids_reflects_actual_registration(
    tmp_path: Path,
) -> None:
    """``scheduler.started.jobs`` lists 3 ids when all flags + deps are on.

    Q2 (Emma, carried forward from B4): single source of truth =
    ``apscheduler.get_job()``. All three flags on, all deps
    present → ``["health-tick", "reliability-recheck",
    "ingestion-cycle"]`` in that order.
    """
    settings = SchedulerSettings(
        enabled=True,
        reliability_enabled=True,
        ingestion_enabled=True,
        ops_retention_enabled=False,
    )
    scheduler, _, audit_writer, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        reliability_service=MagicMock(),
        session_factory=MagicMock(),
        ingestion_cycle_service=MagicMock(),
    )
    scheduler.start()

    try:
        started = next(
            e
            for e in _read_audit_events(audit_writer)
            if e["event_type"] == "scheduler.started"
        )
        assert started["payload"]["jobs"] == [
            "health-tick",
            "reliability-recheck",
            "ingestion-cycle",
        ]
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_loud_warning_when_ingestion_enabled_but_deps_missing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``ingestion_enabled=True`` + missing dep → warning names the dep + skip.

    Q1 (Emma, applied in B5 with 4 deps not 2): the warning is
    ``logging.WARNING`` and names **at least one** missing dep so an
    operator can diagnose the misconfiguration from the log alone.
    Production ``lifespan`` always passes all 4, so this path is
    dev/test-only.
    """
    settings = SchedulerSettings(enabled=True, ingestion_enabled=True)
    # ingestion_cycle_service defaults to None — the misconfiguration Q1 targets.
    scheduler, *_ = _make_scheduler(tmp_path, settings=settings)
    _logger = logging.getLogger("clay.scheduler.service")
    _logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="clay.scheduler.service"):
            scheduler.start()

        assert scheduler._apscheduler.get_job("ingestion-cycle") is None
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and r.name == "clay.scheduler.service"
        ]
        assert len(warnings) >= 1
        warning_text = " ".join(r.getMessage() for r in warnings)
        # Names the B5-specific dep + the shared ones.
        assert (
            "ingestion_cycle_service" in warning_text
            or "session_factory" in warning_text
        )
        assert "NOT registered" in warning_text or "misconfiguration" in warning_text
    finally:
        _logger.removeHandler(caplog.handler)
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_T1_ingestion_cycle_has_async_executor(tmp_path: Path) -> None:
    """T1: ``ingestion-cycle`` registered with ``executor="async"``.

    Sync jobs (``health-tick``, ``reliability-recheck``) keep
    ``executor="default"`` (ThreadPoolExecutor).
    """
    settings = SchedulerSettings(
        enabled=True,
        reliability_enabled=True,
        ingestion_enabled=True,
    )
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        reliability_service=MagicMock(),
        session_factory=MagicMock(),
        ingestion_cycle_service=MagicMock(),
    )
    scheduler.start()

    try:
        ingestion_job = scheduler._apscheduler.get_job("ingestion-cycle")
        health_job = scheduler._apscheduler.get_job("health-tick")
        reliability_job = scheduler._apscheduler.get_job("reliability-recheck")

        assert ingestion_job is not None
        assert health_job is not None
        assert reliability_job is not None

        assert ingestion_job.executor == "async"
        assert health_job.executor == "default"
        assert reliability_job.executor == "default"
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_T2_ingestion_cycle_actually_executes_on_scheduler(
    tmp_path: Path,
) -> None:
    """T2: scheduler-driven ingestion cycle actually runs (no ``coroutine never awaited``).

    Previously the async ``_arun_safely`` was submitted to the sync
    ThreadPoolExecutor (``"default"``) and silently dropped. After
    D4-FIX, it uses ``AsyncIOExecutor`` (``"async"``) and the
    coroutine is awaited.

    We prove this by registering with a short interval, running for
    a few ticks, and asserting the service's ``run_once`` was called.
    """
    from dataclasses import dataclass, field

    @dataclass
    class _FakeRunSummary:
        incidents: list = field(default_factory=list)
        freshness_state_transitions: int = 0

    class _FakeIngestionCycleService:
        """Minimal fake that works with ``IngestionCycleJob``.

        MagicMock is unsuitable because:
        - ``is_running`` (property) is truthy by default →
          always short-circuits the tick.
        - ``run_once`` (async) returns a non-awaitable →
          raises TypeError inside the scheduler's ``await``.
        """

        is_running = False
        call_count = 0

        async def run_once(self, *, emit: bool = False) -> _FakeRunSummary:  # noqa: ARG002
            self.call_count += 1
            return _FakeRunSummary()

        def emit_cycle_events(self, summary: _FakeRunSummary) -> None:
            pass

    ingestion_service = _FakeIngestionCycleService()
    settings = SchedulerSettings(
        enabled=True,
        ingestion_enabled=True,
        ingestion_cycle_interval_seconds=1,
        ops_retention_enabled=False,
    )
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        ingestion_cycle_service=ingestion_service,
        session_factory=MagicMock(),
    )
    scheduler.start()

    try:
        await asyncio.sleep(2.5)
        assert ingestion_service.call_count >= 1, (
            f"Expected >=1 call to run_once, got {ingestion_service.call_count}"
        )
    finally:
        scheduler.shutdown(wait=True)


# === S3d-2 — provider-pool-reconcile job registration + scheduler.started payload ===


@pytest.mark.anyio
async def test_provider_pool_reconcile_registered_when_enabled(
    tmp_path: Path,
) -> None:
    """``provider_pool_reconcile_enabled=True`` + dep present → ``provider-pool-reconcile`` job registered.

    Job knobs: ``executor="default"`` (sync on ThreadPoolExecutor),
    ``max_instances=1``, ``coalesce=True``, ``replace_existing=True``.
    Interval matches ``provider_pool_reconcile_interval_seconds`` (default 300).
    """
    settings = SchedulerSettings(
        enabled=True,
        provider_pool_reconcile_enabled=True,
        provider_pool_reconcile_interval_seconds=120,
    )
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        provider_pool_reconcile_job=MagicMock(spec=ProviderPoolReconcileJob),
    )
    scheduler.start()

    try:
        job = scheduler._apscheduler.get_job("provider-pool-reconcile")
        assert job is not None
        assert job.executor == "default"
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.trigger.interval.total_seconds() == 120
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_provider_pool_reconcile_not_registered_when_disabled(
    tmp_path: Path,
) -> None:
    """``provider_pool_reconcile_enabled=False`` → no job; health-tick still there."""
    settings = SchedulerSettings(
        enabled=True,
        provider_pool_reconcile_enabled=False,
    )
    scheduler, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        provider_pool_reconcile_job=MagicMock(spec=ProviderPoolReconcileJob),
    )
    scheduler.start()

    try:
        assert scheduler._apscheduler.get_job("provider-pool-reconcile") is None
        assert scheduler._apscheduler.get_job("health-tick") is not None
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_provider_pool_reconcile_not_registered_when_dep_missing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``provider_pool_reconcile_enabled=True`` + job is ``None`` → warning + skip."""
    settings = SchedulerSettings(
        enabled=True,
        provider_pool_reconcile_enabled=True,
    )
    # provider_pool_reconcile_job defaults to None — the misconfiguration path.
    scheduler, *_ = _make_scheduler(tmp_path, settings=settings)
    _logger = logging.getLogger("clay.scheduler.service")
    _logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="clay.scheduler.service"):
            scheduler.start()

        assert scheduler._apscheduler.get_job("provider-pool-reconcile") is None
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and r.name == "clay.scheduler.service"
        ]
        assert len(warnings) >= 1
        warning_text = " ".join(r.getMessage() for r in warnings)
        assert "provider_pool_reconcile_job" in warning_text
        assert "NOT registered" in warning_text or "misconfiguration" in warning_text
    finally:
        _logger.removeHandler(caplog.handler)
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_scheduler_started_jobs_includes_provider_pool_reconcile(
    tmp_path: Path,
) -> None:
    """``scheduler.started.jobs`` includes ``provider-pool-reconcile`` when enabled."""
    settings = SchedulerSettings(
        enabled=True,
        provider_pool_reconcile_enabled=True,
    )
    scheduler, _, audit_writer, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        provider_pool_reconcile_job=MagicMock(spec=ProviderPoolReconcileJob),
    )
    scheduler.start()

    try:
        started = next(
            e
            for e in _read_audit_events(audit_writer)
            if e["event_type"] == "scheduler.started"
        )
        assert "provider-pool-reconcile" in started["payload"]["jobs"]
    finally:
        scheduler.shutdown(wait=True)


# ── D-12c: reconcile-cycle dormant + enabled ─────────────────────────────


@pytest.mark.anyio
async def test_reconcile_cycle_dormant_when_disabled(tmp_path: Path) -> None:
    """D-12c: reconcile_enabled=False → job NOT registered, no audit."""
    settings = SchedulerSettings(
        enabled=True,
        reconcile_enabled=False,
    )
    scheduler, _, audit_writer, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
    )
    scheduler.start()

    try:
        assert scheduler._apscheduler.get_job("reconcile-cycle") is None
        started = next(
            e
            for e in _read_audit_events(audit_writer)
            if e["event_type"] == "scheduler.started"
        )
        assert "reconcile-cycle" not in started["payload"]["jobs"]
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_reconcile_cycle_enabled_registers_job(tmp_path: Path) -> None:
    """D-12c: reconcile_enabled=True + job dep → registered."""
    from clay.scheduler.reconcile_job import OrderReconcileJob

    settings = SchedulerSettings(
        enabled=True,
        reconcile_enabled=True,
    )
    mock_job = MagicMock(spec=OrderReconcileJob)
    scheduler, _, audit_writer, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        reconcile_job=mock_job,
    )
    scheduler.start()

    try:
        assert scheduler._apscheduler.get_job("reconcile-cycle") is not None
        started = next(
            e
            for e in _read_audit_events(audit_writer)
            if e["event_type"] == "scheduler.started"
        )
        assert "reconcile-cycle" in started["payload"]["jobs"]
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_reconcile_cycle_enabled_no_dep_loud_skip(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-12c: reconcile_enabled=True but job=None → warning + no registration."""
    import logging as _logging

    settings = SchedulerSettings(
        enabled=True,
        reconcile_enabled=True,
    )
    scheduler, _, audit_writer, *_ = _make_scheduler(
        tmp_path,
        settings=settings,
        reconcile_job=None,
    )
    _logger = _logging.getLogger("clay.scheduler.service")
    _logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(_logging.WARNING, logger="clay.scheduler.service"):
            scheduler.start()

        assert scheduler._apscheduler.get_job("reconcile-cycle") is None
        assert any("reconcile_job is None" in r.message for r in caplog.records)
    finally:
        scheduler.shutdown(wait=True)
        _logger.removeHandler(caplog.handler)
