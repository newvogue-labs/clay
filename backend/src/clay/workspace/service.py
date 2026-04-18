from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.services.registry import ServiceRegistry
from clay.shortlist.read_models import build_shortlist_metrics
from clay.workspace.models import (
    FocusPairSnapshot,
    FocusSelectionSnapshot,
    MonitoringPoolItem,
    NewsContextItem,
    ReasoningSnapshot,
    RiskSnapshot,
    SentimentContextItem,
    SituationMapSnapshot,
    UpdateMetaSnapshot,
    WorkspaceSignalSummary,
    WorkspaceSnapshot,
    WorkspaceStateSnapshot,
)


TIMEFRAME_PRIORITY = {
    "15m": 0,
    "5m": 1,
    "1h": 2,
}


@dataclass(slots=True)
class PairContext:
    symbol: str
    display_name: str
    role: str
    availability_status: str
    last_price: float
    pct_change_24h: float
    volatility: float
    last_scan_at: str
    ranking_score: float
    direction: str
    setup_summary: str
    active_signal_state: str
    active_signal_id: str | None
    confidence: float
    technical_context: list[str]
    execution_notes: list[str]
    risk_posture: str
    confidence_label: str
    risk_reward_hint: str
    action_guidance: str
    situation_bias: str
    entry_hint: str
    target_hint: str
    invalidation_hint: str
    analyst_note: str
    news: list[NewsContextItem]
    sentiment: list[SentimentContextItem]


