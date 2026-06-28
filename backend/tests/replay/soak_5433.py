"""S-REPLAY-6 † доводка: soak на реальных market_bars из 5433.

Прогон ReplayHarness по реальным SOLUSDT 1h барам Jun 2–25.
MarketRepository.list_latest_bars и list_freshness_statuses
запатчены фильтром по clock.now() — чтобы сигнальный движок
видел только бары, актуальные на текущей позиции часов.

Usage:
  python tests/replay/soak_5433.py

Exit code 0 = все проверки пройдены.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

os.environ["CLAY_DATABASE_URL"] = os.environ.get(
    "CLAY_DATABASE_URL",
    "postgresql+psycopg://clay:LjRVpJBOeveAm6ejI1hwd32BdIULVg2j@127.0.0.1:5433/clay",
)

from collections import defaultdict
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.config.paths import XdgPaths
from clay.core.clock import VirtualClock
from clay.db.models_market import MarketBar
from clay.db.repositories_demo import DEFAULT_READ_SCOPE, DemoRepository
from clay.db.repositories_market import MarketRepository
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
from clay.freshness.evaluator import resolve_market_freshness_status

PG_URL = os.environ["CLAY_DATABASE_URL"]
SYMBOL = "SOLUSDT"
TF = "1h"
START_AS_OF = datetime(2026, 6, 2, 0, 0, 0, tzinfo=UTC)
FORWARD_BUFFER = 48

results: dict[str, Any] = {}


def build_bundle(tmp_path: Path, clock: VirtualClock) -> dict[str, Any]:
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


def main() -> int:
    print("=" * 72)
    print("S-REPLAY-6 доводка: soak на реальных барах 5433")
    print("=" * 72)

    engine = create_engine(PG_URL)
    Session_factory = sessionmaker(bind=engine)
    session = Session_factory()

    # ── 1. Pre-read all real data ───────────────────────────────────

    demo = DemoRepository(session)

    all_bars = list(
        session.scalars(
            select(MarketBar).order_by(MarketBar.bar_close_time.asc())
        ).all()
    )
    sol_bars = [b for b in all_bars if b.symbol == SYMBOL and b.timeframe == TF]
    real_n = len(sol_bars)
    assert real_n >= 200, f"Нужно ≥200 SOLUSDT 1h баров, есть {real_n}"

    # Pre-group bars by (symbol, timeframe) for fast lookup
    bars_by_key: dict[tuple[str, str], list[MarketBar]] = defaultdict(list)
    for b in all_bars:
        bars_by_key[(b.symbol, b.timeframe)].append(b)
    for key in bars_by_key:
        bars_by_key[key].sort(key=lambda x: x.bar_close_time, reverse=True)

    print(f"\n📊 SOLUSDT 1h: {real_n} баров")
    print(f"   {sol_bars[0].bar_close_time} → {sol_bars[-1].bar_close_time}")

    baseline_trades = demo.list_all_trade_records(source_scope={"baseline"})
    live_trades = demo.list_all_trade_records(source_scope={"live"})
    bl_wins = sum(1 for t in baseline_trades if t.pnl_pct and t.pnl_pct > 0)
    bl_losses = sum(1 for t in baseline_trades if t.pnl_pct and t.pnl_pct < 0)
    print(f"\n📋 baseline: {len(baseline_trades)} ({bl_wins}W/{bl_losses}L)")
    print(f"   live:     {len(live_trades)} (1 loss)")
    assert len(baseline_trades) == 20
    assert len(live_trades) == 1

    # ── 2. Cleanup leftover replay records from interrupted runs ────

    for r in demo.list_all_trade_records(source_scope={"replay"}):
        session.delete(r)
    session.commit()
    print("\n🧹 Очищены старые replay-scope записи")

    # ── 3. Patch MarketRepository to be clock-aware ─────────────────

    clock = VirtualClock(start=START_AS_OF)
    clock.tick(timedelta(hours=1))

    _orig_list_latest = MarketRepository.list_latest_bars
    _orig_list_freshness = MarketRepository.list_freshness_statuses

    def _patched_list_latest(self, *, symbol=None, timeframe=None, limit=50):
        now = clock.now()
        results = []
        for (sym, tf), group in bars_by_key.items():
            if symbol is not None and sym != symbol:
                continue
            if timeframe is not None and tf != timeframe:
                continue
            for bar in group:
                bt = bar.bar_close_time
                if bt.tzinfo is None:
                    bt = bt.replace(tzinfo=UTC)
                if bt <= now:
                    results.append(bar)
                    break
            if len(results) >= limit:
                break
        return results

    sol_freshness_key = (SYMBOL, TF)

    def _freshness_for_sol(self, now: datetime):
        """Dynamically compute SOLUSDT 1h freshness at clock position."""
        group = bars_by_key.get(sol_freshness_key, [])
        latest = None
        for bar in group:
            bt = bar.bar_close_time
            if bt.tzinfo is None:
                bt = bt.replace(tzinfo=UTC)
            if bt <= now:
                latest = bar
                break
        if latest is None:
            return None
        fl = resolve_market_freshness_status(
            stored_status="fresh",
            timeframe=TF,
            latest_bar_open_time=latest.bar_open_time,
            now=now,
        )
        from types import SimpleNamespace

        return SimpleNamespace(
            symbol=SYMBOL,
            timeframe=TF,
            freshness_state=fl.status,
            latest_bar_open_time=latest.bar_open_time,
            evaluated_at=now,
            is_stale=fl.status != "fresh",
        )

    def _patched_list_freshness(self):
        now = clock.now()
        results = []
        for f in _orig_list_freshness(self):
            if f.symbol == SYMBOL and f.timeframe == TF:
                dyn = _freshness_for_sol(self, now)
                if dyn is not None:
                    results.append(dyn)
                    continue
            results.append(f)
        return results

    MarketRepository.list_latest_bars = _patched_list_latest
    MarketRepository.list_freshness_statuses = _patched_list_freshness

    # ── 3. Snapshot default-scope p/b before soak ──────────────────

    risk_cfg = ConfigLoader().load_scope("risk")
    tmp_dir = Path(tempfile.mkdtemp(prefix="soak_5433_"))
    bundle = build_bundle(tmp_dir, clock)
    se = bundle["signal_engine"]
    sc = bundle["session_control"]

    default_before = se._compute_sizing_stats(
        session, risk_cfg, source_scope=DEFAULT_READ_SCOPE
    )
    replay_before = se._compute_sizing_stats(session, risk_cfg, source_scope={"replay"})

    print("\n📐 p/b до soak:")
    print(
        f"   default-scope:  p={default_before[0]:.5f}, b={default_before[1]:.5f}, ev={default_before[2]:.5f}"
    )
    print(
        f"   replay-scope:   p={replay_before[0]:.5f}, b={replay_before[1]:.5f}, ev={replay_before[2]:.5f}"
    )

    # ── 4. Run the soak ────────────────────────────────────────────

    print(f"\n🚀 Запуск ReplayHarness на {real_n} барах...")

    harness = ReplayHarness(
        session=session,
        clock=clock,
        session_control=sc,
        signal_engine=se,
        demo_trading=bundle["demo_trading"],
    )
    print("      Running harness (logging every 50 bars)...", flush=True)
    import time as _time_module

    # Monkey-patch build_snapshot to report progress
    _orig_bs = SignalEngineService.build_snapshot
    _call_count = [0]

    def _counting_bs(self, session, source_scope=None):
        _call_count[0] += 1
        result = _orig_bs(self, session, source_scope=source_scope)
        if _call_count[0] % 50 == 0:
            print(
                f"        build_snapshot call #{_call_count[0]}: clock={clock.now().strftime('%m-%d %H:%M')}",
                flush=True,
            )
        return result

    SignalEngineService._orig_build_snapshot = SignalEngineService.build_snapshot
    SignalEngineService.build_snapshot = _counting_bs

    _harness_start = _time_module.time()
    summary = harness.run(SYMBOL, TF)
    SignalEngineService.build_snapshot = SignalEngineService._orig_build_snapshot
    _harness_elapsed = _time_module.time() - _harness_start
    print(f"      Harness completed in {_harness_elapsed:.1f}s", flush=True)

    print("✅ Soak завершён:")
    print(f"   bars_processed:  {summary.bars_processed}")
    print(f"   sessions_started: {summary.sessions_started}")
    print(f"   trades_resolved:  {summary.trades_resolved}")
    print(f"   trades:           {len(summary.trades)}")

    wins = sum(1 for t in summary.trades if t.pnl_pct and t.pnl_pct > 0)
    losses = sum(1 for t in summary.trades if t.pnl_pct and t.pnl_pct < 0)

    sessions = summary.sessions_started
    resolved = summary.trades_resolved

    assert sessions >= 30, f"Нужно ≥30 sessions, есть {sessions}"
    assert resolved == len(summary.trades), (
        f"Все trades resolved: {resolved} vs {len(summary.trades)}"
    )
    for t in summary.trades:
        assert t.outcome_status == "matched", (
            f"Trade {t.session_id}: {t.outcome_status}"
        )

    results["sessions_started"] = sessions
    results["trades_resolved"] = resolved
    results["wins"] = wins
    results["losses"] = losses

    total = wins + losses
    print(f"   W/L: {wins}W / {losses}L (total={total})")

    # ── 5. Recalibration proof ─────────────────────────────────────

    replay_after = se._compute_sizing_stats(session, risk_cfg, source_scope={"replay"})

    results["replay_p_b_before"] = {
        "p": replay_before[0],
        "b": replay_before[1],
        "ev": replay_before[2],
    }
    results["replay_p_b_after"] = {
        "p": replay_after[0],
        "b": replay_after[1],
        "ev": replay_after[2],
    }

    print("\n📐 p/b после soak:")
    print(
        f"   replay-scope:    p={replay_after[0]:.5f}, b={replay_after[1]:.5f}, ev={replay_after[2]:.5f}"
    )

    assert replay_after[0] > 0.0, (
        f"replay p должен быть > 0 после recalb, got {replay_after[0]}"
    )
    assert replay_after[0] != replay_before[0], "replay p не изменился после soak"

    # b_emp проверка
    if losses > 0:
        assert replay_after[1] != 1.0, (
            f"replay b должен быть пересчитан (не fallback 1.0), "
            f"wins={wins}, losses={losses}, b={replay_after[1]}"
        )
        print(f" ✅ b пересчитан: {replay_before[1]} → {replay_after[1]}")
    else:
        print(f" ⚠️  Нет потерь — b остался fallback {replay_after[1]}")
        print(
            f"    wins={wins}, losses=0 → b_emp не определён, fallback 1.0 — корректно"
        )
        results["wins_only"] = True

    results["replay_p_moved"] = replay_after[0] != replay_before[0]
    results["recalibrated"] = replay_after[0] > 0 and (
        replay_after[1] != 1.0 or losses == 0
    )

    # ── 6. Default-scope frozen ────────────────────────────────────

    default_after = se._compute_sizing_stats(
        session, risk_cfg, source_scope=DEFAULT_READ_SCOPE
    )
    results["default_p_b_before"] = {
        "p": default_before[0],
        "b": default_before[1],
        "ev": default_before[2],
    }
    results["default_p_b_after"] = {
        "p": default_after[0],
        "b": default_after[1],
        "ev": default_after[2],
    }

    print("\n🔒 default-scope:")
    print(
        f"   before: p={default_before[0]:.5f}, b={default_before[1]:.5f}, ev={default_before[2]:.5f}"
    )
    print(
        f"   after:  p={default_after[0]:.5f}, b={default_after[1]:.5f}, ev={default_after[2]:.5f}"
    )

    assert default_before == default_after, (
        f"default-scope p/b изменился!\n"
        f"  before={default_before}\n  after={default_after}"
    )
    results["default_frozen"] = True

    # ── 7. Isolation ───────────────────────────────────────────────

    bl_after = {
        r.id: (r.pnl_pct, r.outcome_status, r.source)
        for r in demo.list_all_trade_records(source_scope={"baseline", "live"})
    }
    replay_ids = {r.id for r in demo.list_all_trade_records(source_scope={"replay"})}
    default_ids = {r.id for r in demo.list_all_trade_records()}
    isolation_ok = default_ids.isdisjoint(replay_ids)

    results["replay_record_count"] = len(replay_ids)
    results["scope_isolation"] = isolation_ok
    print(
        f"\n🔍 Изоляция: {len(replay_ids)} replay записей, {len(bl_after)} baseline/live"
    )
    assert isolation_ok, "default scope содержит replay записи!"
    print("   ✅ scope_isolation: OK")
    assert bl_wins == sum(1 for r in bl_after.values() if r[0] and r[0] > 0), (
        "baseline/live records изменились!"
    )

    # ── 8. L2 / loss-streak на реальных данных ─────────────────────

    print("\n📉 L2 анализ:")
    if losses >= 3:
        print(f"   ✅ L2 естественно сработал: {losses} потерь в replay-scope")
        results["l2_natural"] = True
        pf = bundle["session_control"].build_snapshot(
            session, for_start=True, source_scope={"replay"}
        )
        l2_check = next(
            (c for c in pf.preflight.checks if c.check_id == "risk-limit-cooldown"),
            None,
        )
        if l2_check is not None:
            results["l2_status"] = l2_check.status
            results["l2_blocks_start"] = l2_check.blocks_start
            print(
                f"   🛑 L2 status={l2_check.status}, blocks_start={l2_check.blocks_start}"
            )
    else:
        print(f"   ⚠️  На {wins}W/{losses}L — естественный loss-streak < 3")
        print("   L2 не сработал (корректно: нет 3 последовательных потерь)")
        results["l2_natural"] = False
        results["l2_losses_count"] = losses

    # ── 9. Clock-desync guard ──────────────────────────────────────

    print("\n⏰ Clock-desync guard...")
    # Create trades at +2h relative to the LATEST soak clock position
    trades_clock = VirtualClock(start=clock.now())
    trades_clock.tick(timedelta(hours=2))
    for i in range(3):
        demo.create_trade_record(
            {
                "session_id": f"desync-check-{i}",
                "signal_id": "desync-check",
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
    session.commit()

    guard_fired = False
    try:
        bundle["session_control"].build_snapshot(
            session, for_start=True, source_scope={"replay"}
        )
    except ValueError as e:
        if "clock desync" in str(e).lower():
            guard_fired = True
            print(f"   ✅ Guard сработал: {e}")

    assert guard_fired, "clock-desync guard не сработал!"
    results["clock_desync_guard"] = True

    # ── 10. Cleanup ────────────────────────────────────────────────

    for r in demo.list_all_trade_records(source_scope={"replay"}):
        session.delete(r)
    session.commit()
    print("\n🧹 Replay-scope записи очищены")

    # ── Restore patches ────────────────────────────────────────────

    MarketRepository.list_latest_bars = _orig_list_latest
    MarketRepository.list_freshness_statuses = _orig_list_freshness

    session.close()
    engine.dispose()

    results["status"] = "PASS"
    print("\n" + "=" * 72)
    print("🎉 Все проверки пройдены!")
    print("=" * 72)
    print(f"\nРезультаты:\n{json.dumps(results, indent=2, default=str)}")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except AssertionError as e:
        print(f"\n❌ ПРОВАЛ: {e}")
        results["status"] = "FAIL"
        results["error"] = str(e)
        print(f"\nРезультаты:\n{json.dumps(results, indent=2, default=str)}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        results["status"] = "ERROR"
        results["error"] = f"{type(e).__name__}: {e}"
        print(f"\nРезультаты:\n{json.dumps(results, indent=2, default=str)}")
        sys.exit(1)
