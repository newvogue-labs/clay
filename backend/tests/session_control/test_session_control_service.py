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
from clay.session_control.service import SessionControlService
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository


def build_session_service() -> SessionControlService:
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
        config_loader=ConfigLoader(),
    )


def seed_session_data(session) -> None:
    now = datetime.now(UTC)
    market_repository = MarketRepository(session)
    context_repository = ContextRepository(session)
    ops_repository = OpsRepository(session)

    for symbol, close, volume in [("BTCUSDT", 70540.0, 260.0), ("SOLUSDT", 181.5, 320.0)]:
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
                "headline": "BTC and SOL remain constructive",
                "summary": "Intraday structure still supports a session start.",
                "published_at": now - timedelta(minutes=20),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/session",
            },
            {
                "source_name": "demo_news_feed",
                "headline": "SOL gains momentum",
                "summary": "Rotation toward SOL improves relative ranking.",
                "published_at": now - timedelta(minutes=10),
                "symbol": "SOLUSDT",
                "source_url": "https://example.invalid/news/sol",
            },
        ]
    )
    context_repository.store_sentiment_snapshots(
        [
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
        ]
    )
    ops_repository.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def test_session_service_runs_full_lifecycle(db_session) -> None:
    service = build_session_service()
    seed_session_data(db_session)

    started = service.start_session(db_session)
    assert started.lifecycle.lifecycle_state == "active_session"
    assert started.lifecycle.can_pause is True

    paused = service.pause_session(db_session)
    assert paused.lifecycle.lifecycle_state == "paused"
    assert paused.lifecycle.can_resume is True

    resumed = service.resume_session(db_session)
    assert resumed.lifecycle.lifecycle_state == "active_session"

    completed = service.complete_session(db_session)
    assert completed.lifecycle.lifecycle_state == "review"
    assert completed.lifecycle.can_start is False


def test_session_service_reviews_and_applies_pair_replacement(db_session) -> None:
    service = build_session_service()
    seed_session_data(db_session)
    started = service.start_session(db_session)
    current_symbol = started.lifecycle.current_pair_symbol
    proposed_symbol = "SOLUSDT" if current_symbol != "SOLUSDT" else "BTCUSDT"

    review = service.review_pair_replacement(db_session, proposed_symbol=proposed_symbol)
    assert review.current_symbol == current_symbol
    assert review.proposed_symbol == proposed_symbol

    updated = service.apply_pair_replacement(db_session, review.review_id)
    assert updated.lifecycle.current_pair_symbol == proposed_symbol
