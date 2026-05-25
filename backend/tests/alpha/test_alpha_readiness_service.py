import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from clay.ai_control.service import AIControlService
from clay.alpha.service import AlphaReadinessService
from clay.api.routes.alpha import get_alpha_overview
from clay.api.routes.demo_trading import ingest_demo_result, log_current_demo_trade
from clay.api.routes.reliability import recheck_reliability
from clay.api.routes.session_control import complete_session, start_session
from clay.api.routes.session_review import capture_session_feedback
from clay.api.routes.validation_lab import run_validation_lab
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.control_center.service import ControlCenterService
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_demo import DemoRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.demo_trading.models import DemoResultIngestCommand, DemoTradeLogCommand
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.reliability.service import ReliabilityService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor
from clay.session_control.service import SessionControlService
from clay.session_review.models import FeedbackCreateCommand
from clay.session_review.service import SessionReviewService
from clay.signal_engine.service import SignalEngineService
from clay.validation_lab.models import ValidationRunCommand
from clay.validation_lab.service import ValidationLabService
from clay.workspace.service import WorkspaceService


def build_alpha_bundle(tmp_path: Path) -> dict[str, object]:
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
    alpha_service = AlphaReadinessService(
        workspace_service=workspace_service,
        session_control_service=session_control_service,
        demo_trading_service=demo_trading_service,
        session_review_service=session_review_service,
        validation_lab_service=validation_lab_service,
        reliability_service=reliability_service,
    )
    return {
        "service": alpha_service,
        "session_control_service": session_control_service,
        "demo_trading_service": demo_trading_service,
        "session_review_service": session_review_service,
        "validation_lab_service": validation_lab_service,
        "reliability_service": reliability_service,
    }


def seed_alpha_inputs(session) -> None:
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
                "high": 70200.0,
                "low": 69900.0,
                "close": 70150.0,
                "volume": 250.0,
                "quote_volume": 17_500_000.0,
                "source": "binance_unit_test",
                "bar_open_time": now - timedelta(minutes=15),
                "bar_close_time": now - timedelta(minutes=1),
            }
        ]
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
                "headline": "Alpha core input is ready",
                "summary": "Context coverage is healthy.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/alpha",
            }
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
            }
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