class WorkspaceService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        preflight_service: PreflightService,
        registry: ServiceRegistry,
    ) -> None:
        self.runtime_manager = runtime_manager
        self.preflight_service = preflight_service
        self.registry = registry
        self._focus_symbol: str | None = None
        self._focus_source: str = "system_recommendation"
        self._selected_signal_id: str | None = None

    def set_focus(
        self,
        *,
        symbol: str,
        focus_source: str,
        signal_id: str | None = None,
    ) -> None:
        self._focus_symbol = symbol
        self._focus_source = focus_source
        self._selected_signal_id = signal_id

    def build_snapshot(self, session: Session) -> WorkspaceSnapshot:
        now = datetime.now(UTC)
        workspace_state, market_status, context_status, last_ingestion_at = (
            self._build_workspace_state(session)
        )
        pair_contexts = self._build_pair_contexts(session)
        if not pair_contexts:
            return self._build_empty_snapshot(
                now=now,
                workspace_state=workspace_state,
                market_status=market_status,
                context_status=context_status,
                last_ingestion_at=last_ingestion_at,
            )

        focus_context = self._pick_focus_context(pair_contexts)
        self._focus_symbol = focus_context.symbol
        if focus_context.active_signal_id is not None:
            self._selected_signal_id = focus_context.active_signal_id
        workspace_state = self._refine_workspace_state(
            base_state=workspace_state,
            focused_signal_state=focus_context.active_signal_state,
        )

        focus_pair = self._build_focus_pair(focus_context)
        return WorkspaceSnapshot(
            focus_pair=focus_pair,
            workspace_state=workspace_state,
            signals=self._build_signal_summaries(pair_contexts),
            monitoring_pool=self._build_monitoring_pool(pair_contexts, focus_context.symbol),
            situation_map=SituationMapSnapshot(
                directional_bias=focus_context.situation_bias,
                entry_hint=focus_context.entry_hint,
                target_hint=focus_context.target_hint,
                invalidation_hint=focus_context.invalidation_hint,
                analyst_note=focus_context.analyst_note,
            ),
            reasoning=ReasoningSnapshot(
                thesis=focus_context.setup_summary,
                technical_context=focus_context.technical_context,
                execution_notes=focus_context.execution_notes,
            ),
            risk=RiskSnapshot(
                risk_posture=focus_context.risk_posture,
                confidence_label=focus_context.confidence_label,
                risk_reward_hint=focus_context.risk_reward_hint,
                action_guidance=focus_context.action_guidance,
            ),
            news=focus_context.news,
            sentiment=focus_context.sentiment,
            update_meta=UpdateMetaSnapshot(
                focus_last_updated_at=focus_context.last_scan_at,
                market_status=market_status,
                context_status=context_status,
                last_ingestion_at=last_ingestion_at,
            ),
        )

    def build_focus_snapshot(self, session: Session) -> FocusSelectionSnapshot:
        snapshot = self.build_snapshot(session)
        return FocusSelectionSnapshot(
            focus_pair=snapshot.focus_pair,
            workspace_state=snapshot.workspace_state,
        )

    def _build_workspace_state(
        self,
        session: Session,
    ) -> tuple[WorkspaceStateSnapshot, str, str, str | None]:
        runtime_snapshot = self.runtime_manager.snapshot()
        preflight = self.preflight_service.run()
        market_repo = MarketRepository(session)
        context_repo = ContextRepository(session)
        ops_repo = OpsRepository(session)

        freshness_rows = market_repo.list_freshness_statuses()
        market_status = "fresh"
        if not freshness_rows:
            market_status = "unknown"
        elif any(row.freshness_state in {"stale", "error", "unknown"} for row in freshness_rows):
            market_status = "degraded"

        latest_news = context_repo.latest_news(limit=10)
        latest_sentiment = context_repo.latest_sentiment(limit=10)
        connector_statuses = ops_repo.latest_connector_statuses()
        context_status = "fresh"
        if (
            not latest_news
            or not latest_sentiment
            or any(row.status in {"degraded", "error"} for row in connector_statuses)
        ):
            context_status = "degraded"

        blocking_reason: str | None = None
        workspace_posture = "normal"
        if runtime_snapshot.state is RuntimeState.DEGRADED or preflight.status == "hard_fail":
            workspace_posture = "restricted_by_degraded"
            blocking_reason = "runtime is degraded or preflight is blocked"
        elif market_status != "fresh":
            workspace_posture = "defensive"
            blocking_reason = "market freshness requires defensive posture"

        last_ingestion_at = None
        if connector_statuses:
            last_ingestion_at = max(
                row.observed_at.isoformat()
                for row in connector_statuses
            )

        return (
            WorkspaceStateSnapshot(
                runtime_state=runtime_snapshot.state.value,
                workspace_posture=workspace_posture,
                focused_signal_state="absent",
                can_open_binance=blocking_reason is None,
                can_log_decision=blocking_reason is None,
                blocking_reason=blocking_reason,
            ),
            market_status,
            context_status,
            last_ingestion_at,
        )

    def _refine_workspace_state(
        self,
        *,
        base_state: WorkspaceStateSnapshot,
        focused_signal_state: str,
    ) -> WorkspaceStateSnapshot:
        posture = base_state.workspace_posture
        can_log_decision = base_state.can_log_decision
        if focused_signal_state == "absent" and posture == "normal":
            posture = "monitoring_only"
            can_log_decision = False
        elif focused_signal_state == "invalidated" and posture == "normal":
            posture = "defensive"
            can_log_decision = False

        return WorkspaceStateSnapshot(
            runtime_state=base_state.runtime_state,
            workspace_posture=posture,
            focused_signal_state=focused_signal_state,
            can_open_binance=base_state.can_open_binance,
            can_log_decision=can_log_decision and focused_signal_state in {"active", "weakening"},
            blocking_reason=base_state.blocking_reason,
        )

    def _build_pair_contexts(self, session: Session) -> list[PairContext]:
        market_repo = MarketRepository(session)
        context_repo = ContextRepository(session)
        bars = market_repo.list_latest_bars(limit=50)
        freshness_rows = market_repo.list_freshness_statuses()
        preferred_bars = self._pick_preferred_bars(bars)
        shortlist_rows = build_shortlist_metrics(preferred_bars, freshness_rows)
        news_rows = context_repo.latest_news(limit=20)
        sentiment_rows = context_repo.latest_sentiment(limit=20)

        news_by_symbol: dict[str, list[NewsContextItem]] = {}
        for row in news_rows:
            if row.symbol is None:
                continue
            news_by_symbol.setdefault(row.symbol, []).append(
                NewsContextItem(
                    headline=row.headline,
                    summary=row.summary,
                    source_name=row.source_name,
                    published_at=row.published_at.isoformat(),
                    source_url=row.source_url,
                ),
            )

        sentiment_by_symbol: dict[str, list[SentimentContextItem]] = {}
        for row in sentiment_rows:
            sentiment_by_symbol.setdefault(row.symbol, []).append(
                SentimentContextItem(
                    source_name=row.source_name,
                    sentiment_label=row.sentiment_label,
                    sentiment_score=row.sentiment_score,
                    captured_at=row.captured_at.isoformat(),
                ),
            )

        pair_contexts: list[PairContext] = []
        for index, row in enumerate(shortlist_rows):
            bar = next((candidate for candidate in preferred_bars if candidate.symbol == row.symbol), None)
            if bar is None:
                continue

            pct_change = round(((bar.close - bar.open) / bar.open) * 100, 2) if bar.open else 0.0
            direction = self._resolve_direction(
                symbol=row.symbol,
                bar_open=bar.open,
                bar_close=bar.close,
                sentiment_items=sentiment_by_symbol.get(row.symbol, []),
            )
            ranking_score = round(
                (row.rolling_volume_score * 0.55) + (row.rolling_volatility_score * 0.45),
                4,
            )
            signal_state = self._resolve_signal_state(
                availability_status=row.availability_status,
                ranking_score=ranking_score,
            )
            confidence = self._resolve_confidence(
                ranking_score=ranking_score,
                sentiment_items=sentiment_by_symbol.get(row.symbol, []),
                availability_status=row.availability_status,
            )
            active_signal_id = None
            if signal_state in {"active", "weakening", "invalidated"}:
                active_signal_id = f"sig-{row.symbol.lower()}"

            role = "primary" if index == 0 else "backup" if index < 3 else "watch"
            pair_contexts.append(
                PairContext(
                    symbol=row.symbol,
                    display_name=self._display_name(row.symbol),
                    role=role,
                    availability_status=row.availability_status,
                    last_price=round(bar.close, 4),
                    pct_change_24h=pct_change,
                    volatility=row.rolling_volatility_score,
                    last_scan_at=bar.bar_close_time.isoformat(),
                    ranking_score=ranking_score,
                    direction=direction,
                    setup_summary=self._build_setup_summary(
                        direction=direction,
                        signal_state=signal_state,
                        liquidity=row.liquidity_summary,
                        symbol=row.symbol,
                    ),
                    active_signal_state=signal_state,
                    active_signal_id=active_signal_id,
                    confidence=confidence,
                    technical_context=[
                        f"Liquidity {row.liquidity_summary}",
                        f"Volatility score {row.rolling_volatility_score:.2f}",
                        f"Availability {row.availability_status}",
                    ],
                    execution_notes=self._build_execution_notes(
                        signal_state=signal_state,
                        direction=direction,
                        availability_status=row.availability_status,
                    ),
                    risk_posture=self._build_risk_posture(signal_state),
                    confidence_label=self._confidence_label(confidence),
                    risk_reward_hint=self._build_risk_reward_hint(
                        direction=direction,
                        ranking_score=ranking_score,
                    ),
                    action_guidance=self._build_action_guidance(signal_state),
                    situation_bias=direction,
                    entry_hint=self._price_hint(bar.close, direction, mode="entry"),
                    target_hint=self._price_hint(bar.close, direction, mode="target"),
                    invalidation_hint=self._price_hint(bar.close, direction, mode="invalidation"),
                    analyst_note=self._build_analyst_note(
                        symbol=row.symbol,
                        signal_state=signal_state,
                        ranking_score=ranking_score,
                    ),
                    news=news_by_symbol.get(row.symbol, [])[:3],
                    sentiment=sentiment_by_symbol.get(row.symbol, [])[:3],
                ),
            )

        pair_contexts.sort(key=lambda item: item.ranking_score, reverse=True)
        return pair_contexts[:5]

    def _pick_focus_context(self, pair_contexts: list[PairContext]) -> PairContext:
        by_symbol = {item.symbol: item for item in pair_contexts}
        if self._focus_symbol in by_symbol:
            return by_symbol[self._focus_symbol]

        if self._selected_signal_id is not None:
            selected = next(
                (
                    item
                    for item in pair_contexts
                    if item.active_signal_id == self._selected_signal_id
                ),
                None,
            )
            if selected is not None:
                return selected

        active = next(
            (item for item in pair_contexts if item.active_signal_state == "active"),
            None,
        )
        if active is not None:
            self._focus_source = "system_recommendation"
            return active

        self._focus_source = "system_recommendation"
        return pair_contexts[0]

    def _build_focus_pair(self, focus_context: PairContext) -> FocusPairSnapshot:
        return FocusPairSnapshot(
            symbol=focus_context.symbol,
            display_name=focus_context.display_name,
            is_focused=True,
            role=focus_context.role,
            last_price=focus_context.last_price,
            pct_change_24h=focus_context.pct_change_24h,
            volatility=focus_context.volatility,
            last_scan_at=focus_context.last_scan_at,
            active_signal_id=focus_context.active_signal_id,
            focus_source=self._focus_source,
        )

    def _build_signal_summaries(
        self,
        pair_contexts: list[PairContext],
    ) -> list[WorkspaceSignalSummary]:
        items = [
            WorkspaceSignalSummary(
                signal_id=item.active_signal_id or f"watch-{item.symbol.lower()}",
                pair=item.symbol,
                direction=item.direction,
                state=item.active_signal_state,
                confidence=item.confidence,
                ranking_score=item.ranking_score,
                setup_summary=item.setup_summary,
                last_updated_at=item.last_scan_at,
            )
            for item in pair_contexts
            if item.active_signal_state in {"active", "weakening", "invalidated"}
        ]
        return items

    def _build_monitoring_pool(
        self,
        pair_contexts: list[PairContext],
        focus_symbol: str,
    ) -> list[MonitoringPoolItem]:
        return [
            MonitoringPoolItem(
                symbol=item.symbol,
                display_name=item.display_name,
                role=item.role,
                availability_status=item.availability_status,
                last_price=item.last_price,
                pct_change_24h=item.pct_change_24h,
                volatility=item.volatility,
                has_active_signal=item.active_signal_id is not None,
                is_focused=item.symbol == focus_symbol,
            )
            for item in pair_contexts
        ]

    def _build_empty_snapshot(
        self,
        *,
        now: datetime,
        workspace_state: WorkspaceStateSnapshot,
        market_status: str,
        context_status: str,
        last_ingestion_at: str | None,
    ) -> WorkspaceSnapshot:
        focus_pair = FocusPairSnapshot(
            symbol="BTCUSDT",
            display_name="BTC / USDT",
            is_focused=True,
            role="primary",
            last_price=0.0,
            pct_change_24h=0.0,
            volatility=0.0,
            last_scan_at=now.isoformat(),
            active_signal_id=None,
            focus_source="system_recommendation",
        )
        refined_state = self._refine_workspace_state(
            base_state=workspace_state,
            focused_signal_state="absent",
        )
        return WorkspaceSnapshot(
            focus_pair=focus_pair,
            workspace_state=refined_state,
            signals=[],
            monitoring_pool=[],
            situation_map=SituationMapSnapshot(
                directional_bias="neutral",
                entry_hint="No fresh market snapshot yet",
                target_hint="Run ingestion to populate the workspace",
                invalidation_hint="Do not treat this state as actionable",
                analyst_note="Workspace is waiting for market/context bootstrap data.",
            ),
            reasoning=ReasoningSnapshot(
                thesis="No active signal yet.",
                technical_context=["Workspace is waiting for storage-backed market data."],
                execution_notes=["Run ingestion and re-open the workspace."],
            ),
            risk=RiskSnapshot(
                risk_posture="monitoring_only",
                confidence_label="low",
                risk_reward_hint="No risk framing available yet.",
                action_guidance="Stay in monitoring mode until data arrives.",
            ),
            news=[],
            sentiment=[],
            update_meta=UpdateMetaSnapshot(
                focus_last_updated_at=now.isoformat(),
                market_status=market_status,
                context_status=context_status,
                last_ingestion_at=last_ingestion_at,
            ),
        )

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
        self,
        *,
        symbol: str,
        bar_open: float,
        bar_close: float,
        sentiment_items: list[SentimentContextItem],
    ) -> str:
        if sentiment_items:
            top = sentiment_items[0]
            if top.sentiment_score >= 0.6:
                return "bullish"
            if top.sentiment_score <= 0.4:
                return "bearish"
        return "bullish" if bar_close >= bar_open else "bearish"

    def _resolve_signal_state(
        self,
        *,
        availability_status: str,
        ranking_score: float,
    ) -> str:
        if availability_status != "fresh":
            return "invalidated"
        if ranking_score >= 0.72:
            return "active"
        if ranking_score >= 0.45:
            return "weakening"
        return "absent"

    def _resolve_confidence(
        self,
        *,
        ranking_score: float,
        sentiment_items: list[SentimentContextItem],
        availability_status: str,
    ) -> float:
        confidence = ranking_score
        if sentiment_items:
            confidence = min(1.0, confidence + 0.08)
        if availability_status != "fresh":
            confidence = max(0.1, confidence - 0.25)
        return round(confidence, 2)

    def _build_setup_summary(
        self,
        *,
        direction: str,
        signal_state: str,
        liquidity: str,
        symbol: str,
    ) -> str:
        if signal_state == "absent":
            return f"{symbol} stays in monitoring mode while the setup develops."
        return f"{direction.title()} continuation with {liquidity} liquidity and {signal_state} conviction."

    def _build_execution_notes(
        self,
        *,
        signal_state: str,
        direction: str,
        availability_status: str,
    ) -> list[str]:
        notes = [f"Signal direction: {direction}."]
        if signal_state == "active":
            notes.append("Look for confirmation on Binance before any manual execution.")
        elif signal_state == "weakening":
            notes.append("Treat the setup as fragile and wait for cleaner confirmation.")
        elif signal_state == "invalidated":
            notes.append("Do not treat this setup as actionable until freshness recovers.")
        else:
            notes.append("Stay in monitoring mode and wait for a cleaner setup.")
        notes.append(f"Availability status is {availability_status}.")
        return notes

    def _build_risk_posture(self, signal_state: str) -> str:
        if signal_state == "active":
            return "normal"
        if signal_state == "weakening":
            return "defensive"
        return "monitoring_only"

    def _confidence_label(self, confidence: float) -> str:
        if confidence >= 0.8:
            return "high"
        if confidence >= 0.55:
            return "medium"
        return "low"

    def _build_risk_reward_hint(self, *, direction: str, ranking_score: float) -> str:
        if ranking_score >= 0.72:
            return f"{direction.title()} setup supports a structured asymmetric plan."
        if ranking_score >= 0.45:
            return "Reward is still present, but the edge is narrowing."
        return "No favorable risk/reward framing yet."

    def _build_action_guidance(self, signal_state: str) -> str:
        if signal_state == "active":
            return "Open Binance in parallel and validate the execution context manually."
        if signal_state == "weakening":
            return "Reduce urgency and wait for stronger confirmation."
        if signal_state == "invalidated":
            return "Do not execute until the signal or freshness recovers."
        return "Keep monitoring and do not force a trade."

    def _price_hint(self, last_price: float, direction: str, *, mode: str) -> str:
        if direction == "bullish":
            multipliers = {
                "entry": 1.002,
                "target": 1.012,
                "invalidation": 0.994,
            }
        else:
            multipliers = {
                "entry": 0.998,
                "target": 0.988,
                "invalidation": 1.006,
            }
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
        signal_state: str,
        ranking_score: float,
    ) -> str:
        if signal_state == "active":
            return f"{symbol} is the cleanest decision-support candidate in the current shortlist."
        if signal_state == "weakening":
            return f"{symbol} still holds context, but the edge is fading ({ranking_score:.2f})."
        if signal_state == "invalidated":
            return f"{symbol} is visible, but the signal is blocked by degraded freshness."
        return f"{symbol} remains on the radar without an actionable signal."

    def _display_name(self, symbol: str) -> str:
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base} / USDT"
        return symbol
