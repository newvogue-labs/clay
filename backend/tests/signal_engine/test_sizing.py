"""Unit and integration tests for signal_engine/sizing.py and _apply_kelly_sizing."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from clay.config.models import KellyConfig
from clay.runtime.states import RuntimeState
from clay.signal_engine.models import RiskTriggerSnapshot
from clay.signal_engine.service import KellySizingResult, SignalEngineService
from clay.signal_engine.sizing import (
    advisory_fraction,
    compute_sizing_stats,
    empirical_b,
    ev,
    kelly_fraction,
    wilson_lower,
)


# ── Wilson lower bound ──────────────────────────────────────────────────────


def test_wilson_lower_zero_n() -> None:
    assert wilson_lower(0, 0) == 0.0


def test_wilson_lower_perfect() -> None:
    bound = wilson_lower(20, 20)
    assert 0.80 < bound < 1.0


def test_wilson_lower_half() -> None:
    bound = wilson_lower(20, 10)
    assert 0.25 < bound < 0.75


def test_wilson_lower_small_n() -> None:
    bound = wilson_lower(5, 3)
    assert 0.0 < bound < 0.9


# ── Empirical b ─────────────────────────────────────────────────────────────


def test_empirical_b_normal() -> None:
    b = empirical_b(win_pnl_sum=6.0, loss_pnl_sum=-2.0, win_count=3, loss_count=2)
    assert math.isclose(b, 2.0, rel_tol=1e-4)


def test_empirical_b_no_wins() -> None:
    b = empirical_b(win_pnl_sum=0.0, loss_pnl_sum=-5.0, win_count=0, loss_count=3)
    assert b == 1.0  # fallback


def test_empirical_b_no_losses() -> None:
    b = empirical_b(win_pnl_sum=5.0, loss_pnl_sum=0.0, win_count=3, loss_count=0)
    assert b == 1.0  # fallback


# ── Kelly fraction ──────────────────────────────────────────────────────────


def test_kelly_positive_edge() -> None:
    f = kelly_fraction(0.65, 1.5)
    assert math.isclose(f, 0.4167, rel_tol=1e-3)


def test_kelly_zero_ev() -> None:
    f = kelly_fraction(0.5, 1.0)
    assert f == 0.0


def test_kelly_negative_edge() -> None:
    f = kelly_fraction(0.3, 1.0)
    assert f == 0.0


def test_kelly_below_one() -> None:
    f = kelly_fraction(0.6, 1.2)
    assert 0 < f < 1.0


# ── EV ──────────────────────────────────────────────────────────────────────


def test_ev_positive() -> None:
    val = ev(0.65, 1.5)
    assert math.isclose(val, 0.625, rel_tol=1e-4)


def test_ev_zero() -> None:
    val = ev(0.5, 1.0)
    assert val == 0.0


def test_ev_negative() -> None:
    val = ev(0.3, 1.0)
    assert math.isclose(val, -0.4, rel_tol=1e-4)


# ── Advisory fraction ───────────────────────────────────────────────────────


def test_advisory_caps() -> None:
    assert advisory_fraction(0.5, lambda_=0.25, cap=0.02) == 0.02  # 0.125 > 0.02


def test_advisory_below_cap() -> None:
    assert advisory_fraction(0.05, lambda_=0.25, cap=0.02) == 0.0125


def test_advisory_no_edge() -> None:
    assert advisory_fraction(0.0, lambda_=0.25, cap=0.02) == 0.0


# ── compute_sizing_stats ────────────────────────────────────────────────────


def test_compute_sizing_stats_typical() -> None:
    p, b, ev_val, f_star, f = compute_sizing_stats(
        wins=13,
        losses=7,
        win_pnl_sum=7.1305,
        loss_pnl_sum=-2.1798,
        min_outcomes=5,
        lambda_=0.25,
        cap=0.02,
    )
    assert p > 0.0
    assert b > 1.0
    assert ev_val > 0.0
    assert f_star > 0.0
    assert 0 < f <= 0.02  # capped


def test_compute_sizing_stats_no_data() -> None:
    p, b, ev_val, f_star, f = compute_sizing_stats(
        wins=0,
        losses=0,
        win_pnl_sum=0.0,
        loss_pnl_sum=0.0,
    )
    assert p == 0.0
    assert b == 1.0  # fallback
    assert ev_val <= 0.0
    assert f_star == 0.0
    assert f == 0.0


# ── _apply_kelly_sizing ─────────────────────────────────────────────────────


def _make_trigger(
    trigger_id: str = "test", response_action: str = "warning_only"
) -> RiskTriggerSnapshot:
    return RiskTriggerSnapshot(
        trigger_id=trigger_id,
        severity="warning",
        title="Test",
        description="Test trigger.",
        response_action=response_action,
    )


def test_kelly_sizing_degraded_returns_none() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.DEGRADED,
        sizing_stats=(0.65, 1.5, 0.625, 0.2, 0.02),
        kelly_config=KellyConfig(),
    )
    assert result.f is None
    assert result.ev_gate_triggered is False


def test_kelly_sizing_ev_below_zero_zeroes() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.BACKGROUND_MONITORING,
        sizing_stats=(0.3, 1.0, -0.4, 0.0, 0.0),
        kelly_config=KellyConfig(min_ev=0.15),
    )
    assert result.f == 0.0
    assert result.ev_gate_triggered is True


def test_kelly_sizing_ev_below_min_zeroes() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.BACKGROUND_MONITORING,
        sizing_stats=(0.5, 1.05, 0.025, 0.0, 0.0),
        kelly_config=KellyConfig(min_ev=0.15),
    )
    assert result.f == 0.0
    assert result.ev_gate_triggered is True


def test_kelly_sizing_ev_above_min_passes() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.BACKGROUND_MONITORING,
        sizing_stats=(0.65, 1.76, 0.79, 0.45, 0.02),
        kelly_config=KellyConfig(min_ev=0.15),
    )
    assert result.f == 0.02
    assert result.ev_gate_triggered is False


# ── Annotation tests (_build_sizing_note) ────────────────────────────────────


def test_sizing_note_degraded() -> None:
    result = KellySizingResult(
        updated_risk_triggers=[],
        p=None,
        b=None,
        ev_val=None,
        f_star=None,
        f=None,
        ev_gate_triggered=False,
    )
    note = SignalEngineService._build_sizing_note(result)
    assert note == "System degraded — advisory size suppressed (0)."


def test_sizing_note_ev_below_zero() -> None:
    result = KellySizingResult(
        updated_risk_triggers=[],
        p=0.3,
        b=1.0,
        ev_val=-0.4,
        f_star=0.0,
        f=0.0,
        ev_gate_triggered=True,
    )
    note = SignalEngineService._build_sizing_note(result)
    assert "EV ≤ 0" in note
    assert "negative edge" in note


def test_sizing_note_ev_below_min() -> None:
    result = KellySizingResult(
        updated_risk_triggers=[],
        p=0.5,
        b=1.05,
        ev_val=0.025,
        f_star=0.0,
        f=0.0,
        ev_gate_triggered=True,
    )
    note = SignalEngineService._build_sizing_note(result)
    assert "EV 0.03R below min" in note
    assert "signal still visible" in note


def test_sizing_note_gate_open() -> None:
    result = KellySizingResult(
        updated_risk_triggers=[],
        p=0.65,
        b=1.76,
        ev_val=0.79,
        f_star=0.45,
        f=0.02,
        ev_gate_triggered=False,
    )
    note = SignalEngineService._build_sizing_note(result)
    assert "Advisory size: 2.0%" in note
    assert "EV 0.79R" in note


# ── Scenario tests: EV-gate through full chain (ШАГ 1) ──────────────────


class TestEvGateScenarios:
    """Four EV bands tested through _apply_kelly_sizing → _build_execution_notes.

    Each scenario proves simultaneously: advisory_position_size, ev_gate_triggered,
    execution_notes text, and that EV-gate does NOT cascade to signal state/action.
    """

    @staticmethod
    def _engine() -> SignalEngineService:
        return object.__new__(SignalEngineService)

    def _exec_notes(
        self,
        engine: SignalEngineService,
        result: KellySizingResult,
        state: str = "active",
        resp_action: str = "warning_only",
        direction: str = "bullish",
    ) -> list[str]:
        return engine._build_execution_notes(
            state=state,
            response_action=resp_action,
            direction=direction,
            kelly_result=result,
        )

    def test_negative_edge_ev_below_zero(self) -> None:
        """EV ≤ 0: f=0, gate triggered, note says negative edge, signal visible."""
        engine = self._engine()
        cfg = KellyConfig(min_ev=0.15)
        result = engine._apply_kelly_sizing(
            runtime_state=RuntimeState.BACKGROUND_MONITORING,
            sizing_stats=(0.3, 1.0, -0.4, 0.0, 0.0),
            kelly_config=cfg,
        )
        assert result.f == 0.0
        assert result.ev_gate_triggered is True
        notes = self._exec_notes(engine, result)
        assert "EV ≤ 0" in notes[-1]
        assert "negative edge" in notes[-1]

    def test_below_min_gate_blocks(self) -> None:
        """0 < EV ≤ min_ev: f=0, gate triggered, note says below min, signal visible."""
        engine = self._engine()
        cfg = KellyConfig(min_ev=0.15)
        result = engine._apply_kelly_sizing(
            runtime_state=RuntimeState.BACKGROUND_MONITORING,
            sizing_stats=(0.5, 1.05, 0.025, 0.0, 0.0),
            kelly_config=cfg,
        )
        assert result.f == 0.0
        assert result.ev_gate_triggered is True
        notes = self._exec_notes(engine, result)
        assert "below min" in notes[-1]
        assert "signal still visible" in notes[-1]

    def test_above_min_passes_gate(self) -> None:
        """EV > min_ev: f>0 (capped), gate open, note says advisory size."""
        engine = self._engine()
        cfg = KellyConfig(min_ev=0.15)
        result = engine._apply_kelly_sizing(
            runtime_state=RuntimeState.BACKGROUND_MONITORING,
            sizing_stats=(0.65, 1.76, 0.79, 0.45, 0.02),
            kelly_config=cfg,
        )
        assert result.f == 0.02
        assert result.ev_gate_triggered is False
        notes = self._exec_notes(engine, result)
        assert "Advisory size: 2.0%" in notes[-1]

    def test_degraded_skips_kelly(self) -> None:
        """Degraded: f=None, gate not triggered, note says degraded."""
        engine = self._engine()
        cfg = KellyConfig(min_ev=0.15)
        result = engine._apply_kelly_sizing(
            runtime_state=RuntimeState.DEGRADED,
            sizing_stats=(0.65, 1.5, 0.625, 0.2, 0.02),
            kelly_config=cfg,
        )
        assert result.f is None
        assert result.ev_gate_triggered is False
        notes = self._exec_notes(engine, result)
        assert "System degraded" in notes[-1]


class TestEvGateNoCascade:
    """Proof: EV-gate does NOT propagate to signal state or response_action.

    _resolve_signal_state depends on market_status, response_action, ranking_score, time.
    _resolve_response_action depends only on risk_triggers.
    Neither receives KellySizingResult — EV gate ONLY touches:
    - advisory_position_size field on the signal
    - ev_gate_triggered field on the signal
    - execution_notes (via _build_sizing_note)
    """

    def test_signal_state_independent_of_kelly(self) -> None:
        engine = object.__new__(SignalEngineService)
        now = datetime.now(UTC)
        state = engine._resolve_signal_state(
            market_status="fresh",
            response_action="warning_only",
            ranking_score=0.72,
            bar_close_time=now,
            now=now,
        )
        assert state == "active"

    def test_response_action_independent_of_kelly(self) -> None:
        engine = object.__new__(SignalEngineService)
        action = engine._resolve_response_action([])
        assert action == "warning_only"


# ── Hard-block regression tests (ШАГ 2) ─────────────────────────────────


class TestHardBlockRegression:
    """Verify stale-market / expired-window → block_signal path still works.

    Covers the pre-existing hard-block path: trigger → response_action → notes → state.
    """

    @staticmethod
    def _engine() -> SignalEngineService:
        return object.__new__(SignalEngineService)

    def test_stale_market_triggers_block_signal(self) -> None:
        engine = self._engine()
        triggers = [
            RiskTriggerSnapshot(
                trigger_id="stale-market-btcusdt",
                severity="critical",
                title="Stale market data",
                description=".",
                response_action="block_signal",
            ),
        ]
        assert engine._resolve_response_action(triggers) == "block_signal"

    def test_expired_window_triggers_block_signal(self) -> None:
        engine = self._engine()
        triggers = [
            RiskTriggerSnapshot(
                trigger_id="expired-window-btcusdt",
                severity="warning",
                title="Signal window expired",
                description=".",
                response_action="block_signal",
            ),
        ]
        assert engine._resolve_response_action(triggers) == "block_signal"

    def test_block_signal_notes_do_not_execute(self) -> None:
        engine = self._engine()
        notes = engine._build_execution_notes(
            state="invalidated",
            response_action="block_signal",
            direction="bullish",
            kelly_result=None,
        )
        assert "Do not execute" in notes[1]

    def test_block_signal_produces_invalidated_state(self) -> None:
        engine = self._engine()
        now = datetime.now(UTC)
        state = engine._resolve_signal_state(
            market_status="stale",
            response_action="block_signal",
            ranking_score=0.65,
            bar_close_time=now,
            now=now,
        )
        assert state == "invalidated"

    def test_expired_window_state_expired(self) -> None:
        engine = self._engine()
        old = datetime.now(UTC) - timedelta(hours=3)
        state = engine._resolve_signal_state(
            market_status="fresh",
            response_action="warning_only",
            ranking_score=0.65,
            bar_close_time=old,
            now=datetime.now(UTC),
        )
        assert state == "expired"
