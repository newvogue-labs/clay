from datetime import UTC, datetime, timedelta
from pathlib import Path

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.db.repositories_demo import DemoRepository
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_review.models import FeedbackCreateCommand
from clay.session_review.service import SessionReviewService


def build_review_service(tmp_path: Path) -> SessionReviewService:
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
    audit_writer.write("demo.trade.logged", {"record_id": 1, "signal_id": "sig-btc", "symbol": "BTCUSDT"})
    return SessionReviewService(
        audit_writer=audit_writer,
        event_bus=event_bus,
        ai_control_service=ai_control_service,
    )


def seed_review_records(session) -> None:
    repository = DemoRepository(session)
    now = datetime.now(UTC)
    repository.create_trade_record(
        {
            "session_id": "session-1",
            "signal_id": "sig-btc",
            "symbol": "BTCUSDT",
            "executed_symbol": "BTCUSDT",
            "operator_action": "entered",
            "recorded_at": now - timedelta(minutes=30),
            "broker_status": "closed",
            "entry_price": 100.0,
            "exit_price": 102.0,
            "pnl_pct": 2.0,
            "observed_at": now - timedelta(minutes=20),
            "outcome_status": "matched",
        }
    )
    repository.create_trade_record(
        {
            "session_id": "session-2",
            "signal_id": "sig-sol",
            "symbol": "SOLUSDT",
            "executed_symbol": "SOLUSDT",
            "operator_action": "off_signal",
            "recorded_at": now - timedelta(minutes=10),
            "broker_status": "closed",
            "entry_price": 100.0,
            "exit_price": 99.0,
            "pnl_pct": -1.0,
            "observed_at": now - timedelta(minutes=5),
            "outcome_status": "mismatched",
        }
    )
    session.commit()


def test_session_review_snapshot_includes_filters_and_cards(db_session, tmp_path: Path) -> None:
    service = build_review_service(tmp_path)
    seed_review_records(db_session)

    snapshot = service.build_snapshot(db_session)

    assert snapshot.summary.total_demo_records == 2
    assert "BTCUSDT" in snapshot.filter_options.pairs
    assert snapshot.ai_review_cards
    assert snapshot.audit


def test_session_review_feedback_capture_updates_snapshot(db_session, tmp_path: Path) -> None:
    service = build_review_service(tmp_path)
    seed_review_records(db_session)

    snapshot = service.capture_feedback(
        db_session,
        FeedbackCreateCommand(record_id=1, feedback_label="useful", notes="Good structure."),
    )

    assert snapshot.feedback[0].feedback_label == "useful"
    assert snapshot.summary.feedback_count == 1
