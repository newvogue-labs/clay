from __future__ import annotations

import math

DEFAULT_Z = 1.96


def wilson_lower(n: int, k: int, z: float = DEFAULT_Z) -> float:
    """Wilson lower bound for a proportion (95% CI by default).

    Returns the lower bound of the confidence interval. For small n
    or extreme k this can be 0 or negative — caller should take max(0, ...).
    """
    if n == 0:
        return 0.0
    p_hat = k / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (p_hat + z2 / (2 * n)) / denominator
    margin = z * math.sqrt((p_hat * (1 - p_hat) / n + z2 / (4 * n * n))) / denominator
    return max(0.0, centre - margin)


def empirical_b(
    *,
    win_pnl_sum: float,
    loss_pnl_sum: float,
    win_count: int,
    loss_count: int,
    fallback: float = 1.0,
) -> float:
    """Empirical payoff b from realised demo outcomes.

    Returns avg_win / avg_loss. If there are no wins or no losses
    returns *fallback* (default 1.0) — no edge assumption.
    """
    if win_count == 0 or loss_count == 0:
        return fallback
    avg_win = win_pnl_sum / win_count
    avg_loss = abs(loss_pnl_sum) / loss_count  # loss_pnl_sum is negative
    if avg_loss == 0:
        return fallback
    return round(avg_win / avg_loss, 4)


def kelly_fraction(p: float, b: float) -> float:
    """Full Kelly fraction: f* = (p*b - (1-p)) / b.

    Returns 0 if EV ≤ 0 (no positive edge)."""
    if b <= 0:
        return 0.0
    raw = (p * b - (1 - p)) / b
    return max(0.0, raw)


def ev(p: float, b: float) -> float:
    """Expected value in R-units: EV = p*b - (1-p)."""
    return p * b - (1 - p)


def advisory_fraction(f_star: float, lambda_: float, cap: float) -> float:
    """Clamp fractional Kelly to [0, cap]."""
    if f_star <= 0:
        return 0.0
    return min(lambda_ * f_star, cap)


SizingStats = tuple[
    float,   # p (Wilson lower bound)
    float,   # b (empirical payoff)
    float,   # EV
    float,   # f* (full Kelly)
    float,   # f (advisory fraction)
]


def compute_sizing_stats(
    *,
    wins: int,
    losses: int,
    win_pnl_sum: float,
    loss_pnl_sum: float,
    min_outcomes: int = 30,
    lambda_: float = 0.25,
    cap: float = 0.02,
) -> SizingStats:
    """Compute all sizing stats from demo outcome aggregates.

    If total < *min_outcomes* the Wilson lower bound will be
    conservative (and f likely 0 or capped at minimum). This is
    expected — edge is not statistically proven with thin data.
    """
    total = wins + losses
    p = wilson_lower(total, wins) if total > 0 else 0.0
    b = empirical_b(
        win_pnl_sum=win_pnl_sum,
        loss_pnl_sum=loss_pnl_sum,
        win_count=wins,
        loss_count=losses,
    )
    ev_val = ev(p, b)
    f_star = kelly_fraction(p, b)
    f = advisory_fraction(f_star, lambda_, cap)
    return p, b, ev_val, f_star, f
