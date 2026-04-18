from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from clay.ai_control.service import AIControlService
from clay.config.loader import ConfigLoader
from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.shortlist.read_models import build_shortlist_metrics
from clay.signal_engine.models import (
    EvaluatedSignalSnapshot,
    RiskTriggerSnapshot,
    SignalEngineSnapshot,
)


TIMEFRAME_PRIORITY = {
    "15m": 0,
    "5m": 1,
    "1h": 2,
}


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
    ) -> None:
        self.runtime_manager = runtime_manager
        self.preflight_service = preflight_service
        self.config_loader = config_loader
        self.ai_control_service = ai_control_service

    def build_snapshot(self, session: Session) -> SignalEngineSnapshot:
        runtime_snapshot = self.runtime_manager.snapshot()
        candidates = self._evaluate_candidates(session)
        signals = sorted(
            [candidate.signal for candidate in candidates],
            key=lambda item: item.ranking_score,
            reverse=True,
        )

        market_status = "unknown"
        context_status = "unknown"
        if candidates:
            market_status = self._collapse_status([candidate.market_status for candidate in candidates])
            context_status = self._collapse_status([candidate.context_status for candidate in candidates])

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
            strategy_mode_proposal=self._propose_strategy_mode(signals, runtime_snapshot.state),
            signals=signals,
        )

    def _evaluate_candidates(self, session: Session) -> list[SignalCandidate]:
        market_repo = MarketRepository(session)
        context_repo = ContextRepository(session)
        ops_repo = OpsRepository(session)
        ai_snapshot = self.ai_control_service.build_snapshot()
        risk_config = self.config_loader.load_scope("risk")
        now = datetime.now(UTC)

        bars = market_repo.list_latest_bars(limit=50)
        freshness_rows = market_repo.list_freshness_statuses()
        preferred_bars = self._pick_preferred_bars(bars)
        shortlist_rows = build_shortlist_metrics(preferred_bars, freshness_rows)
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
        ai_penalty = max((row.confidence_penalty for row in ai_snapshot.assignments), default=0.0)
        preflight = self.preflight_service.run()
        runtime_state = self.runtime_manager.snapshot().state

        candidates: list[SignalCandidate] = []
        for row in shortlist_rows:
            bar = next((candidate for candidate in preferred_bars if candidate.symbol == row.symbol), None)
            if bar is None:
                continue

            sentiment_scores = sentiment_map.get(row.symbol, [])
            sentiment_score = sentiment_scores[0] if sentiment_scores else None
            direction = self._resolve_direction(bar.open, bar.close, sentiment_score)
            base_ranking = round(
                (row.rolling_volume_score * 0.55) + (row.rolling_volatility_score * 0.45),
                4,
            )
            market_status = row.availability_status
            context_status = (
                "fresh"
                if row.symbol in news_symbols and sentiment_scores and not any(
                    connector.status in {"degraded", "error"} for connector in connector_rows
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
            response_action = self._resolve_response_action(risk_triggers)
            confidence_penalty = self._resolve_confidence_penalty(
                risk_triggers=risk_triggers,
                degraded_penalty=risk_config.degraded_confidence_penalty,
                ai_penalty=ai_penalty,
            )
            ranking_score = self._apply_ranking_penalty(base_ranking, risk_triggers)
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

            candidates.append(
                SignalCandidate(
                    signal=EvaluatedSignalSnapshot(
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
                        ),
                        risk_triggers=risk_triggers,
                        risk_posture=self._build_risk_posture(response_action),
                        risk_reward_hint=self._build_risk_reward_hint(direction=direction, ranking_score=ranking_score),
                        action_guidance=self._build_action_guidance(response_action),
                        directional_bias=direction,
                        entry_hint=self._price_hint(bar.close, direction, mode="entry"),
                        target_hint=self._price_hint(bar.close, direction, mode="target"),
                        invalidation_hint=self._price_hint(bar.close, direction, mode="invalidation"),
                        analyst_note=self._build_analyst_note(
                            symbol=row.symbol,
                            state=state,
                            response_action=response_action,
                            ranking_score=ranking_score,
                        ),
                        last_updated_at=bar.bar_close_time.isoformat(),
                    ),
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

    def _resolve_direction(self, bar_open: float, bar_close: float, sentiment_score: float | None) -> str:
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
        if any(trigger.response_action == "switch_to_defensive" for trigger in risk_triggers):
            return "switch_to_defensive"
        if any(trigger.response_action == "block_signal" for trigger in risk_triggers):
            return "block_signal"
        if any(trigger.response_action == "lower_confidence" for trigger in risk_triggers):
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
        if any(trigger.trigger_id.startswith("stale-market") for trigger in risk_triggers):
            penalty += degraded_penalty
        if any(trigger.trigger_id == "ai-conflict" for trigger in risk_triggers):
            penalty += max(ai_penalty, round(degraded_penalty / 2, 2))
        if any(trigger.trigger_id.startswith("thin-context") for trigger in risk_triggers):
            penalty += 0.08
        if any(trigger.trigger_id == "runtime-degraded" for trigger in risk_triggers):
            penalty += degraded_penalty
        return round(min(0.8, penalty), 2)

    def _apply_ranking_penalty(self, base_ranking: float, risk_triggers: list[RiskTriggerSnapshot]) -> float:
        ranking = base_ranking
        for trigger in risk_triggers:
            if trigger.response_action == "lower_confidence":
                ranking -= 0.08
            elif trigger.response_action == "block_signal":
                ranking -= 0.2
            elif trigger.response_action == "switch_to_defensive":
                ranking -= 0.15
        return round(max(0.0, min(1.0, ranking)), 2)

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

    def _resolve_strategy_mode(self, ranking_score: float, risk_triggers: list[RiskTriggerSnapshot]) -> str:
        if any(trigger.response_action in {"block_signal", "switch_to_defensive"} for trigger in risk_triggers):
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

    def _propose_strategy_mode(self, signals: list[EvaluatedSignalSnapshot], runtime_state: RuntimeState) -> str:
        if runtime_state == RuntimeState.DEGRADED:
            return "defensive"
        best_signal = next(iter(signals), None)
        if best_signal is None:
            return "defensive"
        return best_signal.strategy_mode

    def _collapse_status(self, statuses: list[str]) -> str:
        if not statuses:
            return "unknown"
        if any(status in {"stale", "error", "degraded", "unknown"} for status in statuses):
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
            return f"{symbol} has directional context, but risk controls block the signal."
        return f"{direction.title()} continuation with {liquidity} liquidity and {state} conviction."

    def _build_execution_notes(self, *, state: str, response_action: str, direction: str) -> list[str]:
        notes = [f"Signal direction: {direction}."]
        if response_action == "switch_to_defensive":
            notes.append("Stay defensive and avoid treating this as a full-size setup.")
        elif response_action == "block_signal":
            notes.append("Do not execute until the blocking trigger clears.")
        elif state == "active":
            notes.append("Look for confirmation before any manual execution.")
        elif state == "weakening":
            notes.append("Treat the setup as fragile and wait for cleaner confirmation.")
        else:
            notes.append("Stay in monitoring mode and wait for a cleaner setup.")
        return notes

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
            return "Open Binance in parallel and validate the execution context manually."
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
