from datetime import UTC, datetime, timedelta

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.events.bus import EventBus
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService
from clay.preflight.service import PreflightService


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
    )


def test_workspace_snapshot_contains_required_e3_fields(db_session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)

    market_repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70200.0,
                "high": 70450.0,
                "low": 70100.0,
                "close": 70400.0,
                "volume": 210.0,
                "quote_volume": 12840000.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            },
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "open": 3600.0,
                "high": 3618.0,
                "low": 3580.0,
                "close": 3588.0,
                "volume": 140.0,
                "quote_volume": 510000.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            },
        ],
    )
    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        freshness_state="fresh",
        evaluated_at=now,
        latest_bar_open_time=now - timedelta(minutes=15),
        is_stale=False,
    )
    market_repository.upsert_freshness_status(
        symbol="ETHUSDT",
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
                "sentiment_score": 0.71,
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
    db_session.commit()

    snapshot = build_workspace_service().build_snapshot(db_session)

    assert snapshot.focus_pair.symbol == "BTCUSDT"
    assert snapshot.workspace_state.runtime_state == "background_monitoring"
    assert snapshot.workspace_state.workspace_posture in {"normal", "monitoring_only"}
    assert snapshot.workspace_state.focused_signal_state in {"active", "weakening", "absent"}
    assert snapshot.monitoring_pool
    assert snapshot.update_meta.market_status == "fresh"


def test_workspace_focus_selection_updates_focus_source(db_session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)

    for symbol, close in [("BTCUSDT", 70400.0), ("SOLUSDT", 180.0)]:
        market_repository.upsert_market_bars(
            [
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.985,
                    "close": close,
                    "volume": 100.0 if symbol == "BTCUSDT" else 160.0,
                    "quote_volume": 900000.0,
                    "source": "binance_spot",
                    "bar_open_time": now - timedelta(minutes=15),
                    "bar_close_time": now - timedelta(minutes=1),
                },
            ],
        )
        market_repository.upsert_freshness_status(
            symbol=symbol,
            timeframe="15m",
            freshness_state="fresh",
            evaluated_at=now,
            latest_bar_open_time=now - timedelta(minutes=15),
            is_stale=False,
        )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "SOLUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.84,
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
    db_session.commit()

    service = build_workspace_service()
    service.set_focus(symbol="SOLUSDT", focus_source="monitoring_click")
    snapshot = service.build_snapshot(db_session)

    assert snapshot.focus_pair.symbol == "SOLUSDT"
    assert snapshot.focus_pair.focus_source == "monitoring_click"


def test_workspace_switches_to_defensive_when_market_data_is_old(
    db_session,
) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(db_session)
    context_repository = ContextRepository(db_session)
    ops_repository = OpsRepository(db_session)

    market_repository.upsert_market_bars(
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "open": 70200.0,
                "high": 70450.0,
                "low": 70100.0,
                "close": 70400.0,
                "volume": 210.0,
                "quote_volume": 12840000.0,
                "source": "binance_spot",
                "bar_open_time": now - timedelta(days=6, minutes=15),
                "bar_close_time": now - timedelta(days=6, minutes=1),
            },
        ],
    )
    market_repository.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        freshness_state="fresh",
        evaluated_at=now - timedelta(days=6),
        latest_bar_open_time=now - timedelta(days=6),
        is_stale=False,
    )
    context_repository.store_news_items(
        [
            {
                "source_name": "demo_news_feed",
                "headline": "BTC pauses after breakout",
                "summary": "Context still available, but market data is old.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc-pause",
            },
        ],
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.71,
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
    db_session.commit()

    snapshot = build_workspace_service().build_snapshot(db_session)

    assert snapshot.workspace_state.workspace_posture == "defensive"
    assert snapshot.update_meta.market_status == "degraded"
