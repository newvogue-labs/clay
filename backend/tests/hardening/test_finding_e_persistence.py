"""Finding E: транзакционная ``get_db_session`` (hardening #1).

Тесты персистентности для трёх сервисов + rollback:
- session_control: start_session переживает "рестарт" (dispose engine)
- ai_control: review_assignment + apply_assignment переживают рестарт
- workspace: set_focus переживает рестарт
- rollback: исключение внутри блока не оставляет изменений
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.db import Base, build_engine, build_session_factory
from clay.db.models_ops import SessionState, WorkspaceFocus
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.db.repositories_runtime_state import AIAssignmentRepository
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.settings.ingestion import IngestionSettings
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService


# =========================================================================
#  Хелперы
# =========================================================================


def _seed_session_data(session) -> None:
    now = datetime.now(UTC)
    market_repo = MarketRepository(session)
    context_repo = ContextRepository(session)
    ops_repo = OpsRepository(session)

    for symbol, close in [("BTCUSDT", 70540.0), ("SOLUSDT", 181.5)]:
        market_repo.upsert_market_bars([
            {
                "symbol": symbol,
                "timeframe": "15m",
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.985,
                "close": close,
                "volume": 260.0,
                "quote_volume": close * 260.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            }
        ])
        market_repo.upsert_freshness_status(
            symbol=symbol,
            timeframe="15m",
            source="binance_spot",
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=now - timedelta(minutes=15),
            is_stale=False,
        )

    context_repo.store_sentiment_snapshots([
        {
            "source_name": "demo_sentiment_feed",
            "symbol": "BTCUSDT",
            "sentiment_label": "bullish",
            "sentiment_score": 0.74,
            "captured_at": now - timedelta(minutes=12),
        },
        {
            "source_name": "demo_sentiment_feed",
            "symbol": "SOLUSDT",
            "sentiment_label": "bullish",
            "sentiment_score": 0.88,
            "captured_at": now - timedelta(minutes=8),
        },
    ])
    ops_repo.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )


def _build_session_control_service(
    session_factory: sessionmaker,
):
    from clay.session_control.service import SessionControlService

    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
    audit_writer = AuditWriter(config_loader.paths.state_dir)
    event_bus = EventBus()

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
    )
    return SessionControlService(
        runtime_manager=runtime_manager,
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
        config_loader=ConfigLoader(),
    )


def _build_ai_control_service(
    session_factory: sessionmaker,
) -> AIControlService:
    registry = ServiceRegistry()
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
    return AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=AuditWriter(config_loader.paths.state_dir),
        event_bus=EventBus(),
        session_factory=session_factory,
    )


def _build_workspace_service(
    session_factory: sessionmaker,
) -> WorkspaceService:
    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    config_loader = ConfigLoader()
    config_loader.ensure_default_configs()
    config_loader.load_all()
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    audit_writer = AuditWriter(config_loader.paths.state_dir)
    event_bus = EventBus()
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
    return WorkspaceService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        signal_engine_service=signal_engine_service,
        session_factory=session_factory,
    )


# =========================================================================
#  SessionControl persistence
# =========================================================================


def test_session_control_start_persists_across_restart(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'sc-test.db'}"
    settings = IngestionSettings(database_url=db_url)

    engine1 = build_engine(settings)
    Base.metadata.create_all(engine1)
    factory1 = build_session_factory(settings)

    service = _build_session_control_service(factory1)

    with factory1() as session:
        _seed_session_data(session)
        session.commit()

    with factory1() as session:
        service.start_session(session)
        session.commit()

    engine1.dispose()

    engine2 = build_engine(settings)
    factory2 = build_session_factory(settings)

    with factory2() as session:
        row = session.get(SessionState, 1)
        assert row is not None
        assert row.session_id is not None
        assert row.started_at is not None


# =========================================================================
#  AIControl persistence
# =========================================================================


def test_ai_control_apply_persists_across_restart(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'ai-test.db'}"
    settings = IngestionSettings(database_url=db_url)

    engine1 = build_engine(settings)
    Base.metadata.create_all(engine1)
    factory1 = build_session_factory(settings)

    service = _build_ai_control_service(factory1)

    with factory1() as session:
        review = service.review_assignment(
            "forecast-model", "forecast-lite-v1", session=session
        )
        service.apply_assignment(review.review_id, session=session)
        session.commit()

    engine1.dispose()

    engine2 = build_engine(settings)
    factory2 = build_session_factory(settings)

    service2 = _build_ai_control_service(factory2)
    assert service2.assignments["forecast-model"] == "forecast-lite-v1"


# =========================================================================
#  Workspace persistence
# =========================================================================


def test_workspace_set_focus_persists_across_restart(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'ws-test.db'}"
    settings = IngestionSettings(database_url=db_url)

    engine1 = build_engine(settings)
    Base.metadata.create_all(engine1)
    factory1 = build_session_factory(settings)

    service = _build_workspace_service(factory1)

    with factory1() as session:
        _seed_session_data(session)
        session.commit()

    with factory1() as session:
        service.set_focus(
            symbol="BTCUSDT",
            focus_source="manual",
            signal_id=None,
            session=session,
        )
        session.commit()

    engine1.dispose()

    engine2 = build_engine(settings)
    factory2 = build_session_factory(settings)

    with factory2() as session:
        row = session.get(WorkspaceFocus, 1)
        assert row is not None
        assert row.focus_symbol == "BTCUSDT"
        assert row.focus_source == "manual"


# =========================================================================
#  Rollback test
# =========================================================================


def test_rollback_on_exception_removes_changes(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'rollback-test.db'}"
    settings = IngestionSettings(database_url=db_url)

    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    factory = build_session_factory(settings)

    session_obj = factory()
    try:
        repo = AIAssignmentRepository(session_obj)
        repo.upsert("test-role", "test-model")
        raise RuntimeError("simulated failure")
    except RuntimeError:
        session_obj.rollback()
    finally:
        session_obj.close()

    engine.dispose()

    engine2 = build_engine(settings)
    factory2 = build_session_factory(settings)
    with factory2() as session:
        repo = AIAssignmentRepository(session)
        all_assignments = repo.read_all()
        assert "test-role" not in all_assignments
