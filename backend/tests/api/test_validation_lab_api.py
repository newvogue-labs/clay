import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clay.ai_control.service import AIControlService
from clay.api.routes.validation_lab import (
    apply_activation,
    get_validation_lab_overview,
    review_activation,
    run_validation_lab,
)
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_review.service import SessionReviewService
from clay.signal_engine.service import SignalEngineService
from clay.validation_lab.models import (
    ActivationApplyCommand,
    ActivationReviewCommand,
    ValidationRunCommand,
)
from clay.validation_lab.service import ValidationLabService


def build_validation_service(tmp_path: Path) -> ValidationLabService:
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
    session_review_service = SessionReviewService(
        audit_writer=audit_writer,
        event_bus=event_bus,
        ai_control_service=ai_control_service,
    )
    signal_engine_service = SignalEngineService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        ai_control_service=ai_control_service,
    )
    return ValidationLabService(
        signal_engine_service=signal_engine_service,
        ai_control_service=ai_control_service,
        session_review_service=session_review_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
    )


def seed_validation_inputs(session) -> None:
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
                "headline": "Validation input is ready",
                "summary": "Context supports replay analysis.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/validation",
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
    session.commit()


def test_validation_lab_overview_and_run_route(db_session, tmp_path: Path) -> None:
    service = build_validation_service(tmp_path)
    seed_validation_inputs(db_session)

    initial = asyncio.run(get_validation_lab_overview(db_session, service))
    assert initial["summary"]["total_runs"] == 0

    payload = asyncio.run(
        run_validation_lab(
            ValidationRunCommand(
                run_type="signal_quality", label="Signal quality replay"
            ),
            db_session,
            service,
        )
    )
    assert payload["summary"]["total_runs"] == 1


def test_validation_lab_review_and_apply_route(db_session, tmp_path: Path) -> None:
    service = build_validation_service(tmp_path)
    seed_validation_inputs(db_session)
    asyncio.run(
        run_validation_lab(
            ValidationRunCommand(run_type="strategy_replay", label="Replay"),
            db_session,
            service,
        )
    )
    review = asyncio.run(
        review_activation(
            ActivationReviewCommand(
                target_type="strategy_mode",
                target_id="global-strategy",
                proposed_value="defensive",
            ),
            db_session,
            service,
        )
    )
    payload = asyncio.run(
        apply_activation(
            ActivationApplyCommand(review_id=review["review_id"]),
            db_session,
            service,
        )
    )

    assert payload["activation_reviews"][0]["status"] == "applied"
