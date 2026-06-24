import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.api.routes.reliability import get_reliability_overview, recheck_reliability
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.control_center.service import ControlCenterService
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_demo import DemoRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
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
from clay.settings.ingestion import IngestionSettings
from clay.signal_engine.service import SignalEngineService
from clay.services.models import ServiceStatus
from clay.validation_lab.models import ValidationRunCommand
from clay.validation_lab.service import ValidationLabService
from clay.workspace.service import WorkspaceService


def build_reliability_bundle(tmp_path: Path) -> dict[str, object]:
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
    session_control_service = SessionControlService(
        runtime_manager=runtime_manager,
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
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
    reliability_service = ReliabilityService(
        control_center_service=control_center_service,
        ai_control_service=ai_control_service,
        demo_trading_service=demo_trading_service,
        session_review_service=session_review_service,
        validation_lab_service=validation_lab_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    return {
        "service": reliability_service,
        "runtime_manager": runtime_manager,
        "registry": registry,
        "validation_lab_service": validation_lab_service,
    }


def seed_reliability_inputs(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)
    market_repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70000.0,
                "high": 70600.0,
                "low": 69950.0,
                "close": 70500.0,
                "volume": 250.0,
                "quote_volume": 17600000.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            },
        ]
    )
    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=now,
        latest_bar_open_time=now - timedelta(minutes=15),
        is_stale=False,
    )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "Reliability input is ready",
                "summary": "Context coverage is healthy.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/reliability",
            },
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.8,
                "captured_at": now - timedelta(minutes=20),
            },
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    ops_repository.record_connector_status(
        connector_id="demo-sentiment",
        connector_type="sentiment",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def seed_release_ready_evidence(session) -> None:
    demo_repository = DemoRepository(session)
    now = datetime.now(UTC)
    for index in range(5):
        demo_repository.create_trade_record(
            {
                "session_id": f"session-{index + 1}",
                "signal_id": f"sig-btc-{index + 1}",
                "symbol": "BTCUSDT",
                "executed_symbol": "BTCUSDT",
                "operator_action": "entered",
                "operator_notes": "disciplined replay sample",
                "recorded_at": now - timedelta(hours=index + 1),
                "broker_status": "closed",
                "entry_price": 70000.0 + index,
                "exit_price": 70120.0 + index,
                "pnl_pct": 1.2 + (index * 0.1),
                "observed_at": now - timedelta(hours=index + 1) + timedelta(minutes=20),
                "outcome_status": "matched",
            }
        )
    session.commit()


def test_reliability_overview_route_returns_snapshot(db_session, tmp_path: Path) -> None:
    bundle = build_reliability_bundle(tmp_path)
    seed_reliability_inputs(db_session)
    bundle["runtime_manager"].enter_degraded()
    bundle["registry"].update_status("control-api", ServiceStatus.STOPPED, error="operator stop")

    payload = asyncio.run(get_reliability_overview(db_session, bundle["service"]))

    assert payload["summary"]["release_readiness_status"] == "blocked"
    assert payload["degraded_triggers"]


def test_reliability_recheck_route_returns_updated_snapshot(db_session, tmp_path: Path) -> None:
    bundle = build_reliability_bundle(tmp_path)
    seed_reliability_inputs(db_session)
    seed_release_ready_evidence(db_session)
    bundle["validation_lab_service"].run_validation(
        db_session,
        ValidationRunCommand(run_type="strategy_replay", label="Release rehearsal"),
    )

    payload = asyncio.run(recheck_reliability(db_session, bundle["service"]))

    assert payload["summary"]["release_readiness_status"] == "ready_for_demo"
    assert payload["summary"]["last_rechecked_at"] is not None
    assert payload["release_gates"]


def test_reliability_ignores_resolved_incidents_for_release_blockers(
    db_session,
    tmp_path: Path,
) -> None:
    bundle = build_reliability_bundle(tmp_path)
    seed_reliability_inputs(db_session)
    ops_repository = OpsRepository(db_session)
    now = datetime.now(UTC)

    ops_repository.record_source_health_event(
        source_name="binance_spot:BTCUSDT:5m",
        severity="error",
        message="TimeoutError",
        recorded_at=now - timedelta(minutes=10),
    )
    ops_repository.resolve_source_health_events(
        source_name="binance_spot:BTCUSDT:5m",
        resolved_at=now,
        resolution_message="Market ingest recovered after successful refresh.",
    )
    db_session.commit()

    payload = asyncio.run(get_reliability_overview(db_session, bundle["service"]))

    assert payload["summary"]["blocking_gate_count"] == 0
    assert all(trigger["trigger_id"] != "critical-incidents" for trigger in payload["degraded_triggers"])
    assert all(
        not (gate["gate_id"] == "incident-budget" and gate["blocks_release"])
        for gate in payload["release_gates"]
    )
