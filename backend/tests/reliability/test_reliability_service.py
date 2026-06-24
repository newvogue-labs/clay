import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.control_center.service import ControlCenterService
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
from clay.settings.ingestion import IngestionSettings
from clay.services.registry import ServiceRegistry
from clay.services.supervisor import ProcessSupervisor
from clay.session_control.service import SessionControlService
from clay.session_review.service import SessionReviewService
from clay.signal_engine.service import SignalEngineService
from clay.validation_lab.models import ValidationRunCommand
from clay.validation_lab.service import ValidationLabService
from clay.workspace.service import WorkspaceService


def build_reliability_bundle(tmp_path: Path) -> dict[str, object]:
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
        config_loader=ConfigLoader(),
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
        ingestion_settings=IngestionSettings(),
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
    return {
        "service": reliability_service,
        "runtime_manager": runtime_manager,
        "registry": registry,
        "validation_lab_service": validation_lab_service,
    }


def seed_reliability_inputs(session) -> None:
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
                "headline": "Reliability input is ready",
                "summary": "Context coverage is healthy.",
                "published_at": now - timedelta(minutes=30),
                "symbol": "BTCUSDT",
                "source_url": "https://example.invalid/news/reliability",
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
    ops_repository.record_connector_status(
        connector_id="demo-sentiment",
        connector_type="sentiment",
        status="healthy",
        observed_at=now,
    )
    session.commit()


