"""Tests for ``ClayScheduler.is_running`` property (MP2 readiness)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.health.monitor import HealthMonitor
from clay.scheduler.service import ClayScheduler
from clay.services.models import ServiceCriticality, ServiceStatus
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
    assert scheduler.is_running is False
