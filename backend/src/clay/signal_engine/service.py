from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from clay.ai_control.service import AIControlService
from clay.ai_control.models import AssignmentSnapshot
from clay.core.clock import Clock, SystemClock
from clay.config.loader import ConfigLoader
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.settings.ingestion import IngestionSettings
from clay.shortlist.read_models import build_shortlist_metrics
from clay.signal_engine.models import (
    AppliedPenalty,
    EvaluatedSignalSnapshot,
    RiskTriggerSnapshot,
    SignalEngineSnapshot,
)
from clay.signal_engine.sizing import SizingStats, compute_sizing_stats


logger = logging.getLogger(__name__)


TIMEFRAME_PRIORITY = {
    "15m": 0,
    "5m": 1,
    "1h": 2,
}


@dataclass(slots=True)
class KellySizingResult:
    updated_risk_triggers: list[RiskTriggerSnapshot]
    p: float | None
    b: float | None
    ev_val: float | None
    f_star: float | None
    f: float | None
    ev_gate_triggered: bool


@dataclass(slots=True)
class SignalCandidate:
    signal: EvaluatedSignalSnapshot
    market_status: str
    context_status: str


class SignalEngineService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        preflight_service: PreflightService,
        config_loader: ConfigLoader,
        ai_control_service: AIControlService,
        ingestion_settings: IngestionSettings | None = None,
        clock: Clock = SystemClock(),
    ) -> None:
        self.runtime_manager = runtime_manager
        self.preflight_service = preflight_service
        self.config_loader = config_loader
        self.ai_control_service = ai_control_service
        self.ingestion_settings = ingestion_settings or IngestionSettings()  # type: ignore[reportCallIssue]  # FOOTGUN A: reads from CLAY_DATABASE_URL env
        self._clock = clock

    def build_snapshot(
        self, session: Session, source_scope: Collection[str] | None = None
    ) -> SignalEngineSnapshot:
        runtime_snapshot = self.runtime_manager.snapshot()
        candidates = self._evaluate_candidates(session, source_scope=source_scope)
        signals = sorted(
            [candidate.signal for candidate in candidates],
            key=lambda item: item.ranking_score,
            reverse=True,
        )

        market_status = "unknown"
        context_status = "unknown"
        if candidates:
            market_status = self._collapse_status(
                [candidate.market_status for candidate in candidates]
            )
            context_status = self._collapse_status(
                [candidate.context_status for candidate in candidates]
            )

        workspace_posture = self._resolve_workspace_posture(
            runtime_state=runtime_snapshot.state,
            market_status=market_status,
            signals=signals,
        )
        return SignalEngineSnapshot(
            runtime_state=runtime_snapshot.state.value,
            workspace_posture=workspace_posture,
            market_status=market_status,
            context_status=context_status,
            strategy_mode_proposal=self._propose_strategy_mode(
                signals, runtime_snapshot.state
            ),
            signals=signals,
        )

    def _evaluate_candidates(
        self, session: Session, source_scope: Collection[str] | None = None
    ) -> list[SignalCandidate]:
        market_repo = MarketRepository(session)
        context_repo = ContextRepository(session)
        ops_repo = OpsRepository(session)
        ai_snapshot = self.ai_control_service.build_snapshot()
        risk_config = self.config_loader.load_scope("risk")
        sizing_stats = self._compute_sizing_stats(
            session, risk_config, source_scope=source_scope
        )
        now = self._clock.now()

        bars = market_repo.list_latest_bars(limit=50)
        freshness_rows = market_repo.list_freshness_statuses()
        preferred_bars = self._pick_preferred_bars(bars)
        shortlist_rows = build_shortlist_metrics(
            preferred_bars,
            freshness_rows,
            low_quote_volume_threshold=self.ingestion_settings.low_quote_volume_threshold,
            now=now,
        )
        news_rows = context_repo.latest_news(limit=20)
        sentiment_rows = context_repo.latest_sentiment(limit=20)
        connector_rows = ops_repo.latest_connector_statuses()

        news_symbols = {row.symbol for row in news_rows if row.symbol is not None}
        sentiment_map: dict[str, list[float]] = {}
        for row in sentiment_rows:
            sentiment_map.setdefault(row.symbol, []).append(row.sentiment_score)

        degraded_ai = {
            row.role_id
            for row in ai_snapshot.assignments
            if row.assignment_health in {"review_required", "degraded"}
        }
        ai_penalty = max(
            (row.confidence_penalty for row in ai_snapshot.assignments), default=0.0
        )
        preflight = self.preflight_service.run()
        runtime_state = self.runtime_manager.snapshot().state

        candidates: list[SignalCandidate] = []
        for row in shortlist_rows:
            bar = next(
                (
                    candidate
                    for candidate in preferred_bars
                    if candidate.symbol == row.symbol
                ),
                None,
            )
            if bar is None:
                continue

            sentiment_scores = sentiment_map.get(row.symbol, [])
            sentiment_score = sentiment_scores[0] if sentiment_scores else None
            direction = self._resolve_direction(bar.open, bar.close, sentiment_score)
            base_ranking = round(
                (row.rolling_volume_score * 0.55)
                + (row.rolling_volatility_score * 0.45),
                4,
            )
            market_status = row.availability_status
            context_status = (
                "fresh"
                if row.symbol in news_symbols
                and sentiment_scores
                and not any(
                    connector.status in {"degraded", "error"}
                    for connector in connector_rows
                )
                else "degraded"
            )
            risk_triggers = self._build_risk_triggers(
                symbol=row.symbol,
                market_status=market_status,
                context_status=context_status,
                runtime_state=runtime_state,
                preflight_status=preflight.status,
                degraded_ai=degraded_ai,
                bar_close_time=bar.bar_close_time,
                now=now,
            )
            kelly_result = self._apply_kelly_sizing(
                runtime_state=runtime_state,
                sizing_stats=sizing_stats,
                kelly_config=risk_config.kelly,
            )
            response_action = self._resolve_response_action(risk_triggers)
            confidence_penalty = self._resolve_confidence_penalty(
                risk_triggers=risk_triggers,
                degraded_penalty=risk_config.degraded_confidence_penalty,
                ai_penalty=ai_penalty,
            )
            ranking_score, applied_penalties = self._apply_ranking_penalty(
                base_ranking=base_ranking,
                risk_triggers=risk_triggers,
                ai_assignments=ai_snapshot.assignments,
            )
            confidence = self._resolve_confidence(
                ranking_score=ranking_score,
                sentiment_score=sentiment_score,
                confidence_penalty=confidence_penalty,
            )
            state = self._resolve_signal_state(
                market_status=market_status,
                response_action=response_action,
                ranking_score=ranking_score,
                bar_close_time=bar.bar_close_time,
                now=now,
            )

            signal = EvaluatedSignalSnapshot(
                signal_id=f"sig-{row.symbol.lower()}",
                symbol=row.symbol,
                display_name=self._display_name(row.symbol),
                direction=direction,
                state=state,
                confidence=confidence,
                ranking_score=ranking_score,
                confidence_penalty=confidence_penalty,
                strategy_mode=self._resolve_strategy_mode(ranking_score, risk_triggers),
                response_action=response_action,
                setup_summary=self._build_setup_summary(
                    symbol=row.symbol,
                    direction=direction,
                    state=state,
                    liquidity=row.liquidity_summary,
                    response_action=response_action,
                ),
                technical_context=[
                    f"Liquidity {row.liquidity_summary}",
                    f"Volatility score {row.rolling_volatility_score:.2f}",
                    f"Availability {market_status}",
                ],
                execution_notes=self._build_execution_notes(
                    state=state,
                    response_action=response_action,
                    direction=direction,
                    kelly_result=kelly_result,
                ),
                risk_triggers=risk_triggers,
                risk_posture=self._build_risk_posture(response_action),
                risk_reward_hint=self._build_risk_reward_hint(
                    direction=direction, ranking_score=ranking_score
                ),
                action_guidance=self._build_action_guidance(response_action),
                directional_bias=direction,
                entry_hint=self._price_hint(bar.close, direction, mode="entry"),
                target_hint=self._price_hint(bar.close, direction, mode="target"),
                invalidation_hint=self._price_hint(
                    bar.close, direction, mode="invalidation"
                ),
                analyst_note=self._build_analyst_note(
                    symbol=row.symbol,
                    state=state,
                    response_action=response_action,
                    ranking_score=ranking_score,
                ),
                last_updated_at=bar.bar_close_time.isoformat(),
                applied_penalties=applied_penalties,
                stale_timeframes=row.stale_timeframes,
                leader_quote_volume=row.leader_quote_volume,
                low_quote_volume=row.low_quote_volume,
                probability_estimate=kelly_result.p,
                payoff_estimate=kelly_result.b,
                kelly_fraction=kelly_result.f_star,
                advisory_position_size=kelly_result.f,
                ev_value=kelly_result.ev_val,
                ev_gate_triggered=kelly_result.ev_gate_triggered,
            )
            if applied_penalties:
                logger.info(
                    "signal.ranking_capped symbol=%s base=%.2f capped=%.2f penalties=%s",
                    row.symbol,
                    base_ranking,
                    ranking_score,
                    "; ".join(
                        f"{p.trigger}:{p.delta:+.2f}({p.note})"
                        for p in applied_penalties
                    ),
                )
            if row.stale_timeframes:
                logger.info(
                    "signal.stale_timeframes_detected symbol=%s stale_tfs=%s",
                    row.symbol,
                    ",".join(row.stale_timeframes),
                )
            if row.low_quote_volume:
                logger.info(
                    "signal.low_quote_volume_detected symbol=%s leader_quote_volume=%.2f threshold=%.2f",
                    row.symbol,
                    row.leader_quote_volume,
                    self.ingestion_settings.low_quote_volume_threshold,
                )
            candidates.append(
                SignalCandidate(
                    signal=signal,
                    market_status=market_status,
                    context_status=context_status,
                )
            )
        return candidates

    def _pick_preferred_bars(self, bars: list[object]) -> list[object]:
        by_symbol: dict[str, object] = {}
        for bar in bars:
            current = by_symbol.get(bar.symbol)
            if current is None:
                by_symbol[bar.symbol] = bar
                continue
            current_priority = TIMEFRAME_PRIORITY.get(current.timeframe, 99)
            next_priority = TIMEFRAME_PRIORITY.get(bar.timeframe, 99)
            if next_priority < current_priority:
                by_symbol[bar.symbol] = bar
        return list(by_symbol.values())

    def _resolve_direction(
        self, bar_open: float, bar_close: float, sentiment_score: float | None
    ) -> str:
        if sentiment_score is not None:
            if sentiment_score >= 0.6:
                return "bullish"
            if sentiment_score <= 0.4:
                return "bearish"
        return "bullish" if bar_close >= bar_open else "bearish"

    def _build_risk_triggers(
        self,
        *,
        symbol: str,
        market_status: str,
        context_status: str,
        runtime_state: RuntimeState,
        preflight_status: str,
        degraded_ai: set[str],
        bar_close_time: datetime,
        now: datetime,
    ) -> list[RiskTriggerSnapshot]:
        bar_close_time = self._normalize_timestamp(bar_close_time)
        triggers: list[RiskTriggerSnapshot] = []
        if market_status != "fresh":
            triggers.append(
                RiskTriggerSnapshot(
                    trigger_id=f"stale-market-{symbol.lower()}",
                    severity="critical",
                    title="Stale market data",
                    description="Market freshness for this pair is not fresh, so signal trust is blocked.",
                    response_action="block_signal",
                )
            )
        if context_status != "fresh":
            triggers.append(
                RiskTriggerSnapshot(
                    trigger_id=f"thin-context-{symbol.lower()}",
                    severity="warning",
                    title="Low context quality",
                    description="News or sentiment coverage is thin, so confidence should be reduced.",
                    response_action="lower_confidence",
                )
            )
        if degraded_ai:
            triggers.append(
                RiskTriggerSnapshot(
                    trigger_id="ai-conflict",
                    severity="warning",
                    title="AI orchestration conflict",
                    description="At least one AI role is degraded or review-required, so synthesis confidence must drop.",
                    response_action="lower_confidence",
                )
            )
        if runtime_state == RuntimeState.DEGRADED or preflight_status == "hard_fail":
            triggers.append(
                RiskTriggerSnapshot(
                    trigger_id="runtime-degraded",
                    severity="critical",
                    title="Runtime degraded",
                    description="Runtime/preflight is degraded; active signal execution should switch to defensive behavior.",
                    response_action="switch_to_defensive",
                )
            )
        if now - bar_close_time >= timedelta(hours=2):
            triggers.append(
                RiskTriggerSnapshot(
                    trigger_id=f"expired-window-{symbol.lower()}",
                    severity="warning",
                    title="Signal window expired",
                    description="Bar context is too old for an intraday actionable signal.",
                    response_action="block_signal",
                )
            )
        return triggers

    def _resolve_response_action(self, risk_triggers: list[RiskTriggerSnapshot]) -> str:
        if any(
            trigger.response_action == "switch_to_defensive"
            for trigger in risk_triggers
        ):
            return "switch_to_defensive"
        if any(trigger.response_action == "block_signal" for trigger in risk_triggers):
            return "block_signal"
        if any(
            trigger.response_action == "lower_confidence" for trigger in risk_triggers
        ):
            return "lower_confidence"
        return "warning_only"

    def _resolve_confidence_penalty(
        self,
        *,
        risk_triggers: list[RiskTriggerSnapshot],
        degraded_penalty: float,
        ai_penalty: float,
    ) -> float:
        penalty = 0.0
        if any(
            trigger.trigger_id.startswith("stale-market") for trigger in risk_triggers
        ):
            penalty += degraded_penalty
        if any(trigger.trigger_id == "ai-conflict" for trigger in risk_triggers):
            penalty += max(ai_penalty, round(degraded_penalty / 2, 2))
        if any(
            trigger.trigger_id.startswith("thin-context") for trigger in risk_triggers
        ):
            penalty += 0.08
        if any(trigger.trigger_id == "runtime-degraded" for trigger in risk_triggers):
            penalty += degraded_penalty
        return round(min(0.8, penalty), 2)

    def _apply_ranking_penalty(
        self,
        *,
        base_ranking: float,
        risk_triggers: list[RiskTriggerSnapshot],
        ai_assignments: list[AssignmentSnapshot],
    ) -> tuple[float, list[AppliedPenalty]]:
        ranking = base_ranking
        applied: list[AppliedPenalty] = []
        chief_provider = next(
            (row.provider for row in ai_assignments if row.role_id == "chief-agent"),
            "unknown",
        )
        for trigger in risk_triggers:
            if trigger.response_action == "lower_confidence":
                ranking -= 0.08
                if trigger.trigger_id == "ai-conflict":
                    conflicts = [
                        f"{row.role_id}={row.provider}"
                        for row in ai_assignments
                        if row.review_required
                    ]
                    note = f"provider-mix: chief={chief_provider} vs " + ", ".join(
                        conflicts
                    )
                else:
                    note = f"trigger={trigger.trigger_id} severity={trigger.severity}"
                applied.append(
                    AppliedPenalty(trigger=trigger.trigger_id, delta=-0.08, note=note),
                )
            elif trigger.response_action == "block_signal":
                ranking -= 0.2
                applied.append(
                    AppliedPenalty(
                        trigger=trigger.trigger_id,
                        delta=-0.2,
                        note=f"trigger={trigger.trigger_id} severity={trigger.severity}",
                    ),
                )
            elif trigger.response_action == "switch_to_defensive":
                ranking -= 0.15
                applied.append(
                    AppliedPenalty(
                        trigger=trigger.trigger_id,
                        delta=-0.15,
                        note=f"trigger={trigger.trigger_id} severity={trigger.severity}",
                    ),
                )
        return round(max(0.0, min(1.0, ranking)), 2), applied

    def _compute_sizing_stats(
        self,
        session: Session,
        risk_config: object,
        source_scope: Collection[str] | None = None,
    ) -> SizingStats:
        from clay.db.repositories_demo import DEFAULT_READ_SCOPE, DemoRepository

        scope = source_scope if source_scope is not None else DEFAULT_READ_SCOPE
        repo = DemoRepository(session)
        records = repo.list_all_trade_records(source_scope=scope)
        wins = 0
        losses = 0
        win_pnl_sum = 0.0
        loss_pnl_sum = 0.0
        for r in records:
            if r.pnl_pct is None:
                continue
            if r.pnl_pct > 0:
                wins += 1
                win_pnl_sum += r.pnl_pct
            elif r.pnl_pct < 0:
                losses += 1
                loss_pnl_sum += r.pnl_pct
        kelly_cfg = getattr(risk_config, "kelly", None)
        cal_cfg = getattr(risk_config, "calibration", None)
        min_outcomes = (
            cal_cfg.min_outcomes_for_recalibration if cal_cfg is not None else 30
        )
        lam = kelly_cfg.lambda_ if kelly_cfg is not None else 0.25
        cap = kelly_cfg.cap if kelly_cfg is not None else 0.02

        return compute_sizing_stats(
            wins=wins,
            losses=losses,
            win_pnl_sum=win_pnl_sum,
            loss_pnl_sum=loss_pnl_sum,
            min_outcomes=min_outcomes,
            lambda_=lam,
            cap=cap,
        )

    def _apply_kelly_sizing(
        self,
        *,
        runtime_state: RuntimeState,
        sizing_stats: SizingStats,
        kelly_config: object,
    ) -> KellySizingResult:
        degraded = runtime_state in (RuntimeState.DEGRADED,)
        if degraded:
            return KellySizingResult(
                updated_risk_triggers=[],
                p=None,
                b=None,
                ev_val=None,
                f_star=None,
                f=None,
                ev_gate_triggered=False,
            )

        p, b, ev_val, f_star, f = sizing_stats
        min_ev = getattr(kelly_config, "min_ev", 0.15)

        if ev_val <= 0:
            return KellySizingResult(
                updated_risk_triggers=[],
                p=p,
                b=b,
                ev_val=ev_val,
                f_star=0.0,
                f=0.0,
                ev_gate_triggered=True,
            )

        if ev_val <= min_ev:
            return KellySizingResult(
                updated_risk_triggers=[],
                p=p,
                b=b,
                ev_val=ev_val,
                f_star=0.0,
                f=0.0,
                ev_gate_triggered=True,
            )

        return KellySizingResult(
            updated_risk_triggers=[],
            p=p,
            b=b,
            ev_val=ev_val,
            f_star=f_star,
            f=f,
            ev_gate_triggered=False,
        )

    def _resolve_confidence(
        self,
        *,
        ranking_score: float,
        sentiment_score: float | None,
        confidence_penalty: float,
    ) -> float:
        confidence = ranking_score
        if sentiment_score is not None:
            confidence = min(1.0, confidence + 0.08)
        confidence = max(0.05, confidence - confidence_penalty)
        return round(confidence, 2)

    def _resolve_signal_state(
        self,
        *,
        market_status: str,
        response_action: str,
        ranking_score: float,
        bar_close_time: datetime,
        now: datetime,
    ) -> str:
        bar_close_time = self._normalize_timestamp(bar_close_time)
        if now - bar_close_time >= timedelta(hours=2):
            return "expired"
        if market_status != "fresh" or response_action == "block_signal":
            return "invalidated"
        if response_action == "switch_to_defensive":
            return "weakening"
        if ranking_score >= 0.72:
            return "active"
        if ranking_score >= 0.45:
            return "weakening"
        return "absent"

    def _resolve_strategy_mode(
        self, ranking_score: float, risk_triggers: list[RiskTriggerSnapshot]
    ) -> str:
        if any(
            trigger.response_action in {"block_signal", "switch_to_defensive"}
            for trigger in risk_triggers
        ):
            return "defensive"
        if ranking_score >= 0.78:
            return "momentum"
        return "trend_following"

    def _resolve_workspace_posture(
        self,
        *,
        runtime_state: RuntimeState,
        market_status: str,
        signals: list[EvaluatedSignalSnapshot],
    ) -> str:
        if runtime_state == RuntimeState.DEGRADED:
            return "restricted_by_degraded"
        if market_status != "fresh":
            return "defensive"
        if not any(signal.state == "active" for signal in signals):
            return "monitoring_only"
        return "normal"

    def _propose_strategy_mode(
        self, signals: list[EvaluatedSignalSnapshot], runtime_state: RuntimeState
    ) -> str:
        if runtime_state == RuntimeState.DEGRADED:
            return "defensive"
        best_signal = next(iter(signals), None)
        if best_signal is None:
            return "defensive"
        return best_signal.strategy_mode

    def _collapse_status(self, statuses: list[str]) -> str:
        if not statuses:
            return "unknown"
        if any(
            status in {"stale", "error", "degraded", "unknown"} for status in statuses
        ):
            return "degraded"
        return "fresh"

    def _build_setup_summary(
        self,
        *,
        symbol: str,
        direction: str,
        state: str,
        liquidity: str,
        response_action: str,
    ) -> str:
        if state == "absent":
            return f"{symbol} stays in monitoring mode while the setup develops."
        if response_action == "block_signal":
            return (
                f"{symbol} has directional context, but risk controls block the signal."
            )
        return f"{direction.title()} continuation with {liquidity} liquidity and {state} conviction."

    def _build_execution_notes(
        self,
        *,
        state: str,
        response_action: str,
        direction: str,
        kelly_result: KellySizingResult | None = None,
    ) -> list[str]:
        notes = [f"Signal direction: {direction}."]
        if response_action == "switch_to_defensive":
            notes.append("Stay defensive and avoid treating this as a full-size setup.")
        elif response_action == "block_signal":
            notes.append("Do not execute until the blocking trigger clears.")
        elif state == "active":
            notes.append("Look for confirmation before any manual execution.")
        elif state == "weakening":
            notes.append(
                "Treat the setup as fragile and wait for cleaner confirmation."
            )
        else:
            notes.append("Stay in monitoring mode and wait for a cleaner setup.")
        if kelly_result is not None:
            sizing_note = self._build_sizing_note(kelly_result)
            if sizing_note:
                notes.append(sizing_note)
        return notes

    @staticmethod
    def _build_sizing_note(kelly_result: KellySizingResult) -> str | None:
        if kelly_result.f is None:
            return "System degraded — advisory size suppressed (0)."
        if kelly_result.ev_gate_triggered:
            if kelly_result.ev_val is not None and kelly_result.ev_val <= 0:
                return "EV ≤ 0 — negative edge, advisory size = 0."
            min_ev = 0.15  # default; caller can override in future
            ev = kelly_result.ev_val or 0.0
            return f"EV {ev:.2f}R below min ({min_ev:.2f}R) — advisory size = 0 (signal still visible)."
        if kelly_result.f is not None and kelly_result.f > 0:
            ev = kelly_result.ev_val or 0.0
            return f"Advisory size: {kelly_result.f * 100:.1f}% equity (fractional Kelly, EV {ev:.2f}R)."
        return None

    def _build_risk_posture(self, response_action: str) -> str:
        if response_action == "warning_only":
            return "normal"
        if response_action == "lower_confidence":
            return "cautious"
        if response_action == "switch_to_defensive":
            return "defensive"
        return "blocked"

    def _build_risk_reward_hint(self, *, direction: str, ranking_score: float) -> str:
        if ranking_score >= 0.72:
            return f"{direction.title()} setup supports a structured asymmetric plan."
        if ranking_score >= 0.45:
            return "Reward is still present, but the edge is narrowing."
        return "No favorable risk/reward framing yet."

    def _build_action_guidance(self, response_action: str) -> str:
        if response_action == "warning_only":
            return (
                "Open Binance in parallel and validate the execution context manually."
            )
        if response_action == "lower_confidence":
            return "Reduce urgency and size assumptions until confidence recovers."
        if response_action == "switch_to_defensive":
            return "Keep the setup visible, but treat it as defensive-only."
        return "Do not execute until the signal or the data quality recovers."

    def _price_hint(self, last_price: float, direction: str, *, mode: str) -> str:
        if direction == "bullish":
            multipliers = {"entry": 1.002, "target": 1.012, "invalidation": 0.994}
        else:
            multipliers = {"entry": 0.998, "target": 0.988, "invalidation": 1.006}
        hinted_price = round(last_price * multipliers[mode], 4)
        if mode == "entry":
            return f"Watch reaction near {hinted_price}"
        if mode == "target":
            return f"First decision zone near {hinted_price}"
        return f"Treat a move through {hinted_price} as invalidation"

    def _build_analyst_note(
        self,
        *,
        symbol: str,
        state: str,
        response_action: str,
        ranking_score: float,
    ) -> str:
        if response_action == "block_signal":
            return f"{symbol} is visible, but risk triggers currently block the signal."
        if response_action == "switch_to_defensive":
            return f"{symbol} remains tradable only in defensive mode."
        if state == "active":
            return f"{symbol} is the cleanest decision-support candidate in the current shortlist."
        if state == "weakening":
            return f"{symbol} still holds context, but the edge is fading ({ranking_score:.2f})."
        if state == "expired":
            return f"{symbol} has an expired decision window and should not be treated as fresh."
        return f"{symbol} remains on the radar without an actionable signal."

    def _display_name(self, symbol: str) -> str:
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]} / USDT"
        return symbol

    def _normalize_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
