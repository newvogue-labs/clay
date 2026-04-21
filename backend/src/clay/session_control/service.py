from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState
from clay.session_control.models import (
    PairReplacementReviewSnapshot,
    SessionBriefingSignal,
    SessionBriefingSnapshot,
    SessionControlSnapshot,
    SessionLifecycleSnapshot,
    SessionPreflightCheck,
    SessionPreflightSnapshot,
)
from clay.signal_engine.service import SignalEngineService
from clay.workspace.service import WorkspaceService


@dataclass
class ActiveSessionRecord:
    session_id: str
    current_pair_symbol: str
    current_signal_id: str | None
    strategy_mode: str
    started_at: datetime
    paused_at: datetime | None = None


@dataclass
class PendingReplacementReview:
    review_id: str
    current_symbol: str
    proposed_symbol: str
    created_at: datetime


class SessionControlService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        signal_engine_service: SignalEngineService,
        ai_control_service: AIControlService,
        workspace_service: WorkspaceService,
        audit_writer: AuditWriter,
        event_bus: EventBus,
    ) -> None:
        self.runtime_manager = runtime_manager
        self.signal_engine_service = signal_engine_service
        self.ai_control_service = ai_control_service
        self.workspace_service = workspace_service
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self._active_session: ActiveSessionRecord | None = None
        self._pending_replacement: PendingReplacementReview | None = None

    def build_snapshot(self, session: Session) -> SessionControlSnapshot:
        signal_snapshot = self.signal_engine_service.build_snapshot(session)
        ai_snapshot = self.ai_control_service.build_snapshot(session)
        preflight = self._build_preflight(session, signal_snapshot, ai_snapshot)
        briefing = self._build_briefing(signal_snapshot, ai_snapshot)
        lifecycle = self._build_lifecycle(preflight)
        pending_replacement = self._build_pending_replacement(signal_snapshot)
        return SessionControlSnapshot(
            preflight=preflight,
            briefing=briefing,
            lifecycle=lifecycle,
            pending_pair_replacement=pending_replacement,
        )

    def start_session(self, session: Session) -> SessionControlSnapshot:
        snapshot = self.build_snapshot(session)
        if snapshot.preflight.status != "pass":
            raise ValueError(snapshot.preflight.blocking_reason or "preflight blocked")

        top_signal = next(
            (
                signal
                for signal in snapshot.briefing.shortlist
                if signal.state in {"active", "weakening"}
            ),
            None,
        )
        if top_signal is None:
            raise ValueError("no eligible signal to start session")

        if self.runtime_manager.snapshot().state == RuntimeState.BACKGROUND_MONITORING:
            self.runtime_manager.transition_to(RuntimeState.PRE_SESSION)
        if self.runtime_manager.snapshot().state == RuntimeState.PRE_SESSION:
            self.runtime_manager.transition_to(RuntimeState.ACTIVE_SESSION)

        self.workspace_service.set_focus(
            symbol=top_signal.symbol,
            focus_source="session_start",
            signal_id=top_signal.signal_id,
        )
        self._active_session = ActiveSessionRecord(
            session_id=str(uuid4()),
            current_pair_symbol=top_signal.symbol,
            current_signal_id=top_signal.signal_id,
            strategy_mode=snapshot.briefing.active_strategy,
            started_at=datetime.now(UTC),
        )
        self._pending_replacement = None
        self._write_and_publish(
            "session.started",
            {
                "session_id": self._active_session.session_id,
                "symbol": top_signal.symbol,
                "signal_id": top_signal.signal_id,
            },
        )
        return self.build_snapshot(session)

    def pause_session(self, session: Session) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        if self.runtime_manager.snapshot().state != RuntimeState.ACTIVE_SESSION:
            raise ValueError("runtime is not in active_session")
        self.runtime_manager.transition_to(RuntimeState.PAUSED)
        self._active_session.paused_at = datetime.now(UTC)
        self._write_and_publish(
            "session.paused",
            {"session_id": self._active_session.session_id},
        )
        return self.build_snapshot(session)

    def resume_session(self, session: Session) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        if self.runtime_manager.snapshot().state != RuntimeState.PAUSED:
            raise ValueError("runtime is not paused")
        self.runtime_manager.transition_to(RuntimeState.ACTIVE_SESSION)
        self._active_session.paused_at = None
        self._write_and_publish(
            "session.resumed",
            {"session_id": self._active_session.session_id},
        )
        return self.build_snapshot(session)

    def complete_session(self, session: Session) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        state = self.runtime_manager.snapshot().state
        if state not in {RuntimeState.ACTIVE_SESSION, RuntimeState.PAUSED}:
            raise ValueError("session is not active")
        self.runtime_manager.transition_to(RuntimeState.REVIEW)
        self._write_and_publish(
            "session.completed",
            {"session_id": self._active_session.session_id},
        )
        self._active_session = None
        self._pending_replacement = None
        return self.build_snapshot(session)

    def review_pair_replacement(
        self,
        session: Session,
        *,
        proposed_symbol: str | None = None,
    ) -> PairReplacementReviewSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")

        signal_snapshot = self.signal_engine_service.build_snapshot(session)
        current_signal = next(
            (signal for signal in signal_snapshot.signals if signal.symbol == self._active_session.current_pair_symbol),
            None,
        )
        candidate = self._pick_replacement_candidate(signal_snapshot, proposed_symbol=proposed_symbol)
        if candidate is None:
            raise ValueError("no replacement candidate available")
        if candidate.symbol == self._active_session.current_pair_symbol:
            raise ValueError("replacement candidate matches current pair")

        self._pending_replacement = PendingReplacementReview(
            review_id=str(uuid4()),
            current_symbol=self._active_session.current_pair_symbol,
            proposed_symbol=candidate.symbol,
            created_at=datetime.now(UTC),
        )
        review = self._build_replacement_review(current_signal=current_signal, candidate=candidate)
        self._write_and_publish(
            "session.replacement.reviewed",
            {
                "review_id": review.review_id,
                "current_symbol": review.current_symbol,
                "proposed_symbol": review.proposed_symbol,
            },
        )
        return review

    def apply_pair_replacement(self, session: Session, review_id: str) -> SessionControlSnapshot:
        if self._active_session is None:
            raise ValueError("no active session")
        if self._pending_replacement is None or self._pending_replacement.review_id != review_id:
            raise ValueError("pair replacement review is missing or stale")

        signal_snapshot = self.signal_engine_service.build_snapshot(session)
        candidate = next(
            (signal for signal in signal_snapshot.signals if signal.symbol == self._pending_replacement.proposed_symbol),
            None,
        )
        if candidate is None:
            raise ValueError("replacement candidate is no longer available")

        self._active_session.current_pair_symbol = candidate.symbol
        self._active_session.current_signal_id = candidate.signal_id
        self.workspace_service.set_focus(
            symbol=candidate.symbol,
            focus_source="session_replacement",
            signal_id=candidate.signal_id,
        )
        self._write_and_publish(
            "session.replacement.applied",
            {
                "session_id": self._active_session.session_id,
                "review_id": review_id,
                "symbol": candidate.symbol,
                "signal_id": candidate.signal_id,
            },
        )
        self._pending_replacement = None
        return self.build_snapshot(session)

    def _build_preflight(
        self,
        session: Session,
        signal_snapshot,
        ai_snapshot,
    ) -> SessionPreflightSnapshot:
        del session
        control_api_ready = False
        try:
            control_api = self.runtime_manager.registry.get("control-api")
            control_api_ready = control_api.status.value in {"healthy", "degraded"}
        except KeyError:
            control_api_ready = False

        checks = [
            SessionPreflightCheck(
                check_id="data-freshness",
                label="Data freshness",
                status="ok" if signal_snapshot.market_status == "fresh" else "hard_fail",
                reason=(
                    "Market data is fresh enough for session start."
                    if signal_snapshot.market_status == "fresh"
                    else "Market data is degraded or stale."
                ),
                blocks_start=signal_snapshot.market_status != "fresh",
            ),
            SessionPreflightCheck(
                check_id="api-availability",
                label="API availability",
                status="ok" if control_api_ready else "hard_fail",
                reason=(
                    "Control API service is registered and available."
                    if control_api_ready
                    else "Control API service is missing or not ready."
                ),
                blocks_start=not control_api_ready,
            ),
            SessionPreflightCheck(
                check_id="active-model-loaded",
                label="Active models loaded",
                status="ok" if ai_snapshot.summary.degraded_role_count == 0 else "hard_fail",
                reason=(
                    "All active AI roles are healthy."
                    if ai_snapshot.summary.degraded_role_count == 0
                    else "One or more AI roles are degraded."
                ),
                blocks_start=ai_snapshot.summary.degraded_role_count > 0,
            ),
            SessionPreflightCheck(
                check_id="shortlist-confirmed",
                label="Shortlist confirmed",
                status=(
                    "ok"
                    if any(signal.state in {"active", "weakening"} for signal in signal_snapshot.signals)
                    else "hard_fail"
                ),
                reason=(
                    "At least one ranked signal is available."
                    if any(signal.state in {"active", "weakening"} for signal in signal_snapshot.signals)
                    else "No ranked signal is ready for session start."
                ),
                blocks_start=not any(signal.state in {"active", "weakening"} for signal in signal_snapshot.signals),
            ),
            SessionPreflightCheck(
                check_id="strategy-confirmed",
                label="Strategy confirmed",
                status="ok" if signal_snapshot.strategy_mode_proposal else "hard_fail",
                reason=(
                    f"Strategy proposal is {signal_snapshot.strategy_mode_proposal}."
                    if signal_snapshot.strategy_mode_proposal
                    else "No strategy mode proposal is available."
                ),
                blocks_start=not bool(signal_snapshot.strategy_mode_proposal),
            ),
            SessionPreflightCheck(
                check_id="risk-limits-active",
                label="Risk limits active",
                status="ok",
                reason="Risk configuration is loaded and confidence penalties are active.",
                blocks_start=False,
            ),
        ]

        blockers = [check.reason for check in checks if check.blocks_start]
        return SessionPreflightSnapshot(
            status="hard_fail" if blockers else "pass",
            blocking_reason=blockers[0] if blockers else None,
            checks=checks,
        )

    def _build_briefing(self, signal_snapshot, ai_snapshot) -> SessionBriefingSnapshot:
        shortlist = [
            SessionBriefingSignal(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                direction=signal.direction,
                state=signal.state,
                confidence=signal.confidence,
                ranking_score=signal.ranking_score,
                setup_summary=signal.setup_summary,
            )
            for signal in signal_snapshot.signals[:3]
        ]
        risk_alerts = [
            f"{signal.symbol}: {trigger.title}"
            for signal in signal_snapshot.signals[:3]
            for trigger in signal.risk_triggers
        ]
        sentiment_summary = (
            "Signals show acceptable context coverage."
            if signal_snapshot.context_status == "fresh"
            else "Context coverage is thin; confidence penalties remain active."
        )
        market_context = (
            f"Market status is {signal_snapshot.market_status}, workspace posture is {signal_snapshot.workspace_posture}."
        )
        ai_summary = (
            f"Chief Agent uses {ai_snapshot.summary.chief_agent_model}. "
            f"Active AI conflicts: {ai_snapshot.summary.active_conflict_count}."
        )
        return SessionBriefingSnapshot(
            shortlist=shortlist,
            market_context=market_context,
            sentiment_summary=sentiment_summary,
            active_strategy=signal_snapshot.strategy_mode_proposal,
            risk_alerts=risk_alerts or ["No elevated risk alerts in the current shortlist."],
            ai_summary=ai_summary,
        )

    def _build_lifecycle(self, preflight: SessionPreflightSnapshot) -> SessionLifecycleSnapshot:
        runtime_state = self.runtime_manager.snapshot().state
        if self._active_session is None and runtime_state == RuntimeState.REVIEW:
            lifecycle_state: str = "review"
        elif self._active_session is None:
            lifecycle_state: str = "idle"
        elif runtime_state == RuntimeState.PAUSED:
            lifecycle_state = "paused"
        elif runtime_state == RuntimeState.ACTIVE_SESSION:
            lifecycle_state = "active_session"
        elif runtime_state == RuntimeState.PRE_SESSION:
            lifecycle_state = "pre_session"
        else:
            lifecycle_state = "review"

        return SessionLifecycleSnapshot(
            lifecycle_state=lifecycle_state,
            runtime_state=runtime_state.value,
            session_id=self._active_session.session_id if self._active_session else None,
            current_pair_symbol=self._active_session.current_pair_symbol if self._active_session else None,
            current_signal_id=self._active_session.current_signal_id if self._active_session else None,
            started_at=self._active_session.started_at.isoformat() if self._active_session else None,
            paused_at=self._active_session.paused_at.isoformat() if self._active_session and self._active_session.paused_at else None,
            resume_ready=runtime_state == RuntimeState.PAUSED and self._active_session is not None,
            can_start=preflight.status == "pass" and self._active_session is None and runtime_state != RuntimeState.REVIEW,
            can_pause=runtime_state == RuntimeState.ACTIVE_SESSION and self._active_session is not None,
            can_resume=runtime_state == RuntimeState.PAUSED and self._active_session is not None,
            can_complete=runtime_state in {RuntimeState.ACTIVE_SESSION, RuntimeState.PAUSED} and self._active_session is not None,
        )

    def _build_pending_replacement(self, signal_snapshot) -> PairReplacementReviewSnapshot | None:
        if self._pending_replacement is None or self._active_session is None:
            return None
        current_signal = next(
            (signal for signal in signal_snapshot.signals if signal.symbol == self._pending_replacement.current_symbol),
            None,
        )
        candidate = next(
            (signal for signal in signal_snapshot.signals if signal.symbol == self._pending_replacement.proposed_symbol),
            None,
        )
        if candidate is None:
            return None
        return self._build_replacement_review(current_signal=current_signal, candidate=candidate)

    def _pick_replacement_candidate(self, signal_snapshot, *, proposed_symbol: str | None):
        if proposed_symbol is not None:
            return next((signal for signal in signal_snapshot.signals if signal.symbol == proposed_symbol), None)
        current_symbol = self._active_session.current_pair_symbol if self._active_session else None
        current_signal = next(
            (signal for signal in signal_snapshot.signals if signal.symbol == current_symbol),
            None,
        )
        for signal in signal_snapshot.signals:
            if signal.symbol == current_symbol:
                continue
            if signal.state not in {"active", "weakening"}:
                continue
            if current_signal is None or signal.ranking_score > current_signal.ranking_score + 0.08:
                return signal
        return None

    def _build_replacement_review(self, *, current_signal, candidate) -> PairReplacementReviewSnapshot:
        current_symbol = current_signal.symbol if current_signal is not None else self._active_session.current_pair_symbol
        reasons = [
            f"{candidate.symbol} ranking score is {candidate.ranking_score:.2f}.",
            f"{candidate.symbol} response action is {candidate.response_action}.",
        ]
        risks = [
            f"Focus will move away from {current_symbol}.",
            "Operator should confirm that the current pair no longer has better execution context.",
        ]
        severity = "warning" if candidate.response_action != "warning_only" else "info"
        return PairReplacementReviewSnapshot(
            review_id=self._pending_replacement.review_id if self._pending_replacement else str(uuid4()),
            current_symbol=current_symbol,
            proposed_symbol=candidate.symbol,
            severity=severity,
            summary=f"Review replacement from {current_symbol} to {candidate.symbol}.",
            reasons_to_switch=reasons,
            risks=risks,
            approval_required=True,
            blocks_apply=candidate.response_action == "block_signal",
        )

    def _write_and_publish(self, event_type: str, payload: dict[str, object]) -> None:
        self.audit_writer.write(event_type, payload)
        self.event_bus.publish("session.updated", {"event_type": event_type, **payload})
