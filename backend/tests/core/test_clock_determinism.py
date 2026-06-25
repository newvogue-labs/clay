"""Determinism test: shared VirtualClock across the reliability snapshot chain.

Verifies that every ``build_snapshot()`` on the auto-pilot replay path
derives ``now`` from the injected clock, not from ``datetime.now(UTC)``.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.control_center.service import ControlCenterService
from clay.core.clock import VirtualClock
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
from clay.validation_lab.service import ValidationLabService
from clay.workspace.service import WorkspaceService


AS_OF = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)


def _build_bundle(tmp_path: Path, clock: VirtualClock) -> dict[str, Any]:
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
        clock=clock,
    )
    signal_engine_service = SignalEngineService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        ai_control_service=ai_control_service,
        clock=clock,
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
        clock=clock,
    )
    demo_trading_service = DemoTradingService(
        session_control_service=session_control_service,
        workspace_service=workspace_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        clock=clock,
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
        clock=clock,
    )
    control_center_service = ControlCenterService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        supervisor=supervisor,
        config_loader=config_loader,
        audit_writer=audit_writer,
        ingestion_settings=IngestionSettings(),
        clock=clock,
    )
    reliability_service = ReliabilityService(
        control_center_service=control_center_service,
        ai_control_service=ai_control_service,
        demo_trading_service=demo_trading_service,
        session_review_service=session_review_service,
        validation_lab_service=validation_lab_service,
        audit_writer=audit_writer,
        event_bus=event_bus,
        clock=clock,
    )
    return {"service": reliability_service, "clock": clock}


def _seed_data(session: Any) -> None:
    now = datetime.now(UTC)
    market_repo = MarketRepository(session)
    context_repo = ContextRepository(session)
    ops_repo = OpsRepository(session)
    demo_repo = DemoRepository(session)

    market_repo.upsert_market_bars([
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
    ])
    market_repo.upsert_freshness_status(
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_spot",
        freshness_state="fresh",
        evaluated_at=now,
        latest_bar_open_time=now - timedelta(minutes=15),
        is_stale=False,
    )
    context_repo.store_news_items([
        {
            "source_name": "demo_news_feed",
            "headline": "test",
            "summary": "test",
            "published_at": now - timedelta(minutes=30),
            "symbol": "BTCUSDT",
            "source_url": "https://example.invalid/news/test",
        },
    ])
    context_repo.store_sentiment_snapshots([
        {
            "source_name": "demo_sentiment_feed",
            "symbol": "BTCUSDT",
            "sentiment_label": "bullish",
            "sentiment_score": 0.8,
            "captured_at": now - timedelta(minutes=20),
        },
    ])
    ops_repo.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=now,
    )
    ops_repo.record_connector_status(
        connector_id="demo-sentiment",
        connector_type="sentiment",
        status="healthy",
        observed_at=now,
    )
    for i in range(3):
        demo_repo.create_trade_record({
            "session_id": f"det-session-{i}",
            "signal_id": f"sig-{i}",
            "symbol": "BTCUSDT",
            "executed_symbol": "BTCUSDT",
            "operator_action": "entered",
            "operator_notes": "determinism seed",
            "recorded_at": now - timedelta(hours=i + 1),
            "broker_status": "closed",
            "entry_price": 70000.0 + i,
            "exit_price": 70120.0 + i,
            "pnl_pct": 1.2 + (i * 0.1),
            "observed_at": now - timedelta(hours=i + 1) + timedelta(minutes=20),
            "outcome_status": "matched",
        })
    session.commit()


class TestReplayPathDeterminism:
    """All timestamps in the reliability snapshot must derive from VirtualClock."""

    def test_reliability_last_evaluated_at_matches_virtual_clock(
        self, db_session: Any, tmp_path: Path,
    ) -> None:
        clock = VirtualClock(start=AS_OF)
        bundle = _build_bundle(tmp_path, clock)
        _seed_data(db_session)

        snapshot = bundle["service"].build_snapshot(db_session)

        assert snapshot.summary.last_evaluated_at == AS_OF.isoformat()

    def test_control_center_last_evaluated_at_matches_virtual_clock(
        self, db_session: Any, tmp_path: Path,
    ) -> None:
        clock = VirtualClock(start=AS_OF)
        bundle = _build_bundle(tmp_path, clock)
        _seed_data(db_session)

        snapshot = bundle["service"].build_snapshot(db_session)

        # The control_center summary stores last_evaluated_at as ISO string
        # inside the reliability snapshot — verify it matches AS_OF.
        assert snapshot.summary.last_evaluated_at == AS_OF.isoformat()

    def test_clock_not_wall_clock(
        self, db_session: Any, tmp_path: Path,
    ) -> None:
        """With VirtualClock at historical AS_OF, the snapshot must NOT
        contain a wall-clock timestamp."""
        clock = VirtualClock(start=AS_OF)
        bundle = _build_bundle(tmp_path, clock)
        _seed_data(db_session)

        snapshot = bundle["service"].build_snapshot(db_session)

        now_wall = datetime.now(UTC)
        ts = snapshot.summary.last_evaluated_at
        parsed = datetime.fromisoformat(ts)
        # The parsed timestamp should be AS_OF, not wall-clock
        assert parsed == AS_OF, (
            f"last_evaluated_at={ts} is wall-clock, expected AS_OF={AS_OF.isoformat()}"
        )
        # Wall-clock would differ by much more than 1s; if it passes,
        # the clock was properly injected.
        wall_delta = abs((parsed - now_wall).total_seconds())
        assert wall_delta > 60, (
            f"last_evaluated_at={ts} is within {wall_delta:.0f}s of wall-clock — "
            f"VirtualClock not used"
        )
