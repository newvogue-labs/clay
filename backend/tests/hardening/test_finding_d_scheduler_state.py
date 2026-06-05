"""Finding D: ``ClayScheduler.is_running`` = real apscheduler state (hardening #6).

The MP2 plan recorded ``is_running`` as a property backed by
``apscheduler.schedulers.base.STATE_RUNNING`` — but the actual code
shipped with a hand-maintained ``self._running`` mirror flag. If the
underlying ``AsyncIOScheduler`` stopped out of band (asyncio-loop
crash, direct ``_apscheduler.shutdown`` bypass, exception in
``start()`` before the flag flipped), the mirror stayed ``True`` and
``/health/ready`` reported ``scheduler=running`` against a dead
scheduler — a false-healthy failure of the readiness gate.

Slice FIX-D removes the mirror entirely. ``is_running`` now reads
the live ``self._apscheduler.state`` — single source of truth.

Two tests:

1. **drift-regression** — the bug itself: start the scheduler, then
   stop the inner apscheduler in a way that bypasses the facade
   (``scheduler._apscheduler.shutdown(wait=False)``). Yield to the
   event loop so the scheduled ``_shutdown`` callback runs, then
   assert ``is_running is False``. Pre-fix this returned ``True``
   because the mirror was not updated by the bypass.

2. **readiness-проброс** — same drift, but observed through
   ``/health/ready``: ``app.state.scheduler = scheduler``,
   start, bypass-shutdown, GET ``/health/ready`` → 503 with
   ``checks.scheduler == "stopped"``. This is the production
   failure mode the bug would have caused.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from clay.api.main import create_app
from clay.api.routes import health as health_module
from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.health.monitor import HealthMonitor
from clay.scheduler.service import ClayScheduler
from clay.services.models import ServiceCriticality
from clay.services.registry import ServiceRegistry
from clay.settings.scheduler import SchedulerSettings


# =========================================================================
#  helpers
# =========================================================================


def _make_scheduler(tmp_path: Path) -> ClayScheduler:
    registry = ServiceRegistry()
    registry.register(
        service_id="session-scheduler",
        service_type="scheduler",
        criticality=ServiceCriticality.IMPORTANT,
        startup_policy="always-on",
    )
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    health_monitor = HealthMonitor(registry, stale_after_seconds=60)
    settings = SchedulerSettings(
        enabled=True,
        ops_retention_enabled=False,
        reliability_enabled=False,
        ingestion_enabled=False,
    )
    return ClayScheduler(
        settings=settings,
        registry=registry,
        health_monitor=health_monitor,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )


# =========================================================================
#  1) drift-regression: bypass-shutdown is reflected in is_running
# =========================================================================


@pytest.mark.anyio
async def test_is_running_reflects_inner_apscheduler_shutdown(
    tmp_path: Path,
) -> None:
    """Reproduce the FIX-D bug: start the scheduler, then stop the
    inner ``AsyncIOScheduler`` in a way that bypasses the facade
    (direct ``_apscheduler.shutdown(wait=False)``). After yielding
    to the event loop so apscheduler's scheduled ``_shutdown``
    callback runs, ``is_running`` must be ``False``. Pre-fix the
    hand-maintained ``self._running`` mirror stayed ``True`` —
    that was the false-healthy readiness failure.
    """
    scheduler = _make_scheduler(tmp_path)
    scheduler.start()
    try:
        assert scheduler.is_running is True

        # Bypass the facade: stop the inner apscheduler directly.
        scheduler._apscheduler.shutdown(wait=False)
        # AsyncIOScheduler.shutdown() schedules the actual state
        # transition to STATE_STOPPED via call_soon_threadsafe.
        # Yield so the loop can drain the scheduled callback.
        for _ in range(50):
            if scheduler.is_running is False:
                break
            await asyncio.sleep(0.01)

        assert scheduler.is_running is False
    finally:
        # Best-effort facade shutdown for cleanup. is_running may
        # already be False from the bypass.
        if scheduler._apscheduler.state != 0:  # STATE_STOPPED
            scheduler.shutdown(wait=True)
            await asyncio.sleep(0.1)


# =========================================================================
#  2) readiness-проброс: /health/ready sees the dead scheduler
# =========================================================================


@pytest.mark.anyio
async def test_health_ready_503_when_inner_apscheduler_dead(
    tmp_path: Path,
) -> None:
    """Production failure mode of the FIX-D bug: ``/health/ready``
    must report ``scheduler=stopped`` (and 503) when the underlying
    apscheduler is dead — even if ``ClayScheduler.shutdown()`` was
    never called.
    """
    app = create_app()
    scheduler = _make_scheduler(tmp_path)
    scheduler.start()
    app.state.scheduler = scheduler
    app.state.started_at = datetime.now(UTC)

    # Patch DB + ingest checks to be healthy so only the scheduler
    # branch can fail this probe.
    orig_db = health_module._check_db
    orig_ingest = health_module._check_ingest_freshness

    async def _db_ok() -> bool:
        return True

    async def _ingest_ok(
        started_at: datetime | None,
        threshold: int,
    ) -> str:
        return "ok"

    health_module._check_db = _db_ok  # type: ignore[method-assign]
    health_module._check_ingest_freshness = _ingest_ok  # type: ignore[method-assign]
    try:
        # Bypass the facade: stop the inner apscheduler directly.
        scheduler._apscheduler.shutdown(wait=False)
        # Let the event loop drain the scheduled _shutdown.
        for _ in range(50):
            if scheduler.is_running is False:
                break
            await asyncio.sleep(0.01)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/health/ready")
    finally:
        health_module._check_db = orig_db  # type: ignore[method-assign]
        health_module._check_ingest_freshness = orig_ingest  # type: ignore[method-assign]
        if scheduler._apscheduler.state != 0:
            scheduler.shutdown(wait=True)
            await asyncio.sleep(0.1)

    assert response.status_code == 503
    data = response.json()
    assert data["checks"]["scheduler"] == "stopped"
    assert data["status"] == "degraded"
