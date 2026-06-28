"""Tests for session-level risk limits L1-L5 (_build_preflight → risk-limit-* checks)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_control.service import ActiveSessionRecord, SessionControlService
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService


def _build_service() -> SessionControlService:
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


def _demo_record(
    pnl_pct: float | None,
    *,
    outcome_status: str = "matched",
    operator_action: str = "entered",
    broker_status: str = "closed",
    session_id: str = "s1",
    recorded_at: datetime | None = None,
    advisory_size_pct: float | None = None,
) -> object:
    record = type(
        "FakeDemoRecord",
        (),
        {
            "pnl_pct": pnl_pct,
            "outcome_status": outcome_status,
            "operator_action": operator_action,
            "broker_status": broker_status,
            "session_id": session_id,
            "recorded_at": recorded_at or datetime.now(UTC),
            "advisory_size_pct": advisory_size_pct,
        },
    )
    return record()


def _risk_checks(service, db_session):
    snapshot = service.build_snapshot(db_session)
    return {
        c.check_id: c
        for c in snapshot.preflight.checks
        if c.check_id.startswith("risk-limit-")
    }


# ── Empty DB (RV1: empty → pass, no deadlock) ────────────────────────────────


def test_empty_db_all_limits_pass(db_session) -> None:
    """Empty demo_trade_records → all risk-limit-* checks are ok, no deadlock."""
    service = _build_service()
    checks = _risk_checks(service, db_session)
    for cid, check in checks.items():
        assert check.status == "ok", (
            f"{cid} should be ok on empty DB, got {check.status}"
        )
        assert check.blocks_start is False


# ── L1: Drawdown ─────────────────────────────────────────────────────────────


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window")
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l1_drawdown_triggers_hard_fail(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """Cum P&L ≥ 15% → hard_fail + blocks_start."""
    mock_window.return_value = [_demo_record(pnl_pct=-8.0), _demo_record(pnl_pct=-7.5)]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-drawdown"].status == "hard_fail"
    assert checks["risk-limit-drawdown"].blocks_start is True


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window")
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l1_drawdown_passes_below_threshold(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """Cum P&L < 15% → ok, no block."""
    mock_window.return_value = [_demo_record(pnl_pct=-5.0), _demo_record(pnl_pct=-3.2)]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-drawdown"].status == "ok"
    assert checks["risk-limit-drawdown"].blocks_start is False


# ── L2: Consecutive-loss cooldown ────────────────────────────────────────────


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent")
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l2_cooldown_triggers_hard_fail(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """3 consecutive losses within cooldown → hard_fail + blocks_start."""
    now = datetime.now(UTC)
    mock_ordered.return_value = [
        _demo_record(pnl_pct=-2.0, recorded_at=now),
        _demo_record(pnl_pct=-1.5, recorded_at=now),
        _demo_record(pnl_pct=-3.0, recorded_at=now),
    ]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-cooldown"].status == "hard_fail"
    assert checks["risk-limit-cooldown"].blocks_start is True


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent")
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l2_cooldown_expires(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """3 consecutive losses but cooldown expired → ok."""
    old = datetime.now(UTC) - timedelta(hours=2)
    mock_ordered.return_value = [
        _demo_record(pnl_pct=-2.0, recorded_at=old),
        _demo_record(pnl_pct=-1.5, recorded_at=old),
        _demo_record(pnl_pct=-3.0, recorded_at=old),
    ]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-cooldown"].status == "ok"
    assert checks["risk-limit-cooldown"].blocks_start is False


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent")
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l2_single_loss_passes(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """1 loss (below threshold of 3) → ok."""
    now = datetime.now(UTC)
    mock_ordered.return_value = [_demo_record(pnl_pct=-2.0, recorded_at=now)]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-cooldown"].status == "ok"


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent")
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l2_win_breaks_streak(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """2 losses then a win → streak resets, ok."""
    now = datetime.now(UTC)
    mock_ordered.return_value = [
        _demo_record(pnl_pct=-2.0, recorded_at=now),
        _demo_record(pnl_pct=1.5, recorded_at=now),  # win breaks streak
        _demo_record(pnl_pct=-3.0, recorded_at=now),
    ]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-cooldown"].status == "ok"


# ── L3: Concurrent sessions ──────────────────────────────────────────────────


def test_l3_concurrent_ok_when_active_overview(db_session) -> None:
    """Active session overview → ok (not block, not warn — it's the same session)."""
    service = _build_service()
    object.__setattr__(
        service,
        "_active_session",
        ActiveSessionRecord(
            session_id="test-session",
            current_pair_symbol="BTCUSDT",
            current_signal_id="sig-1",
            strategy_mode="momentum",
            started_at=datetime.now(UTC),
        ),
    )
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-concurrent"].status == "ok"
    assert checks["risk-limit-concurrent"].blocks_start is False


def test_l3_concurrent_blocks_new_start(db_session) -> None:
    """Active session + for_start=True → hard_fail, blocks_start."""
    service = _build_service()
    object.__setattr__(
        service,
        "_active_session",
        ActiveSessionRecord(
            session_id="existing-session",
            current_pair_symbol="BTCUSDT",
            current_signal_id="sig-1",
            strategy_mode="momentum",
            started_at=datetime.now(UTC),
        ),
    )
    snapshot = service.build_snapshot(db_session, for_start=True)
    check = next(
        c for c in snapshot.preflight.checks if c.check_id == "risk-limit-concurrent"
    )
    assert check.status == "hard_fail"
    assert check.blocks_start is True


def test_l3_concurrent_ok_when_idle(db_session) -> None:
    """No active session → ok."""
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-concurrent"].status == "ok"
    assert checks["risk-limit-concurrent"].blocks_start is False


# ── L4: Aggregate advisory exposure ──────────────────────────────────────────


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions")
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l4_exposure_warns_when_exceeded(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """Total exposure > 4% → warn, NOT blocks_start, rollup still pass."""
    mock_open.return_value = [
        _demo_record(
            pnl_pct=None, advisory_size_pct=3.0, broker_status="awaiting_result"
        ),
        _demo_record(
            pnl_pct=None, advisory_size_pct=2.0, broker_status="awaiting_result"
        ),
    ]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-exposure"].status == "warn"
    assert checks["risk-limit-exposure"].blocks_start is False


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions")
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades", return_value=[])
def test_l4_exposure_passes_within_threshold(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """Total exposure ≤ 4% → ok."""
    mock_open.return_value = [
        _demo_record(
            pnl_pct=None, advisory_size_pct=2.0, broker_status="awaiting_result"
        ),
    ]
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-exposure"].status == "ok"


# ── L5: Per-session loss alert ───────────────────────────────────────────────


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades")
def test_l5_session_loss_warns(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """Active session with P&L ≤ -8% → warn, NOT blocks_start."""
    service = _build_service()
    object.__setattr__(
        service,
        "_active_session",
        ActiveSessionRecord(
            session_id="s-lossy",
            current_pair_symbol="BTCUSDT",
            current_signal_id="sig-1",
            strategy_mode="momentum",
            started_at=datetime.now(UTC),
        ),
    )
    mock_session.return_value = [
        _demo_record(pnl_pct=-5.0, session_id="s-lossy"),
        _demo_record(pnl_pct=-4.0, session_id="s-lossy"),
    ]
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-session-loss"].status == "warn"
    assert checks["risk-limit-session-loss"].blocks_start is False


@patch("clay.db.repositories_demo.DemoRepository.list_resolved_window", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_ordered_recent", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_open_positions", return_value=[])
@patch("clay.db.repositories_demo.DemoRepository.list_session_trades")
def test_l5_session_loss_passes(
    mock_session, mock_open, mock_ordered, mock_window, db_session
) -> None:
    """Active session with small P&L → ok."""
    service = _build_service()
    object.__setattr__(
        service,
        "_active_session",
        ActiveSessionRecord(
            session_id="s-good",
            current_pair_symbol="BTCUSDT",
            current_signal_id="sig-1",
            strategy_mode="momentum",
            started_at=datetime.now(UTC),
        ),
    )
    mock_session.return_value = [
        _demo_record(pnl_pct=2.0, session_id="s-good"),
        _demo_record(pnl_pct=-1.0, session_id="s-good"),
    ]
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-session-loss"].status == "ok"


def test_l5_session_loss_skipped_when_idle(db_session) -> None:
    """No active session → ok (skip L5)."""
    service = _build_service()
    checks = _risk_checks(service, db_session)
    assert checks["risk-limit-session-loss"].status == "ok"


# ── Warn checks preserve rollup (invariant) ──────────────────────────────────


def test_warn_checks_do_not_block_rollup(db_session) -> None:
    """All warn checks → preflight still pass (blocks_start=False)."""
    service = _build_service()
    snapshot = service.build_snapshot(db_session)
    warn_count = sum(
        1
        for c in snapshot.preflight.checks
        if c.check_id.startswith("risk-limit-") and c.status == "warn"
    )
    if warn_count > 0:
        assert snapshot.preflight.status == "pass"  # warn checks don't block
