"""Session risk assessment — SSOT for drawdown / cooldown evaluation.

Extracted from ``SessionControlService._build_preflight`` (ADR-021) to
provide a single source of truth for both preflight checks and the
per-order gate probe (``session_risk_probe``).

Probe is **off-by-default** — requires ``proof_enforce_session_risk=True``
in ``ExecutionConfig`` and late-bind via ``bootstrap.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, sessionmaker

from clay.db.repositories_demo import DEFAULT_READ_SCOPE, DemoRepository

if TYPE_CHECKING:
    from clay.config.loader import ConfigLoader
    from clay.config.models import SessionLimitsConfig


@dataclass(frozen=True)
class SessionRiskAssessment:
    """Результат оценки session-level risk limits (drawdown + cooldown)."""

    drawdown_tripped: bool
    cooldown_tripped: bool
    cum_pnl: float
    loss_pct: float
    streak: int
    cooldown_remaining_minutes: int | None = None


def evaluate_session_risk(
    session: Session,
    *,
    limits_cfg: SessionLimitsConfig,
    now: datetime,
    scope: Collection[str] = DEFAULT_READ_SCOPE,
) -> SessionRiskAssessment:
    """Оценка drawdown + cooldown по данным DemoRepository.

    Чистая функция: зависит только от session/limits/now/scope.
    Пустые данные → not tripped (ADR-021: empty result = pass).
    Исключения пропускаются наверх (не глушатся).
    """
    demo_repo = DemoRepository(session)

    # --- Drawdown ---
    window_records = demo_repo.list_resolved_window(
        hours=limits_cfg.drawdown_window_hours, source_scope=scope
    )
    cum_pnl = round(sum(r.pnl_pct or 0.0 for r in window_records), 2)
    loss_pct = abs(cum_pnl) if cum_pnl < 0 else 0.0
    drawdown_tripped = loss_pct >= limits_cfg.max_drawdown_pct

    # --- Cooldown ---
    ordered = demo_repo.list_ordered_recent(limit=50, source_scope=scope)
    streak = 0
    streak_ts: datetime | None = None
    for r in ordered:
        if (r.pnl_pct or 0.0) < 0 and r.outcome_status in {
            "matched",
            "missed",
            "late_matched",
            "mismatched",
        }:
            streak += 1
            if streak_ts is None:
                streak_ts = r.recorded_at
        else:
            break

    cooldown_tripped = False
    cooldown_remaining_minutes: int | None = None

    if streak >= limits_cfg.max_consecutive_losses and streak_ts is not None:
        if streak_ts.tzinfo is None:
            streak_ts = streak_ts.replace(tzinfo=UTC)
        ahead = (streak_ts - now).total_seconds()
        if ahead > 60:
            raise ValueError(
                f"clock desync: trade recorded_at={streak_ts.isoformat()} "
                f"ahead of clock now={now.isoformat()} by {ahead:.0f}s"
            )
        elapsed_min = (now - streak_ts).total_seconds() / 60
        if elapsed_min < limits_cfg.cooldown_minutes:
            cooldown_tripped = True
            cooldown_remaining_minutes = int(limits_cfg.cooldown_minutes - elapsed_min)

    return SessionRiskAssessment(
        drawdown_tripped=drawdown_tripped,
        cooldown_tripped=cooldown_tripped,
        cum_pnl=cum_pnl,
        loss_pct=loss_pct,
        streak=streak,
        cooldown_remaining_minutes=cooldown_remaining_minutes,
    )


def build_session_risk_probe(
    session_factory: sessionmaker,
    config_loader: ConfigLoader,
    *,
    scope: Collection[str] = DEFAULT_READ_SCOPE,
    now_fn: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> Callable[[], tuple[bool, bool]]:
    """Фабрика probe: zero-arg callable для ``ExecutionProofGate``.

    На каждый вызов: свежий config, своя session, ``evaluate_session_risk``.
    Исключения НЕ глушатся — gate сам fail-closed → ``(True, True)``.
    """

    def _probe() -> tuple[bool, bool]:
        from clay.config.models import SessionLimitsConfig

        risk_cfg = config_loader.load_scope("risk")
        limits_cfg: SessionLimitsConfig = getattr(
            risk_cfg, "session_limits", SessionLimitsConfig()
        )
        with session_factory() as db_session:
            assessment = evaluate_session_risk(
                db_session,
                limits_cfg=limits_cfg,
                now=now_fn(),
                scope=scope,
            )
            return (assessment.drawdown_tripped, assessment.cooldown_tripped)

    return _probe
