"""Unit and integration tests for signal_engine/sizing.py and _apply_kelly_sizing."""

from __future__ import annotations

import math

from clay.runtime.states import RuntimeState
from clay.signal_engine.models import RiskTriggerSnapshot
from clay.signal_engine.service import SignalEngineService
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
        wins=13, losses=7, win_pnl_sum=7.1305, loss_pnl_sum=-2.1798,
        min_outcomes=5, lambda_=0.25, cap=0.02,
    )
    assert p > 0.0
    assert b > 1.0
    assert ev_val > 0.0
    assert f_star > 0.0
    assert 0 < f <= 0.02  # capped


def test_compute_sizing_stats_no_data() -> None:
    p, b, ev_val, f_star, f = compute_sizing_stats(
        wins=0, losses=0, win_pnl_sum=0.0, loss_pnl_sum=0.0,
    )
    assert p == 0.0
    assert b == 1.0  # fallback
    assert ev_val <= 0.0
    assert f_star == 0.0
    assert f == 0.0


# ── _apply_kelly_sizing ─────────────────────────────────────────────────────

def _make_trigger(trigger_id: str = "test", response_action: str = "warning_only") -> RiskTriggerSnapshot:
    return RiskTriggerSnapshot(
        trigger_id=trigger_id,
        severity="warning",
        title="Test",
        description="Test trigger.",
        response_action=response_action,
    )


class FakeKellyConfig:
    def __init__(self, min_ev: float = 0.15) -> None:
        self.min_ev = min_ev
        self.lambda_ = 0.25
        self.cap = 0.02


class FakeRiskConfig:
    def __init__(self) -> None:
        self.kelly = FakeKellyConfig()
        self.calibration = type("FakeCal", (), {"min_outcomes_for_recalibration": 30})()


def test_kelly_sizing_degraded_returns_none() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.DEGRADED,
        sizing_stats=(0.65, 1.5, 0.625, 0.2, 0.02),
        kelly_config=FakeKellyConfig(),
    )
    assert result.f is None
    assert result.ev_gate_triggered is False


def test_kelly_sizing_ev_below_zero_zeroes() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.BACKGROUND_MONITORING,
        sizing_stats=(0.3, 1.0, -0.4, 0.0, 0.0),
        kelly_config=FakeKellyConfig(min_ev=0.15),
    )
    assert result.f == 0.0
    assert result.ev_gate_triggered is True


def test_kelly_sizing_ev_below_min_zeroes() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.BACKGROUND_MONITORING,
        sizing_stats=(0.5, 1.05, 0.025, 0.0, 0.0),
        kelly_config=FakeKellyConfig(min_ev=0.15),
    )
    assert result.f == 0.0
    assert result.ev_gate_triggered is True


def test_kelly_sizing_ev_above_min_passes() -> None:
    engine = object.__new__(SignalEngineService)
    result = engine._apply_kelly_sizing(
        runtime_state=RuntimeState.BACKGROUND_MONITORING,
        sizing_stats=(0.65, 1.76, 0.79, 0.45, 0.02),
        kelly_config=FakeKellyConfig(min_ev=0.15),
    )
    assert result.f == 0.02
    assert result.ev_gate_triggered is False
