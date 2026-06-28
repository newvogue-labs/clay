"""Persistence tests for ``ReliabilityService`` reliability_state (Slice A5).

The ``ReliabilityService`` has a single persistence contract:
``recheck`` writes the new ``last_rechecked_at`` to the
``ops.reliability_state`` singleton row, and a brand-new service on
restart restores it.

Contracts exercised:

- **First-boot:** an empty DB is seeded with a ``reliability_state``
  singleton row (id=1, ``last_rechecked_at`` is ``None``) on the
  first ``ReliabilityService`` construction with a ``session_factory``.
- **Restart-survival + tz-aware:** ``recheck`` writes a UTC-aware
  ``datetime``, a process restart restores it, and the value stays
  tz-aware through SQLite (A2.5 invariant).
- **Write-through:** the in-memory ``_last_rechecked_at`` and the DB
  row are kept consistent via ``ReliabilityStateRepository.save``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.settings.ingestion import IngestionSettings
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.control_center.service import ControlCenterService
from clay.db.models_ops import ReliabilityState
from clay.db.repositories_runtime_state import ReliabilityStateRepository
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.reliability.service import ReliabilityService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor
from clay.session_control.service import SessionControlService
from clay.session_review.service import SessionReviewService
from clay.signal_engine.service import SignalEngineService
from clay.validation_lab.service import ValidationLabService
from clay.workspace.service import WorkspaceService


def build_service(session_factory: sessionmaker, tmp_path: Path) -> ReliabilityService:
    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    registry.register(
        service_id="session-scheduler",
        service_type="scheduler",
        criticality=ServiceCriticality.IMPORTANT,
        startup_policy="always-on",
    )
    registry.update_status("session-scheduler", ServiceStatus.HEALTHY)
    registry.register(
        service_id="pair-scanner",
        service_type="worker",
        criticality=ServiceCriticality.OPTIONAL,
        startup_policy="on-demand",
    )
    registry.update_status("pair-scanner", ServiceStatus.STOPPED)

    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    config_loader = ConfigLoader(
        XdgPaths(
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
            state_dir=tmp_path / "state",
            cache_dir=tmp_path / "cache",
        )
    )
    config_loader.ensure_default_configs()
    config_loader.load_all()
    audit_writer = AuditWriter(config_loader.paths.state_dir)
    event_bus = EventBus()
    supervisor = ProcessSupervisor(registry)

    ai_control_service = AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )
    signal_engine_service = SignalEngineService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        ai_control_service=ai_control_service,
    )
    workspace_service = WorkspaceService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        signal_engine_service=signal_engine_service,
        session_factory=session_factory,
    )
    session_control_service = SessionControlService(
        runtime_manager=runtime_manager,
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
        config_loader=ConfigLoader(),
    )
    demo_trading_service = DemoTradingService(
        session_control_service=session_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    session_review_service = SessionReviewService(
        audit_writer=audit_writer,
        event_bus=event_bus,
        ai_control_service=ai_control_service,
    )
    validation_lab_service = ValidationLabService(
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        session_review_service=session_review_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )
    control_center_service = ControlCenterService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        supervisor=supervisor,
        config_loader=config_loader,
        audit_writer=audit_writer,
        ingestion_settings=IngestionSettings(),
    )

    return ReliabilityService(
        control_center_service=control_center_service,
        ai_control_service=ai_control_service,
        demo_trading_service=demo_trading_service,
        session_review_service=session_review_service,
        validation_lab_service=validation_lab_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )


# === First-boot


def test_first_boot_creates_empty_reliability_state_row(
    sqlite_session_factory, tmp_path: Path
) -> None:
    build_service(sqlite_session_factory, tmp_path)

    with sqlite_session_factory() as session:
        repo = ReliabilityStateRepository(session)
        row = repo.read()
        assert row is not None
        assert row.id == 1
        assert row.last_rechecked_at is None


def test_first_boot_persists_reliability_state_via_get_or_create(
    sqlite_session_factory, tmp_path: Path
) -> None:
    build_service(sqlite_session_factory, tmp_path)

    with sqlite_session_factory() as session:
        # Exactly one row exists.
        assert session.scalar(select(func.count()).select_from(ReliabilityState)) == 1


# === Restart-survival: recheck


def test_restart_survives_recheck(
    sqlite_session_factory, tmp_path: Path, db_session
) -> None:
    service1 = build_service(sqlite_session_factory, tmp_path)
    before = datetime.now(UTC) - timedelta(seconds=1)
    service1.recheck(db_session)
    after = datetime.now(UTC) + timedelta(seconds=1)
    db_session.commit()

    # In-memory timestamp is within the expected window.
    assert service1._last_rechecked_at is not None
    assert before <= service1._last_rechecked_at <= after

    # DB row reflects the same timestamp.
    with sqlite_session_factory() as session:
        row = ReliabilityStateRepository(session).read()
        assert row is not None
        assert row.last_rechecked_at == service1._last_rechecked_at

    # Brand-new service instance → simulates a process restart.
    service2 = build_service(sqlite_session_factory, tmp_path)
    assert service2._last_rechecked_at is not None
    # A2.5: round-trip preserves tzinfo on SQLite.
    assert service2._last_rechecked_at.tzinfo is not None
    assert service2._last_rechecked_at == service1._last_rechecked_at


# === typing sanity


def test_typing_reliability_state_columns() -> None:
    from clay.db.models_ops import ReliabilityState as Model

    expected = {"id", "last_rechecked_at"}
    assert expected.issubset(set(Model.__annotations__.keys()))
    assert cast(type, Model) is ReliabilityState
