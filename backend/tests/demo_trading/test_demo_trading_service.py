from datetime import UTC, datetime, timedelta
from pathlib import Path

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_demo import DemoRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.demo_trading.models import DemoTradeLogCommand
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_control.service import SessionControlService
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService


def build_demo_service(tmp_path: Path) -> tuple[DemoTradingService, SessionControlService]:
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
    )
    demo_trading_service = DemoTradingService(
        session_control_service=session_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )
    return demo_trading_service, session_control_service


def seed_demo_data(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)
    for symbol, close, volume, sentiment_score in [
        ("BTCUSDT", 70540.0, 240.0, 0.74),
        ("SOLUSDT", 181.5, 320.0, 0.9),
    ]:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.985,
                    "close": close,
                    "volume": volume,
                    "quote_volume": close * volume,
                    "source": "binance_spot",
                    "bar_open_time": now - timedelta(minutes=15),
                    "bar_close_time": now - timedelta(minutes=1),
                },
            ]
        )
        market_repository.upsert_freshness_status(
            symbol=symbol,
            timeframe="15m",
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=now - timedelta(minutes=15),
            is_stale=False,
        )
        context_repository.store_news_items(
            [
                {
                    "source_name": "demo_news_feed",
                    "headline": f"{symbol} setup is live",
                    "summary": "Context supports disciplined demo execution.",
                    "published_at": now - timedelta(minutes=20),
                    "symbol": symbol,
                    "source_url": f"https://example.invalid/news/{symbol.lower()}",
                },
            ]
        )
        context_repository.store_sentiment_snapshots(
            [
                {
                    "source_name": "demo_sentiment_feed",
                    "symbol": symbol,
                    "sentiment_label": "bullish",
                    "sentiment_score": sentiment_score,
                    "captured_at": now - timedelta(minutes=12),
                },
            ]
        )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def test_demo_trading_service_logs_trade_and_ingests_result(
    db_session,
    tmp_path: Path,
) -> None:
    demo_trading_service, session_control_service = build_demo_service(tmp_path)
    seed_demo_data(db_session)

    session_control_service.start_session(db_session)
    snapshot = demo_trading_service.log_current_trade(
        db_session,
        DemoTradeLogCommand(operator_action="entered", operator_notes="Entered on Binance demo."),
    )

    assert snapshot.active_session.can_log_decision is True
    assert snapshot.records[0].operator_action == "entered"
    assert snapshot.records[0].awaiting_result is True

    updated = demo_trading_service.ingest_result(
        db_session,
        record_id=snapshot.records[0].record_id,
        external_trade_id="paper-1",
        broker_status="closed",
        entry_price=100.0,
        exit_price=102.4,
        pnl_pct=2.4,
    )

    assert updated.records[0].outcome_status == "matched"
    assert updated.records[0].awaiting_result is False
    assert updated.readiness.status == "collecting"


def test_demo_trading_service_recognizes_ready_review_gate(
    db_session,
    tmp_path: Path,
) -> None:
    demo_trading_service, _ = build_demo_service(tmp_path)
    repository = DemoRepository(db_session)
    now = datetime.now(UTC)

    for index in range(5):
        repository.create_trade_record(
            {
                "session_id": f"session-{index}",
                "signal_id": f"sig-{index}",
                "symbol": "BTCUSDT",
                "executed_symbol": "BTCUSDT",
                "operator_action": "entered",
                "recorded_at": now - timedelta(hours=index + 1),
                "broker_status": "closed",
                "entry_price": 100.0,
                "exit_price": 101.5,
                "pnl_pct": 1.5,
                "observed_at": now - timedelta(hours=index + 1) + timedelta(minutes=10),
                "outcome_status": "matched",
            }
        )
    db_session.commit()

    snapshot = demo_trading_service.build_snapshot(db_session)

    assert snapshot.readiness.status == "ready_for_review"
    assert snapshot.readiness.distinct_session_count == 5
    assert snapshot.readiness.outcome_counts["matched"] == 5
