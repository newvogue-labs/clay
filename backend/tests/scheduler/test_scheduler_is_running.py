"""Tests for ``ClayScheduler.is_running`` property (MP2 readiness).

The property is backed by the underlying ``AsyncIOScheduler.state``
(FIX-D, hardening #6) — strict ``== STATE_RUNNING``. There is no
private mirror flag.

Note on the ``after_shutdown`` test: ``AsyncIOScheduler.shutdown()``
schedules its actual state transition to ``STATE_STOPPED`` via
``call_soon_threadsafe`` (apscheduler's ``@run_in_event_loop``), so
``state`` only flips asynchronously after ``shutdown()`` returns. The
test yields control to the event loop via ``asyncio.sleep`` so the
loop can drain the scheduled callback before we read ``is_running``.
This is an apscheduler design quirk, not a Clay behaviour — the
pre-FIX-D mirror flag masked it by flipping synchronously, but it
silently disagreed with the real scheduler state.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.health.monitor import HealthMonitor
from clay.scheduler.service import ClayScheduler
from clay.services.models import ServiceCriticality
from clay.services.registry import ServiceRegistry
from clay.settings.scheduler import SchedulerSettings


def _make_registry_with_session_scheduler() -> ServiceRegistry:
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
    settings: SchedulerSettings | None = None,
) -> ClayScheduler:
    registry = _make_registry_with_session_scheduler()
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    health_monitor = HealthMonitor(registry, stale_after_seconds=60)
    if settings is None:
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
        reliability_service=None,
        session_factory=None,
        ingestion_cycle_service=None,
    )


@pytest.mark.anyio
async def test_is_running_true_after_start(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)
    scheduler.start()
    try:
        assert scheduler.is_running is True
    finally:
        scheduler.shutdown(wait=True)


@pytest.mark.anyio
async def test_is_running_false_before_start(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)
    assert scheduler.is_running is False


@pytest.mark.anyio
async def test_is_running_false_after_shutdown(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)
    scheduler.start()
    scheduler.shutdown(wait=True)
    # AsyncIOScheduler.shutdown() schedules the state transition in
    # the event loop; yield to let it flush before reading.
    await asyncio.sleep(0.1)
    assert scheduler.is_running is False