def seed_release_ready_evidence(session) -> None:
    demo_repository = DemoRepository(session)
    now = datetime.now(UTC)
    for index in range(5):
        demo_repository.create_trade_record(
            {
                "session_id": f"session-{index + 1}",
                "signal_id": f"sig-btc-{index + 1}",
                "symbol": "BTCUSDT",
                "executed_symbol": "BTCUSDT",
                "operator_action": "entered",
                "operator_notes": "disciplined replay sample",
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


def test_reliability_snapshot_blocks_release_when_runtime_is_degraded(db_session, tmp_path: Path) -> None:
    bundle = build_reliability_bundle(tmp_path)
    seed_reliability_inputs(db_session)
    bundle["runtime_manager"].enter_degraded()
    bundle["registry"].update_status("control-api", ServiceStatus.STOPPED, error="operator stop")

    snapshot = bundle["service"].build_snapshot(db_session)

    assert snapshot.summary.release_readiness_status == "blocked"
    assert snapshot.summary.blocking_gate_count >= 1
    assert any(trigger.trigger_id == "runtime-degraded" for trigger in snapshot.degraded_triggers)
    assert any(gate.gate_id == "runtime-stability" and gate.blocks_release for gate in snapshot.release_gates)


def test_reliability_snapshot_reports_needs_attention_with_good_demo_evidence(db_session, tmp_path: Path) -> None:
    bundle = build_reliability_bundle(tmp_path)
    seed_reliability_inputs(db_session)
    seed_release_ready_evidence(db_session)
    bundle["validation_lab_service"].run_validation(
        db_session,
        ValidationRunCommand(run_type="strategy_replay", label="Release rehearsal"),
    )

    snapshot = bundle["service"].build_snapshot(db_session)

    assert snapshot.summary.release_readiness_status == "ready_for_demo"
    assert snapshot.summary.blocking_gate_count == 0
    assert any(gate.gate_id == "demo-discipline" and gate.status == "pass" for gate in snapshot.release_gates)
    assert any(gate.gate_id == "local-fallback" and gate.status == "pass" for gate in snapshot.release_gates)


# === B4 — ReliabilityService.recheck() emit-flag refactor ===
#
# The B4 scheduler-driven recheck path (``ReliabilityRecheckJob``) calls
# ``recheck(session, emit=False)`` and applies its own transition-only
# audit/bus policy. The manual ``POST /reliability/recheck`` route keeps
# the default ``emit=True`` (backward-compat with the A6 audit
# contract). The two tests below pin both contracts.


def _read_audit_events(audit_writer: AuditWriter) -> list[dict[str, Any]]:
    """Read the JSONL audit log. Returns ``[]`` if the file does not exist.

    AuditWriter is lazy: ``write()`` creates the file on first call.
    A test that asserts "no audit was written" must tolerate the
    absent file (rather than crashing on ``open()``), so this helper
    short-circuits to ``[]`` when the path is missing.
    """
    if not audit_writer.path.exists():
        return []
    with audit_writer.path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _drain_event_bus(event_bus: EventBus) -> list[tuple[str, dict[str, Any]]]:
    """Drain every subscribed queue (test helper, mirrors scheduler tests)."""
    drained: list[tuple[str, dict[str, Any]]] = []
    for queue in list(event_bus._subscribers):  # noqa: SLF001 (test helper)
        while True:
            try:
                message = queue.get_nowait()
            except Exception:  # asyncio.QueueEmpty
                break
            drained.append((message.event_type, message.payload))
    return drained


def _build_fake_reliability_service(
    tmp_path: Path,
    *,
    session_factory: Any = None,
) -> tuple[ReliabilityService, AuditWriter, EventBus]:
    """Build a ``ReliabilityService`` with stubbed sub-services.

    Only the side-effect surface of ``recheck`` (audit_writer, event_bus,
    session_factory) is exercised here — the snapshot build pipeline is
    covered by the existing ``build_snapshot`` tests above, so the
    sub-services are stubbed with ``MagicMock`` and ``build_snapshot``
    is replaced with a fake.

    ``session_factory`` defaults to ``None`` so ``__init__`` falls
    into the no-restore branch (``_last_rechecked_at = None``). Tests
    that need ``recheck`` to persist ``last_rechecked_at`` assign
    ``service.session_factory`` post-construction (avoiding the
    no-op MagicMock init-restore that would otherwise clobber the
    in-memory timestamp with a MagicMock attribute).
    """
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    event_bus.subscribe()  # so _drain_event_bus sees published events
    stub = MagicMock()
    service = ReliabilityService(
        control_center_service=stub,
        ai_control_service=stub,
        demo_trading_service=stub,
        session_review_service=stub,
        validation_lab_service=stub,
        audit_writer=audit_writer,
        event_bus=event_bus,
        session_factory=session_factory,
    )
    fake_snap = MagicMock()
    fake_snap.summary.release_readiness_status = "ready_for_demo"
    fake_snap.summary.blocking_gate_count = 0
    fake_snap.summary.warning_gate_count = 2
    service.build_snapshot = MagicMock(return_value=fake_snap)  # type: ignore[method-assign]
    return service, audit_writer, event_bus


def test_recheck_default_emits_audit_and_bus(tmp_path: Path) -> None:
    """Backward-compat: ``recheck()`` with default ``emit=True`` writes audit + bus.

    Manual ``POST /reliability/recheck`` route (and any other caller
    that does not pass ``emit=``) keeps the A6 contract: one
    ``reliability.rechecked`` audit and one ``reliability.updated``
    bus event per call.
    """
    service, audit_writer, event_bus = _build_fake_reliability_service(tmp_path)
    session = MagicMock()

    service.recheck(session)  # default emit=True

    events = _read_audit_events(audit_writer)
    assert any(e["event_type"] == "reliability.rechecked" for e in events)
    drained = _drain_event_bus(event_bus)
    assert any(topic == "reliability.updated" for topic, _ in drained)


def test_recheck_emit_false_skips_audit_and_bus_but_persists_last_rechecked_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``emit=False`` → no audit, no bus, but ``last_rechecked_at`` updated (in-memory + DB).

    B4 scheduler-driven path: ``ReliabilityRecheckJob`` calls
    ``recheck(session, emit=False)`` and applies its own
    transition-only audit/bus policy. The DB write of
    ``last_rechecked_at`` must still happen so the post-restart
    timestamp stays current (A5 persistence contract —
    ``last_rechecked_at`` is the timestamp the operator trusts for
    "how fresh is the latest recheck").
    """
    from clay.db.repositories_runtime_state import ReliabilityStateRepository

    save_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        ReliabilityStateRepository,
        "save",
        lambda self, **kwargs: save_calls.append(kwargs),
    )

    # Build with session_factory=None so ``__init__`` does not try to
    # restore ``_last_rechecked_at`` from a MagicMock session (which
    # would clobber the ``None`` initial state with a MagicMock
    # attribute and break the assertion below). Assign the fake
    # session_factory post-construction so ``recheck`` still calls
    # ``ReliabilityStateRepository.save``.
    service, audit_writer, event_bus = _build_fake_reliability_service(tmp_path)
    service.session_factory = MagicMock()
    session = MagicMock()
    assert service._last_rechecked_at is None  # __init__ default

    service.recheck(session, emit=False)

    # No audit, no bus — emit path is fully suppressed.
    assert _read_audit_events(audit_writer) == []
    assert _drain_event_bus(event_bus) == []
    # _last_rechecked_at updated in-memory.
    assert service._last_rechecked_at is not None
    # ``ReliabilityStateRepository.save`` invoked with last_rechecked_at=.
    assert len(save_calls) == 1
    assert "last_rechecked_at" in save_calls[0]
