"""S-REPLAY-6: soak + recalibration + risk-limit block (ADR-024).

Single soaked harness run → ≥30 sessions, p/b recalibrated,
live frozen, isolation under load.
Separate minimal test for L2 hard-block.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.core.clock import VirtualClock
from clay.db.repositories_demo import DEFAULT_READ_SCOPE, DemoRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.replay.harness import ReplayHarness
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_control.service import SessionControlService
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService

import pytest

START_AS_OF = datetime(2026, 6, 2, 0, 0, 0, tzinfo=UTC)
SYMBOL = "SOLUSDT"
TF = "1h"
SOAK_BARS = 2000


def _build_bundle(tmp_path: Any, clock: VirtualClock) -> dict[str, Any]:
    registry = ServiceRegistry()
    for sid, stype, crit, policy in [
        ("control-api", "api", ServiceCriticality.CRITICAL, "always-on"),
        ("session-scheduler", "scheduler", ServiceCriticality.IMPORTANT, "always-on"),
        ("pair-scanner", "worker", ServiceCriticality.OPTIONAL, "on-demand"),
    ]:
        registry.register(sid, stype, crit, policy)
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    registry.update_status("session-scheduler", ServiceStatus.HEALTHY)
    registry.update_status("pair-scanner", ServiceStatus.STOPPED)

    runtime_manager = RuntimeManager(registry=registry)
    preflight_service = PreflightService(registry)
    xdg = XdgPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
    )
    config_loader = ConfigLoader(xdg)
    config_loader.ensure_default_configs()
    config_loader.load_all()
    audit_writer = AuditWriter(config_loader.paths.state_dir)
    event_bus = EventBus()

    ai_control = AIControlService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        audit_writer=audit_writer,
        event_bus=event_bus,
        clock=clock,
    )
    signal_engine = SignalEngineService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        config_loader=config_loader,
        ai_control_service=ai_control,
        clock=clock,
    )
    workspace = WorkspaceService(
        runtime_manager=runtime_manager,
        preflight_service=preflight_service,
        registry=registry,
        signal_engine_service=signal_engine,
        clock=clock,
    )
    session_control = SessionControlService(
        runtime_manager=runtime_manager,
        signal_engine_service=signal_engine,
        ai_control_service=ai_control,
        workspace_service=workspace,
        audit_writer=audit_writer,
        event_bus=event_bus,
        config_loader=ConfigLoader(),
        clock=clock,
    )
    demo_trading = DemoTradingService(
        session_control_service=session_control,
        workspace_service=workspace,
        audit_writer=audit_writer,
        event_bus=event_bus,
        clock=clock,
    )
    return {
        "session_control": session_control,
        "signal_engine": signal_engine,
        "demo_trading": demo_trading,
        "clock": clock,
    }


def _seed_market_data(
    session: Any, clock: VirtualClock, *, n_bars: int = SOAK_BARS
) -> None:
    market_repo = MarketRepository(session)
    ops_repo = OpsRepository(session)
    bar_start = clock.now() - timedelta(hours=n_bars)
    for i in range(n_bars):
        bar_close = bar_start + timedelta(hours=i + 1)
        bar_open = bar_start + timedelta(hours=i)
        is_up = i % 2 == 1
        market_repo.upsert_market_bars(
            [
                {
                    "symbol": SYMBOL,
                    "timeframe": TF,
                    "open": 100.0,
                    "high": 105.0 if is_up else 102.0,
                    "low": 98.0 if is_up else 95.0,
                    "close": 105.0 if is_up else 95.0,
                    "volume": 1000.0,
                    "quote_volume": 100000.0,
                    "source": "binance_spot",
                    "bar_open_time": bar_open,
                    "bar_close_time": bar_close,
                }
            ]
        )
        market_repo.upsert_freshness_status(
            symbol=SYMBOL,
            timeframe=TF,
            source="binance_spot",
            freshness_state="fresh",
            evaluated_at=bar_open,
            latest_bar_open_time=bar_open,
            is_stale=False,
        )
    ops_repo.record_connector_status(
        connector_id="demo-news",
        connector_type="news",
        status="healthy",
        observed_at=clock.now(),
    )
    ops_repo.record_connector_status(
        connector_id="demo-sentiment",
        connector_type="sentiment",
        status="healthy",
        observed_at=clock.now(),
    )
    session.commit()


def _seed_baseline_live(session: Any, clock: VirtualClock) -> None:
    demo_repo = DemoRepository(session)
    clock_now = clock.now()
    for i in range(20):
        demo_repo.create_trade_record(
            {
                "session_id": f"baseline-session-{i}",
                "signal_id": f"bl-sig-{i}",
                "symbol": SYMBOL,
                "executed_symbol": SYMBOL,
                "operator_action": "entered",
                "recorded_at": clock_now - timedelta(days=30 - i),
                "broker_status": "closed",
                "entry_price": 90.0 + i,
                "exit_price": 93.0 + i,
                "pnl_pct": 3.0 + i,
                "observed_at": clock_now - timedelta(days=30 - i) + timedelta(hours=1),
                "outcome_status": "matched",
                "source": "baseline",
            }
        )
    demo_repo.create_trade_record(
        {
            "session_id": "live-session",
            "signal_id": "live-sig",
            "symbol": SYMBOL,
            "executed_symbol": SYMBOL,
            "operator_action": "entered",
            "recorded_at": clock_now - timedelta(days=1),
            "broker_status": "closed",
            "entry_price": 95.0,
            "exit_price": 97.0,
            "pnl_pct": 2.1,
            "observed_at": clock_now - timedelta(days=1) + timedelta(hours=2),
            "outcome_status": "matched",
            "source": "live",
        }
    )
    session.commit()


TEST_SET = False
TEST_RESULTS: dict[str, Any] = {}


class TestSoak:
    @pytest.mark.slow
    def test_full_soak(self, db_session: Any, tmp_path: Any) -> None:
        """Single soak run → verify ≥30 sessions, recalibration, live frozen, isolation."""
        global TEST_SET, TEST_RESULTS

        clock = VirtualClock(start=START_AS_OF)
        _seed_market_data(db_session, clock, n_bars=SOAK_BARS)
        _seed_baseline_live(db_session, clock)
        demo_repo = DemoRepository(db_session)

        # ── Snapshot pre-soak state ──────────────────────────────────

        bundle = _build_bundle(tmp_path / "soak", clock)
        se = bundle["signal_engine"]
        sc = bundle["session_control"]
        risk_config = ConfigLoader().load_scope("risk")

        default_before = se._compute_sizing_stats(
            db_session, risk_config, source_scope=DEFAULT_READ_SCOPE
        )
        replay_before = se._compute_sizing_stats(
            db_session, risk_config, source_scope={"replay"}
        )
        bl_before = {
            r.id: (r.pnl_pct, r.outcome_status, r.source)
            for r in demo_repo.list_all_trade_records(source_scope={"baseline", "live"})
        }

        # ── Run soak ─────────────────────────────────────────────────
        # Single VirtualClock for both services and harness — clock-seam
        # invariant (M223): all subsystems share the same time source.
        harness = ReplayHarness(
            session=db_session,
            clock=clock,
            session_control=sc,
            signal_engine=se,
            demo_trading=bundle["demo_trading"],
        )
        summary = harness.run(SYMBOL, TF)

        # ── 1. Soak ≥30 sessions ─────────────────────────────────────

        assert summary.bars_processed >= SOAK_BARS - 10, (
            f"processed {summary.bars_processed}/{SOAK_BARS} bars"
        )
        assert summary.sessions_started >= 30, (
            f"sessions_started={summary.sessions_started}, need ≥30"
        )
        assert summary.trades_resolved == len(summary.trades), (
            "all started trades must resolve"
        )
        for t in summary.trades:
            assert t.outcome_status == "matched"

        replay_sessions = summary.sessions_started
        replay_resolved = summary.trades_resolved

        # ── 2. Recalibration p/b in replay-scope ─────────────────────

        replay_after = se._compute_sizing_stats(
            db_session, risk_config, source_scope={"replay"}
        )

        assert replay_before[0] == 0.0, (
            f"pre-soak replay p must be 0, got {replay_before[0]}"
        )
        assert replay_after[0] > 0.0, (
            f"post-soak replay p must be > 0, got {replay_after[0]}"
        )
        assert replay_after[0] != replay_before[0], "replay p unchanged after soak"
        assert replay_before[1] == 1.0, (
            f"pre-soak replay b must be fallback 1.0, got {replay_before[1]}"
        )

        # ── 3. LIVE p/b frozen ──────────────────────────────────────

        default_after = se._compute_sizing_stats(
            db_session, risk_config, source_scope=DEFAULT_READ_SCOPE
        )
        assert default_before == default_after, (
            f"default-scope p/b CHANGED!\n"
            f"  before={default_before}\n  after={default_after}"
        )

        # ── 4. L2 hard-block not tested in soak (needs aligned clock) ──

        # ── 5. Isolation under load ─────────────────────────────────

        bl_after = {
            r.id: (r.pnl_pct, r.outcome_status, r.source)
            for r in demo_repo.list_all_trade_records(source_scope={"baseline", "live"})
        }
        assert bl_before == bl_after, "baseline/live records changed after soak"

        replay_ids = {
            r.id for r in demo_repo.list_all_trade_records(source_scope={"replay"})
        }
        assert len(replay_ids) >= 30, (
            f"expected ≥30 replay records, got {len(replay_ids)}"
        )
        default_ids = {r.id for r in demo_repo.list_all_trade_records()}
        assert default_ids.isdisjoint(replay_ids), "default scope leaks replay records"

        # ── Store results for report ─────────────────────────────────

        TEST_SET = True
        TEST_RESULTS = {
            "sessions_started": replay_sessions,
            "trades_resolved": replay_resolved,
            "replay_p_b_before": {
                "p": replay_before[0],
                "b": replay_before[1],
                "ev": replay_before[2],
            },
            "replay_p_b_after": {
                "p": replay_after[0],
                "b": replay_after[1],
                "ev": replay_after[2],
            },
            "default_p_b_before": {
                "p": default_before[0],
                "b": default_before[1],
                "ev": default_before[2],
            },
            "default_p_b_after": {
                "p": default_after[0],
                "b": default_after[1],
                "ev": default_after[2],
            },
            "replay_record_count": len(replay_ids),
            "replay_wins": sum(
                1 for t in summary.trades if t.pnl_pct and t.pnl_pct > 0
            ),
            "replay_losses": sum(
                1 for t in summary.trades if t.pnl_pct and t.pnl_pct < 0
            ),
        }

    # ── 4. L2 hard-block (separate, self-contained) ─────────────────

    def test_l2_loss_streak_blocks_replay_session(
        self, db_session: Any, tmp_path: Any
    ) -> None:
        """Self-contained L2 proof: 3 replay losses → start_session raises ValueError."""
        clock = VirtualClock(start=START_AS_OF)
        _seed_market_data(db_session, clock, n_bars=100)
        _seed_baseline_live(db_session, clock)
        demo_repo = DemoRepository(db_session)

        # Seed 3 consecutive losing replay trades within cooldown window
        now = clock.now()
        for i in range(3):
            demo_repo.create_trade_record(
                {
                    "session_id": f"l2-loss-{i}",
                    "signal_id": "l2-loss",
                    "symbol": SYMBOL,
                    "executed_symbol": SYMBOL,
                    "operator_action": "entered",
                    "recorded_at": now - timedelta(minutes=20 - i * 5),
                    "broker_status": "closed",
                    "entry_price": 100.0,
                    "exit_price": 99.4,
                    "pnl_pct": -0.6,
                    "observed_at": now
                    - timedelta(minutes=20 - i * 5)
                    + timedelta(minutes=2),
                    "outcome_status": "matched",
                    "source": "replay",
                }
            )
        demo_repo.create_trade_record(
            {
                "session_id": "l2-win",
                "signal_id": "l2-win",
                "symbol": SYMBOL,
                "executed_symbol": SYMBOL,
                "operator_action": "entered",
                "recorded_at": now - timedelta(hours=2),
                "broker_status": "closed",
                "entry_price": 100.0,
                "exit_price": 101.2,
                "pnl_pct": 1.2,
                "observed_at": now - timedelta(hours=2) + timedelta(minutes=5),
                "outcome_status": "matched",
                "source": "replay",
            }
        )
        db_session.commit()

        bundle = _build_bundle(tmp_path / "l2", clock)
        sc = bundle["session_control"]

        # Prove: replay scope has 3+ losses
        losses = sum(
            1
            for r in demo_repo.list_all_trade_records(source_scope={"replay"})
            if r.pnl_pct and r.pnl_pct < 0
        )
        assert losses >= 3, f"need ≥3 losses in replay scope, got {losses}"

        # Direct proof: build_snapshot(for_start=True) shows L2 hard_fail
        pf = sc.build_snapshot(db_session, for_start=True, source_scope={"replay"})
        l2_check = next(
            (c for c in pf.preflight.checks if c.check_id == "risk-limit-cooldown"),
            None,
        )
        assert l2_check is not None, "L2 check not found in preflight"
        assert l2_check.status == "hard_fail", (
            f"L2 should be hard_fail on 3-loss streak, got {l2_check.status}"
        )
        assert l2_check.blocks_start is True

        # start_session raises ValueError (hard-block)
        with pytest.raises(ValueError):
            sc.start_session(db_session, source_scope={"replay"})

    def test_l2_cooldown_guard_detects_clock_desync(
        self, db_session: Any, tmp_path: Any
    ) -> None:
        """Clock desync guard: recorded_at ahead of clock.now() → ValueError.

        Regression for the S-REPLAY-6 bug: two VirtualClock instances
        caused negative elapsed_min which silently blocked replay sessions
        via L2 cooldown hard_fail.
        """
        services_clock = VirtualClock(start=START_AS_OF)
        trades_clock = VirtualClock(start=START_AS_OF)
        trades_clock.tick(timedelta(hours=2))  # trades in the future

        _seed_market_data(db_session, services_clock, n_bars=100)

        demo_repo = DemoRepository(db_session)
        for i in range(3):
            demo_repo.create_trade_record(
                {
                    "session_id": f"desync-loss-{i}",
                    "signal_id": "desync-loss",
                    "symbol": SYMBOL,
                    "executed_symbol": SYMBOL,
                    "operator_action": "entered",
                    "recorded_at": trades_clock.now(),
                    "broker_status": "closed",
                    "entry_price": 100.0,
                    "exit_price": 99.4,
                    "pnl_pct": -0.6,
                    "observed_at": trades_clock.now(),
                    "outcome_status": "matched",
                    "source": "replay",
                }
            )
        db_session.commit()

        bundle = _build_bundle(tmp_path / "desync", services_clock)
        sc = bundle["session_control"]

        with pytest.raises(ValueError, match="clock desync"):
            sc.build_snapshot(db_session, for_start=True, source_scope={"replay"})
