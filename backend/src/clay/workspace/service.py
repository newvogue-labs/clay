from dataclasses import dataclass
from datetime import datetime

from clay.core.clock import Clock, SystemClock

from sqlalchemy.orm import Session, sessionmaker

from clay.db.repositories_context import ContextRepository
from clay.db.repositories_market import MarketRepository
from clay.db.repositories_ops import OpsRepository
from clay.db.repositories_runtime_state import WorkspaceFocusRepository
from clay.freshness.evaluator import (
    collapse_market_statuses,
    resolve_market_freshness_status,
)
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.services.registry import ServiceRegistry
from clay.signal_engine.service import SignalEngineService
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
    confidence_penalty: float
    response_action: str
    strategy_mode: str
    technical_context: list[str]
    execution_notes: list[str]
    risk_posture: str
    confidence_label: str
    risk_reward_hint: str
    action_guidance: str
    active_triggers: list[str]
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
        signal_engine_service: SignalEngineService,
        session_factory: sessionmaker | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.runtime_manager = runtime_manager
        self._clock = clock or SystemClock()
        self.preflight_service = preflight_service
        self.registry = registry
        self.signal_engine_service = signal_engine_service
        self.session_factory = session_factory
        # ``_focus_symbol`` / ``_focus_source`` / ``_selected_signal_id`` are
        # restored from the ``ops.workspace_focus`` singleton row when a
        # ``session_factory`` is supplied. Without one (legacy callers and
        # pre-A5 tests), the service falls back to the in-memory defaults
        # and stays non-persistent.
        if session_factory is None:
            self._focus_symbol: str | None = None
            self._focus_source: str = "system_recommendation"
            self._selected_signal_id: str | None = None
        else:
            with session_factory() as session:
                self._restore_focus_from_db(session)
                session.commit()

    def _restore_focus_from_db(self, session: Session) -> None:
        state = WorkspaceFocusRepository(session).get_or_create()
        # All three fields are safely nullable / have defaults: an empty
        # row is a valid "no focus" state.
        self._focus_symbol = state.focus_symbol
        self._focus_source = state.focus_source
        self._selected_signal_id = state.selected_signal_id

    def set_focus(
        self,
        *,
        symbol: str,
        focus_source: str,
        signal_id: str | None = None,
        session: Session,
    ) -> None:
        self._focus_symbol = symbol
        self._focus_source = focus_source
        self._selected_signal_id = signal_id
        # write-through: persist the new focus immediately. If the DB
        # write raises, in-memory state stays consistent with the previous
        # commit and the caller can safely retry.
        if self.session_factory is not None:
            WorkspaceFocusRepository(session).save(
                focus_symbol=self._focus_symbol,
                focus_source=self._focus_source,
                selected_signal_id=self._selected_signal_id,
            )

    def build_snapshot(self, session: Session) -> WorkspaceSnapshot:
        now = self._clock.now()
        workspace_state, market_status, context_status, last_ingestion_at = (
            self._build_workspace_state(session, now=now)
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
        if self._focus_source == "system_recommendation":
            # Ephemeral focus: refresh in-memory from the auto-pick. This
            # is the normal flow for system-recommendation — it is
            # deterministically recomputed on every build_snapshot and
            # does not need to survive across calls.
            self._focus_symbol = focus_context.symbol
            if focus_context.active_signal_id is not None:
                self._selected_signal_id = focus_context.active_signal_id
        # Else: an explicit (operator- or session-set) focus is in effect.
        # We MUST NOT overwrite it from the auto-pick result: the explicit
        # focus is the whole point of workspace persistence (D1), and a
        # post-restart build_snapshot would otherwise wipe it before the
        # operator can react.
        workspace_state = self._refine_workspace_state(
            base_state=workspace_state,
            focused_signal_state=focus_context.active_signal_state,
        )

        return WorkspaceSnapshot(
            focus_pair=self._build_focus_pair(focus_context),
            workspace_state=workspace_state,
            signals=self._build_signal_summaries(pair_contexts),
            monitoring_pool=self._build_monitoring_pool(
                pair_contexts, focus_context.symbol
            ),
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
                confidence_penalty=focus_context.confidence_penalty,
                response_action=focus_context.response_action,
                strategy_mode=focus_context.strategy_mode,
                risk_reward_hint=focus_context.risk_reward_hint,
                action_guidance=focus_context.action_guidance,
                active_triggers=focus_context.active_triggers,
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
        now: datetime | None = None,
    ) -> tuple[WorkspaceStateSnapshot, str, str, str | None]:
        now = self._clock.now() if now is None else now
        runtime_snapshot = self.runtime_manager.snapshot()
        preflight = self.preflight_service.run()
        market_repo = MarketRepository(session)
        context_repo = ContextRepository(session)
        ops_repo = OpsRepository(session)

        freshness_rows = market_repo.list_freshness_statuses()
        effective_market_statuses = [
            resolve_market_freshness_status(
                stored_status=row.freshness_state,
                timeframe=row.timeframe,
                latest_bar_open_time=row.latest_bar_open_time,
                now=now,
            ).status
            for row in freshness_rows
        ]
        market_status = collapse_market_statuses(effective_market_statuses)
        if market_status in {"stale", "error"}:
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
        if (
            runtime_snapshot.state is RuntimeState.DEGRADED
            or preflight.status == "hard_fail"
        ):
            workspace_posture = "restricted_by_degraded"
            blocking_reason = "runtime is degraded or preflight is blocked"
        elif market_status != "fresh":
            workspace_posture = "defensive"
            blocking_reason = "market freshness requires defensive posture"

        last_ingestion_at = None
        if connector_statuses:
            last_ingestion_at = max(
                row.observed_at.isoformat() for row in connector_statuses
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
        elif focused_signal_state in {"invalidated", "expired"} and posture == "normal":
            posture = "defensive"
            can_log_decision = False

        return WorkspaceStateSnapshot(
            runtime_state=base_state.runtime_state,
            workspace_posture=posture,
            focused_signal_state=focused_signal_state,
            can_open_binance=base_state.can_open_binance,
            can_log_decision=can_log_decision
            and focused_signal_state in {"active", "weakening"},
            blocking_reason=base_state.blocking_reason,
        )

    def _build_pair_contexts(self, session: Session) -> list[PairContext]:
        context_repo = ContextRepository(session)
        market_repo = MarketRepository(session)
        signal_snapshot = self.signal_engine_service.build_snapshot(session)
        bars = market_repo.list_latest_bars(limit=50)
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
                )
            )

        sentiment_by_symbol: dict[str, list[SentimentContextItem]] = {}
        for row in sentiment_rows:
            sentiment_by_symbol.setdefault(row.symbol, []).append(
                SentimentContextItem(
                    source_name=row.source_name,
                    sentiment_label=row.sentiment_label,
                    sentiment_score=row.sentiment_score,
                    captured_at=row.captured_at.isoformat(),
                )
            )

        pair_contexts: list[PairContext] = []
        for index, signal in enumerate(signal_snapshot.signals):
            bar = next(
                (candidate for candidate in bars if candidate.symbol == signal.symbol),
                None,
            )
            if bar is None:
                continue

            pct_change = (
                round(((bar.close - bar.open) / bar.open) * 100, 2) if bar.open else 0.0
            )
            role = "primary" if index == 0 else "backup" if index < 3 else "watch"
            pair_contexts.append(
                PairContext(
                    symbol=signal.symbol,
                    display_name=signal.display_name,
                    role=role,
                    availability_status=signal_snapshot.market_status,
                    last_price=round(bar.close, 4),
                    pct_change_24h=pct_change,
                    volatility=round(min(max(bar.volume / 200, 0.05), 1.0), 2),
                    last_scan_at=signal.last_updated_at,
                    ranking_score=signal.ranking_score,
                    direction=signal.direction,
                    setup_summary=signal.setup_summary,
                    active_signal_state=signal.state,
                    active_signal_id=signal.signal_id
                    if signal.state != "absent"
                    else None,
                    confidence=signal.confidence,
                    confidence_penalty=signal.confidence_penalty,
                    response_action=signal.response_action,
                    strategy_mode=signal.strategy_mode,
                    technical_context=signal.technical_context,
                    execution_notes=signal.execution_notes,
                    risk_posture=signal.risk_posture,
                    confidence_label=self._confidence_label(signal.confidence),
                    risk_reward_hint=signal.risk_reward_hint,
                    action_guidance=signal.action_guidance,
                    active_triggers=[trigger.title for trigger in signal.risk_triggers],
                    situation_bias=signal.directional_bias,
                    entry_hint=signal.entry_hint,
                    target_hint=signal.target_hint,
                    invalidation_hint=signal.invalidation_hint,
                    analyst_note=signal.analyst_note,
                    news=news_by_symbol.get(signal.symbol, [])[:3],
                    sentiment=sentiment_by_symbol.get(signal.symbol, [])[:3],
                )
            )
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
        self, pair_contexts: list[PairContext]
    ) -> list[WorkspaceSignalSummary]:
        return [
            WorkspaceSignalSummary(
                signal_id=item.active_signal_id or f"watch-{item.symbol.lower()}",
                pair=item.symbol,
                direction=item.direction,
                state=item.active_signal_state,
                confidence=item.confidence,
                ranking_score=item.ranking_score,
                confidence_penalty=item.confidence_penalty,
                response_action=item.response_action,
                strategy_mode=item.strategy_mode,
                setup_summary=item.setup_summary,
                last_updated_at=item.last_scan_at,
            )
            for item in pair_contexts
            if item.active_signal_state
            in {"active", "weakening", "invalidated", "expired"}
        ]

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
            base_state=workspace_state, focused_signal_state="absent"
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
                technical_context=[
                    "Workspace is waiting for storage-backed market data."
                ],
                execution_notes=["Run ingestion and re-open the workspace."],
            ),
            risk=RiskSnapshot(
                risk_posture="monitoring_only",
                confidence_label="low",
                confidence_penalty=0.0,
                response_action="warning_only",
                strategy_mode="defensive",
                risk_reward_hint="No risk framing available yet.",
                action_guidance="Stay in monitoring mode until data arrives.",
                active_triggers=[],
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

    def _confidence_label(self, confidence: float) -> str:
        if confidence >= 0.8:
            return "high"
        if confidence >= 0.55:
            return "medium"
        return "low"
