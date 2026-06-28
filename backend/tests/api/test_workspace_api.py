import asyncio
from datetime import UTC, datetime, timedelta

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.api.routes.workspace import (
    get_trading_focus,
    get_trading_workspace_snapshot,
    set_focus_pair,
)
from clay.execution.config import ExecutionConfig
from clay.execution.service import OverrideService
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.events.bus import EventBus
from clay.workspace.models import FocusCommand
from clay.workspace.service import WorkspaceService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.preflight.service import PreflightService
from clay.signal_engine.service import SignalEngineService


def build_workspace_service() -> WorkspaceService:
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
    ai_control_service = AIControlService(
        runtime_manager=RuntimeManager(registry=registry),
        preflight_service=PreflightService(registry),
        config_loader=config_loader,
        audit_writer=AuditWriter(config_loader.paths.state_dir),
        event_bus=EventBus(),
    )
    execution_config = ExecutionConfig(mode="dry_run", allow_live_override=False)
    override_service = OverrideService(
        session_factory=None,
        audit_writer=None,
        execution_config=execution_config,
    )
    return WorkspaceService(
        runtime_manager=RuntimeManager(registry=registry),
        preflight_service=PreflightService(registry),
        registry=registry,
        signal_engine_service=SignalEngineService(
            runtime_manager=RuntimeManager(registry=registry),
            preflight_service=PreflightService(registry),
            config_loader=config_loader,
            ai_control_service=ai_control_service,
        ),
        execution_config=execution_config,
        override_service=override_service,
    )


def seed_workspace_data(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)

    bars = [
        ("BTCUSDT", 70200.0, 70620.0, 70020.0, 70540.0, 260.0),
        ("ETHUSDT", 3600.0, 3625.0, 3580.0, 3612.0, 150.0),
        ("SOLUSDT", 178.0, 180.0, 177.2, 179.1, 95.0),
    ]
    for symbol, open_price, high, low, close, volume in bars:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "quote_volume": close * volume,
                    "source": "binance_spot",
                    "bar_open_time": now - timedelta(minutes=15),
                    "bar_close_time": now - timedelta(minutes=1),
                },
            ],
        )
        market_repository.upsert_freshness_status(
            symbol=symbol,
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
                "headline": "BTC keeps leadership",
                "summary": "Momentum stays constructive on intraday pullbacks.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc",
            },
        ],
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.76,
                "captured_at": now - timedelta(minutes=20),
            },
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "SOLUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.81,
                "captured_at": now - timedelta(minutes=20),
            },
        ],
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def test_workspace_snapshot_route_returns_focus_pair_and_state(db_session) -> None:
    seed_workspace_data(db_session)
    payload = asyncio.run(
        get_trading_workspace_snapshot(db_session, build_workspace_service())
    )

    assert payload["focus_pair"]["symbol"] == "BTCUSDT"
    assert payload["workspace_state"]["runtime_state"] == "background_monitoring"
    assert payload["signals"]
    assert payload["monitoring_pool"]


def test_workspace_focus_routes_return_current_focus_snapshot(db_session) -> None:
    service = build_workspace_service()
    seed_workspace_data(db_session)

    before = asyncio.run(get_trading_focus(db_session, service))
    after = asyncio.run(
        set_focus_pair(
            FocusCommand(symbol="SOLUSDT", focus_source="monitoring_click"),
            db_session,
            service,
        ),
    )

    assert before["focus_pair"]["focus_source"] == "system_recommendation"
    assert after["focus_pair"]["symbol"] == "SOLUSDT"
    assert after["focus_pair"]["focus_source"] == "monitoring_click"
