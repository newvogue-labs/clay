"""Integration tests for ReplayHarness (S-REPLAY-5 — ADR-024).

Tests:
  1. RetroResolver unit: forward buffer guard, stop/target logic
  2. End-to-end: replay sessions through real service layer
  3. Source isolation: replay records carry source='replay'
  4. Baseline/live isolation: default scope does not leak replay records
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.core.clock import VirtualClock
from clay.db.models_market import MarketBar
from clay.db.repositories_demo import DemoRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.replay.harness import FORWARD_BUFFER_BARS, ForwardBufferError, RetroResolver
from clay.runtime.manager import RuntimeManager
from clay.services.models import ServiceCriticality, ServiceStatus
from clay.services.registry import ServiceRegistry
from clay.session_control.service import SessionControlService
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService

START_AS_OF = datetime(2026, 6, 10, 0, 0, 0, tzinfo=UTC)
SYMBOL = "SOLUSDT"
TF = "1h"


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


def _seed_data(session: Any, clock: VirtualClock, *, n_bars: int = 120) -> None:
    market_repo = MarketRepository(session)
    ops_repo = OpsRepository(session)
    demo_repo = DemoRepository(session)
    clock_now = clock.now()

    bar_start = clock_now - timedelta(hours=n_bars)
    for i in range(n_bars):
        bar_close = bar_start + timedelta(hours=i + 1)
        bar_open = bar_start + timedelta(hours=i)
        market_repo.upsert_market_bars(
            [
                {
                    "symbol": SYMBOL,
                    "timeframe": TF,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0 if i % 2 == 0 else 98.0,
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
        observed_at=clock_now,
    )
    ops_repo.record_connector_status(
        connector_id="demo-sentiment",
        connector_type="sentiment",
        status="healthy",
        observed_at=clock_now,
    )

    for i in range(3):
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


# ── RetroResolver unit ─────────────────────────────────────────────────────


def _make_bar(
    *,
    close: float,
    low: float,
    high: float,
    bar_close_time: datetime,
    symbol: str = SYMBOL,
) -> MarketBar:
    return MarketBar(
        symbol=symbol,
        timeframe=TF,
        close=close,
        low=low,
        high=high,
        bar_close_time=bar_close_time,
        bar_open_time=bar_close_time - timedelta(hours=1),
    )


class TestRetroResolver:
    def test_insufficient_forward_bars_raises(self) -> None:
        bars = [_make_bar(close=100, low=99, high=101, bar_close_time=START_AS_OF)]
        with pytest.raises(ForwardBufferError, match="Need 48 forward bars"):
            RetroResolver.resolve(0, bars, stop_price=98.0, target_price=103.0)

    def test_empty_bars_raises(self) -> None:
        with pytest.raises(ForwardBufferError, match="Need 48 forward bars"):
            RetroResolver.resolve(0, [], stop_price=98.0, target_price=103.0)

    def test_stop_hit_returns_loss(self) -> None:
        entry = START_AS_OF
        bars = [
            _make_bar(
                close=100, low=99, high=101, bar_close_time=entry + timedelta(hours=i)
            )
            for i in range(FORWARD_BUFFER_BARS + 5)
        ]
        bars[4].low = 97.5  # stop at 98.0
        result = RetroResolver.resolve(0, bars, stop_price=98.0, target_price=103.0)
        assert result.outcome_status == "matched"
        assert result.reason == "stop_hit"
        assert result.pnl_pct == -2.0
        assert result.exit_price == 98.0

    def test_target_hit_returns_win(self) -> None:
        entry = START_AS_OF
        bars = [
            _make_bar(
                close=100, low=99, high=101, bar_close_time=entry + timedelta(hours=i)
            )
            for i in range(FORWARD_BUFFER_BARS + 5)
        ]
        bars[6].high = 103.5  # target at 103.0
        result = RetroResolver.resolve(0, bars, stop_price=98.0, target_price=103.0)
        assert result.outcome_status == "matched"
        assert result.reason == "target_hit"
        assert result.pnl_pct == 3.0
        assert result.exit_price == 103.0

    def test_stop_hit_before_target(self) -> None:
        entry = START_AS_OF
        bars = [
            _make_bar(
                close=100, low=99, high=101, bar_close_time=entry + timedelta(hours=i)
            )
            for i in range(FORWARD_BUFFER_BARS + 5)
        ]
        bars[3].low = 97.5  # stop first
        bars[6].high = 103.5  # target later
        result = RetroResolver.resolve(0, bars, stop_price=98.0, target_price=103.0)
        assert result.reason == "stop_hit"
        assert result.pnl_pct == -2.0

    def test_target_hit_before_stop(self) -> None:
        entry = START_AS_OF
        bars = [
            _make_bar(
                close=100, low=99, high=101, bar_close_time=entry + timedelta(hours=i)
            )
            for i in range(FORWARD_BUFFER_BARS + 5)
        ]
        bars[2].high = 103.5  # target first
        bars[3].low = 97.5  # stop later
        result = RetroResolver.resolve(0, bars, stop_price=98.0, target_price=103.0)
        assert result.reason == "target_hit"
        assert result.pnl_pct == 3.0

    def test_no_hit_within_buffer_raises(self) -> None:
        entry = START_AS_OF
        bars = [
            _make_bar(
                close=100, low=99, high=101, bar_close_time=entry + timedelta(hours=i)
            )
            for i in range(FORWARD_BUFFER_BARS + 5)
        ]
        with pytest.raises(ForwardBufferError, match="did not hit stop"):
            RetroResolver.resolve(0, bars, stop_price=98.0, target_price=103.0)


# ── Integration tests ──────────────────────────────────────────────────────


class TestReplayHarnessIntegration:
    def test_end_to_end_replay_sessions(self, db_session: Any, tmp_path: Any) -> None:
        clock = VirtualClock(start=START_AS_OF)
        bundle = _build_bundle(tmp_path, clock)
        _seed_data(db_session, clock, n_bars=120)

        from clay.replay.harness import ReplayHarness

        harness = ReplayHarness(
            session=db_session,
            clock=clock,
            session_control=bundle["session_control"],
            signal_engine=bundle["signal_engine"],
            demo_trading=bundle["demo_trading"],
        )
        summary = harness.run(SYMBOL, TF)

        assert summary.bars_processed >= 100
        assert summary.sessions_started >= 1, "should trigger at least 1 replay session"
        assert summary.trades_resolved >= 1
        for trade in summary.trades:
            assert trade.outcome_status == "matched"
            assert trade.pnl_pct in (-0.6, 1.2)
            assert trade.exit_price is not None
            assert trade.session_id != ""

    def test_replay_records_have_source_replay(
        self, db_session: Any, tmp_path: Any
    ) -> None:
        clock = VirtualClock(start=START_AS_OF)
        bundle = _build_bundle(tmp_path, clock)
        _seed_data(db_session, clock, n_bars=120)

        from clay.replay.harness import ReplayHarness

        harness = ReplayHarness(
            session=db_session,
            clock=clock,
            session_control=bundle["session_control"],
            signal_engine=bundle["signal_engine"],
            demo_trading=bundle["demo_trading"],
        )
        harness.run(SYMBOL, TF)

        repo = DemoRepository(db_session)
        all_replay = repo.list_all_trade_records(source_scope={"replay"})
        assert len(all_replay) >= 1
        assert all(r.source == "replay" for r in all_replay)

    def test_deterministic_output_with_mid_window_as_of(
        self, db_session: Any, tmp_path: Any
    ) -> None:
        """Mid-window as_of (Jun 10, not at the tail) proves deterministic
        signal→trade→resolve pipeline independent of data freshness.

        Determinism is proven by construction:
        - VirtualClock provides fixed time (M223)
        - build_shortlist_metrics now uses clock.now() (not wall-clock)
        - RetroResolver uses signal-faithful stop/target levels
        - Source scope isolates replay records (M225)

        This test asserts the output has the expected deterministic structure
        and that running the *same* as_of twice produces identical trades.
        """
        as_of = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)
        clock = VirtualClock(start=as_of)
        bundle = _build_bundle(tmp_path, clock)
        _seed_data(db_session, clock, n_bars=200)

        from clay.replay.harness import ReplayHarness

        harness = ReplayHarness(
            session=db_session,
            clock=clock,
            session_control=bundle["session_control"],
            signal_engine=bundle["signal_engine"],
            demo_trading=bundle["demo_trading"],
        )
        summary = harness.run(SYMBOL, TF)

        assert summary.bars_processed >= 100, "should process most seeded bars"
        assert summary.sessions_started >= 1, "should start at least 1 session"
        assert summary.trades_resolved == len(summary.trades), (
            "all trades must be resolved"
        )
        for t in summary.trades:
            assert t.pnl_pct in (-0.6, 1.2), (
                f"pnl must be stop(-0.6%) or target(1.2%), got {t.pnl_pct}"
            )
            assert t.outcome_status == "matched"

    def test_deterministic_identity_double_run(
        self, db_session: Any, tmp_path: Any
    ) -> None:
        """Same as_of → same trades (true identity, not just shape).

        Two fully independent harness instances (separate services, separate
        VirtualClocks) process the same market data. All trade fields must
        match pairwise.
        """
        as_of = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)
        seed_clock = VirtualClock(start=as_of)
        _seed_data(db_session, seed_clock, n_bars=200)

        from clay.replay.harness import ReplayHarness

        def _run(run_dir: Any) -> Any:
            clock = VirtualClock(start=as_of)
            bundle = _build_bundle(run_dir, clock)
            harness = ReplayHarness(
                session=db_session,
                clock=clock,
                session_control=bundle["session_control"],
                signal_engine=bundle["signal_engine"],
                demo_trading=bundle["demo_trading"],
            )
            return harness.run(SYMBOL, TF)

        run1 = _run(tmp_path / "r1")
        run2 = _run(tmp_path / "r2")

        assert len(run1.trades) == len(run2.trades), (
            f"trade count differs: run1={len(run1.trades)}, run2={len(run2.trades)}"
        )
        assert run1.bars_processed == run2.bars_processed
        assert run1.sessions_started == run2.sessions_started
        assert run1.trades_resolved == run2.trades_resolved
        for t1, t2 in zip(run1.trades, run2.trades):
            assert t1.pnl_pct == t2.pnl_pct, (
                f"pnl mismatch: {t1.pnl_pct} vs {t2.pnl_pct} at {t1.entry_bar_time}"
            )
            assert t1.reason == t2.reason
            assert t1.exit_price == t2.exit_price
            assert t1.outcome_status == t2.outcome_status

    def test_list_latest_bars_live_path(self, db_session: Any) -> None:
        """Bug#1 regression: list_latest_bars with default scope returns
        properly deduplicated bars for the live shortlist."""
        market_repo = MarketRepository(db_session)
        clock = VirtualClock(start=datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC))
        _seed_data(db_session, clock, n_bars=50)

        bars = market_repo.list_latest_bars(limit=10)
        assert len(bars) == 1, (
            f"expected 1 deduplicated bar (SOLUSDT/1h), got {len(bars)}"
        )
        assert bars[0].symbol == SYMBOL
        assert bars[0].timeframe == TF

    def test_isolation_baseline_live_untouched(
        self, db_session: Any, tmp_path: Any
    ) -> None:
        clock = VirtualClock(start=START_AS_OF)
        bundle = _build_bundle(tmp_path, clock)
        _seed_data(db_session, clock, n_bars=120)

        repo = DemoRepository(db_session)
        before = {
            r.id: (r.pnl_pct, r.outcome_status, r.source)
            for r in repo.list_all_trade_records(source_scope={"baseline", "live"})
        }

        from clay.replay.harness import ReplayHarness

        harness = ReplayHarness(
            session=db_session,
            clock=clock,
            session_control=bundle["session_control"],
            signal_engine=bundle["signal_engine"],
            demo_trading=bundle["demo_trading"],
        )
        harness.run(SYMBOL, TF)

        after = {
            r.id: (r.pnl_pct, r.outcome_status, r.source)
            for r in repo.list_all_trade_records(source_scope={"baseline", "live"})
        }
        assert before == after, "baseline/live records changed after replay"

        replay_ids = {
            r.id for r in repo.list_all_trade_records(source_scope={"replay"})
        }
        assert len(replay_ids) >= 1

        default_ids = {r.id for r in repo.list_all_trade_records()}
        assert default_ids.isdisjoint(replay_ids), (
            "default scope leaks replay records into baseline/live view"
        )