def seed_alpha_demo_evidence(session) -> None:
    demo_repository = DemoRepository(session)
    now = datetime.now(UTC)
    for index in range(5):
        demo_repository.create_trade_record(
            {
                "session_id": f"alpha-session-{index + 1}",
                "signal_id": f"sig-btc-{index + 1}",
                "symbol": "BTCUSDT",
                "executed_symbol": "BTCUSDT",
                "operator_action": "entered",
                "operator_notes": "alpha readiness sample",
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


def next_operator_step(payload: dict[str, object]) -> dict[str, object] | None:
    return next(
        (
            step
            for step in payload["operator_steps"]
            if isinstance(step, dict) and step["is_next"]
        ),
        None,
    )


def assert_next_step(payload: dict[str, object], step_id: str, target_screen: str) -> None:
    next_step = next_operator_step(payload)
    assert next_step is not None
    assert next_step["step_id"] == step_id
    assert next_step["target_screen"] == target_screen


def test_alpha_readiness_blocks_without_fresh_inputs(db_session, tmp_path: Path) -> None:
    bundle = build_alpha_bundle(tmp_path)

    snapshot = bundle["service"].build_snapshot(db_session)

    assert snapshot.summary.readiness_status == "blocked"
    assert snapshot.summary.operator_path_ready is False
    assert any(gate.gate_id == "preflight-ready" and gate.status == "fail" for gate in snapshot.gates)
    assert any(gate.gate_id == "focused-signal" and gate.blocks_alpha for gate in snapshot.gates)
    next_steps = [step for step in snapshot.operator_steps if step.is_next]
    assert len(next_steps) == 1
    assert next_steps[0].step_id == "check_preflight"
    assert next_steps[0].target_screen == "session-control"


def test_alpha_readiness_opens_operator_path_when_session_can_run(db_session, tmp_path: Path) -> None:
    bundle = build_alpha_bundle(tmp_path)
    seed_alpha_inputs(db_session)
    bundle["session_control_service"].start_session(db_session)

    snapshot = bundle["service"].build_snapshot(db_session)

    assert snapshot.summary.readiness_status == "needs_attention"
    assert snapshot.summary.operator_path_ready is True
    assert snapshot.summary.blocking_gate_count == 0
    assert snapshot.evidence.session_lifecycle_state == "active_session"
    assert any(step.step_id == "log_demo_decision" and step.status == "warn" for step in snapshot.operator_steps)
    next_step = next(step for step in snapshot.operator_steps if step.is_next)
    assert next_step.step_id == "log_demo_decision"
    assert next_step.action_label == "Log demo decision"


def test_alpha_readiness_surfaces_evidence_gates(db_session, tmp_path: Path) -> None:
    bundle = build_alpha_bundle(tmp_path)
    seed_alpha_inputs(db_session)
    seed_alpha_demo_evidence(db_session)
    bundle["validation_lab_service"].run_validation(
        db_session,
        ValidationRunCommand(run_type="strategy_replay", label="Alpha core replay"),
    )

    snapshot = bundle["service"].build_snapshot(db_session)

    assert snapshot.summary.operator_path_ready is True
    assert snapshot.evidence.demo_readiness_status == "ready_for_review"
    assert snapshot.evidence.validation_replay_ready is True
    assert any(gate.gate_id == "demo-evidence" and gate.status == "pass" for gate in snapshot.gates)
    assert any(gate.gate_id == "validation-replay" and gate.status == "pass" for gate in snapshot.gates)


def test_alpha_happy_path_advances_runbook_across_operator_routes(db_session, tmp_path: Path) -> None:
    bundle = build_alpha_bundle(tmp_path)
    seed_alpha_inputs(db_session)

    initial = asyncio.run(get_alpha_overview(db_session, bundle["service"]))
    assert initial["summary"]["operator_path_ready"] is True
    assert_next_step(initial, "start_or_resume_session", "session-control")

    started = asyncio.run(start_session(db_session, bundle["session_control_service"]))
    assert started["lifecycle"]["lifecycle_state"] == "active_session"

    after_start = asyncio.run(get_alpha_overview(db_session, bundle["service"]))
    assert_next_step(after_start, "log_demo_decision", "demo-validation")

    logged = asyncio.run(
        log_current_demo_trade(
            DemoTradeLogCommand(
                operator_action="entered",
                operator_notes="Alpha happy path operator entry.",
            ),
            db_session,
            bundle["demo_trading_service"],
        )
    )
    record_id = logged["records"][0]["record_id"]

    after_log = asyncio.run(get_alpha_overview(db_session, bundle["service"]))
    assert_next_step(after_log, "resolve_demo_result", "demo-validation")

    resolved = asyncio.run(
        ingest_demo_result(
            DemoResultIngestCommand(
                record_id=record_id,
                external_trade_id="alpha-paper-1",
                broker_status="closed",
                entry_price=100.0,
                exit_price=101.4,
                pnl_pct=1.4,
            ),
            db_session,
            bundle["demo_trading_service"],
        )
    )
    assert resolved["records"][0]["outcome_status"] == "matched"

    completed = asyncio.run(complete_session(db_session, bundle["session_control_service"]))
    assert completed["lifecycle"]["lifecycle_state"] == "review"

    after_result = asyncio.run(get_alpha_overview(db_session, bundle["service"]))
    assert after_result["evidence"]["session_lifecycle_state"] == "review"
    assert_next_step(after_result, "review_feedback", "session-review")

    reviewed = asyncio.run(
        capture_session_feedback(
            FeedbackCreateCommand(
                record_id=record_id,
                feedback_label="useful",
                notes="Alpha happy path decision was coherent.",
            ),
            db_session,
            bundle["session_review_service"],
        )
    )
    assert reviewed["summary"]["feedback_count"] == 1

    after_feedback = asyncio.run(get_alpha_overview(db_session, bundle["service"]))
    assert_next_step(after_feedback, "run_validation_replay", "validation-lab")

    validation = asyncio.run(
        run_validation_lab(
            ValidationRunCommand(run_type="strategy_replay", label="Alpha happy path replay"),
            db_session,
            bundle["validation_lab_service"],
        )
    )
    assert validation["summary"]["replay_ready"] is True

    after_validation = asyncio.run(get_alpha_overview(db_session, bundle["service"]))
    assert_next_step(after_validation, "recheck_reliability", "reliability")

    reliability = asyncio.run(recheck_reliability(db_session, bundle["reliability_service"]))
    assert reliability["summary"]["last_rechecked_at"] is not None
    assert reliability["summary"]["release_readiness_status"] == "needs_attention"

    final = asyncio.run(get_alpha_overview(db_session, bundle["service"]))
    assert final["summary"]["operator_path_ready"] is True
    assert next_operator_step(final) is None
    assert all(step["status"] == "pass" for step in final["operator_steps"])


def test_alpha_overview_route_returns_snapshot_payload(db_session, tmp_path: Path) -> None:
    bundle = build_alpha_bundle(tmp_path)
    seed_alpha_inputs(db_session)

    payload = asyncio.run(get_alpha_overview(db_session, bundle["service"]))

    assert payload["summary"]["operator_path_ready"] is True
    assert payload["evidence"]["focus_symbol"] == "BTCUSDT"
    assert payload["gates"]
    assert any(step["is_next"] and step["target_screen"] == "session-control" for step in payload["operator_steps"])
