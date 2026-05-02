import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clay.audit.writer import AuditWriter
from clay.api.routes.control_center import get_control_center_overview
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.control_center.service import ControlCenterService
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor


def build_control_center_service(tmp_path: Path) -> ControlCenterService:
    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    registry.register(
        service_id="pair-scanner",
        service_type="worker",
        criticality=ServiceCriticality.OPTIONAL,
        startup_policy="on-demand",
    )
    registry.update_status("pair-scanner", ServiceStatus.STOPPED)

    config_loader = ConfigLoader(
        XdgPaths(
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
            state_dir=tmp_path / "state",
            cache_dir=tmp_path / "cache",
        ),
    )
    config_loader.ensure_default_configs()
    config_loader.load_all()

    audit_writer = AuditWriter(config_loader.paths.state_dir)
    audit_writer.write("runtime.transitioned", {"target": "background_monitoring"})

    supervisor = ProcessSupervisor(registry)
    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)

    return ControlCenterService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        supervisor=supervisor,
        config_loader=config_loader,
        audit_writer=audit_writer,
    )


def test_control_center_overview_returns_operator_snapshot(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    service = build_control_center_service(tmp_path)

    now = datetime.now(UTC)
    with sqlite_session_factory() as session:
        market_repository = MarketRepository(session)
        context_repository = ContextRepository(session)
        ops_repository = OpsRepository(session)

        market_repository.upsert_market_bars(
            [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "15m",
                    "open": 70200.0,
                    "high": 70400.0,
                    "low": 70100.0,
                    "close": 70350.0,
                    "volume": 120.0,
                    "quote_volume": 8440000.0,
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
        context_repository.store_news_items(
            [
                {
                    "source_name": "demo_news_feed",
                    "headline": "BTC holds breakout",
                    "summary": "Constructive intraday structure",
                    "published_at": now - timedelta(minutes=30),
                    "symbol": "BTCUSDT",
                    "source_url": "https://example.invalid/news/btc-breakout",
                },
            ],
        )
        context_repository.store_sentiment_snapshots(
            [
                {
                    "source_name": "demo_sentiment_feed",
                    "symbol": "BTCUSDT",
                    "sentiment_label": "bullish",
                    "sentiment_score": 0.68,
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
        ops_repository.record_source_health_event(
            source_name="demo_news_feed",
            severity="warning",
            message="connector recovered after retry",
            recorded_at=now,
        )
        session.commit()
        payload = asyncio.run(get_control_center_overview(session, service))

    assert payload["summary"]["runtime_state"] == "background_monitoring"
    assert payload["summary"]["overall_status"] == "degraded"
    assert payload["summary"]["active_incident_count"] == 1
    assert payload["runtime"]["preflight_status"] == "pass"
    assert payload["ingestion"]["market_status"] == "fresh"
    assert payload["services"][0]["service_id"] == "control-api"
    assert payload["incidents"][0]["message"] == "connector recovered after retry"
    assert payload["audit"][0]["event_type"] == "runtime.transitioned"
    assert payload["config"]["scopes"][0]["scope"] == "risk"


def test_control_center_recomputes_stale_market_freshness(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    service = build_control_center_service(tmp_path)
    now = datetime.now(UTC)

    with sqlite_session_factory() as session:
        market_repository = MarketRepository(session)
        market_repository.upsert_freshness_status(
            symbol="BTCUSDT",
            timeframe="15m",
            freshness_state="fresh",
            evaluated_at=now - timedelta(days=6),
            latest_bar_open_time=now - timedelta(days=6),
            is_stale=False,
        )
        session.commit()
        payload = asyncio.run(get_control_center_overview(session, service))

    assert payload["ingestion"]["market_status"] == "stale"
    assert payload["ingestion"]["blocks_active_trading"] is True
    assert payload["ingestion"]["market_items"][0]["status"] == "stale"


def test_control_center_ignores_resolved_incidents_in_active_counts(
    sqlite_session_factory,
    tmp_path: Path,
) -> None:
    service = build_control_center_service(tmp_path)
    now = datetime.now(UTC)

    with sqlite_session_factory() as session:
        ops_repository = OpsRepository(session)
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
        session.commit()
        payload = asyncio.run(get_control_center_overview(session, service))

    assert payload["summary"]["active_incident_count"] == 0
    assert payload["summary"]["critical_incident_count"] == 0
    assert payload["incidents"] == []
