from datetime import UTC, datetime, timedelta

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.signal_engine.service import SignalEngineService
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository


def build_signal_engine() -> SignalEngineService:
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
    return SignalEngineService(
        runtime_manager=RuntimeManager(registry=registry),
        preflight_service=PreflightService(registry),
        config_loader=config_loader,
        ai_control_service=ai_control_service,
    )


def seed_signal_data(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)
    for symbol, close, volume in [("BTCUSDT", 70540.0, 260.0), ("SOLUSDT", 179.1, 95.0)]:
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
                }
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
                "headline": "BTC keeps leadership",
                "summary": "Momentum stays constructive.",
                "published_at": now - timedelta(minutes=25),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/btc",
            }
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
            {
                "source_name": "demo_sentiment_feed",
                "symbol": "BTCUSDT",
                "sentiment_label": "bullish",
                "sentiment_score": 0.81,
                "captured_at": now - timedelta(minutes=10),
            }
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def test_signal_engine_applies_context_penalties_and_risk_actions(db_session) -> None:
    engine = build_signal_engine()
    seed_signal_data(db_session)

    snapshot = engine.build_snapshot(db_session)

    assert snapshot.signals
    btc = next(signal for signal in snapshot.signals if signal.symbol == "BTCUSDT")
    sol = next(signal for signal in snapshot.signals if signal.symbol == "SOLUSDT")
    assert btc.ranking_score >= sol.ranking_score
    assert sol.response_action in {"lower_confidence", "block_signal", "warning_only"}
    assert any(trigger.title == "Low context quality" for trigger in sol.risk_triggers)


def test_signal_engine_switches_to_defensive_when_runtime_is_degraded(db_session) -> None:
    engine = build_signal_engine()
    seed_signal_data(db_session)
    engine.runtime_manager.enter_degraded()

    snapshot = engine.build_snapshot(db_session)

    assert snapshot.workspace_posture == "restricted_by_degraded"
    assert snapshot.strategy_mode_proposal == "defensive"
    assert any(signal.response_action == "switch_to_defensive" for signal in snapshot.signals)
