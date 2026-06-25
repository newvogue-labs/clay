from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.db.models_demo import DemoTradeRecord
from clay.db.repositories_demo import DemoRepository
from clay.db.repositories_review import ReviewRepository
from clay.events.bus import EventBus
from clay.session_review.models import (
    AIReviewCardSnapshot,
    FeedbackCreateCommand,
    FeedbackItemSnapshot,
    NormalizedAuditEventSnapshot,
    ReviewedTradeRecord,
    SessionReviewFilterOptions,
    SessionReviewFilterState,
    SessionReviewSnapshot,
    SessionReviewSummary,
)


class SessionReviewService:
    def __init__(
        self,
        *,
        audit_writer: AuditWriter,
        event_bus: EventBus,
        ai_control_service: AIControlService,
    ) -> None:
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self.ai_control_service = ai_control_service

    def build_snapshot(
        self,
        session: Session,
        *,
        pair: str | None = None,
        strategy: str | None = None,
        model_version: str | None = None,
        confidence_band: str | None = None,
    ) -> SessionReviewSnapshot:
        demo_repository = DemoRepository(session)
        review_repository = ReviewRepository(session)
        records = demo_repository.list_all_trade_records()
        reviewed_records = [self._decorate_record(record) for record in records]
        filtered_records = [
            record
            for record in reviewed_records
            if self._matches_filters(
                record,
                pair=pair,
                strategy=strategy,
                model_version=model_version,
                confidence_band=confidence_band,
            )
        ]
        feedback_items = review_repository.list_feedback(
            symbol=pair,
            strategy_mode=strategy,
            model_version=model_version,
            confidence_band=confidence_band,
            limit=20,
        )
        feedback_snapshots = [self._serialize_feedback(item) for item in feedback_items]
        audit_events = self._read_audit_events(limit=20)

        return SessionReviewSnapshot(
            summary=self._build_summary(filtered_records, feedback_snapshots),
            filters=SessionReviewFilterState(
                pair=pair,
                strategy=strategy,
                model_version=model_version,
                confidence_band=confidence_band,
            ),
            filter_options=self._build_filter_options(
                reviewed_records, feedback_snapshots
            ),
            records=filtered_records[:20],
            feedback=feedback_snapshots,
            audit=audit_events,
            ai_review_cards=self._build_ai_review_cards(
                filtered_records,
                feedback_snapshots,
                audit_events,
            ),
        )

    def capture_feedback(
        self,
        session: Session,
        command: FeedbackCreateCommand,
    ) -> SessionReviewSnapshot:
        demo_repository = DemoRepository(session)
        review_repository = ReviewRepository(session)
        record = demo_repository.get_trade_record(command.record_id)
        if record is None:
            raise ValueError("demo trade record not found")

        decorated = self._decorate_record(record)
        score_map = {"useful": 1.0, "noise": -1.0, "needs_follow_up": 0.0}
        feedback = review_repository.create_feedback(
            {
                "session_id": record.session_id,
                "signal_id": record.signal_id,
                "symbol": record.symbol,
                "strategy_mode": decorated.strategy_mode,
                "model_version": decorated.model_version,
                "confidence_band": decorated.confidence_band,
                "outcome_status": record.outcome_status,
                "feedback_label": command.feedback_label,
                "notes": command.notes,
                "created_at": datetime.now(UTC),  # not on replay exec path; wall-clock intentional
                "score": score_map[command.feedback_label],
            }
        )
        session.commit()
        self.audit_writer.write(
            "review.feedback.captured",
            {
                "feedback_id": feedback.id,
                "record_id": command.record_id,
                "signal_id": record.signal_id,
                "symbol": record.symbol,
                "feedback_label": command.feedback_label,
            },
        )
        self.event_bus.publish(
            "review.updated",
            {
                "event_type": "review.feedback.captured",
                "feedback_id": feedback.id,
                "record_id": command.record_id,
                "signal_id": record.signal_id,
                "symbol": record.symbol,
                "feedback_label": command.feedback_label,
            },
        )
        return self.build_snapshot(session)

    def _decorate_record(self, record: DemoTradeRecord) -> ReviewedTradeRecord:
        strategy_mode = (
            "defensive"
            if record.operator_action in {"skipped", "off_signal"}
            else "momentum"
        )
        model_version = self.ai_control_service.assignments.get(
            "chief-agent", "unknown"
        )
        confidence_band = self._confidence_band(record)
        return ReviewedTradeRecord(
            record_id=record.id,
            session_id=record.session_id,
            signal_id=record.signal_id,
            symbol=record.symbol,
            strategy_mode=strategy_mode,
            model_version=model_version,
            confidence_band=confidence_band,
            operator_action=record.operator_action,
            outcome_status=record.outcome_status,
            pnl_pct=record.pnl_pct,
            recorded_at=record.recorded_at.isoformat(),
            observed_at=record.observed_at.isoformat() if record.observed_at else None,
        )

    def _confidence_band(self, record: DemoTradeRecord) -> str:
        if record.operator_action == "off_signal":
            return "low"
        if record.operator_action == "entered_late":
            return "medium"
        return "high"

    def _matches_filters(
        self,
        record: ReviewedTradeRecord,
        *,
        pair: str | None,
        strategy: str | None,
        model_version: str | None,
        confidence_band: str | None,
    ) -> bool:
        if pair and record.symbol != pair:
            return False
        if strategy and record.strategy_mode != strategy:
            return False
        if model_version and record.model_version != model_version:
            return False
        if confidence_band and record.confidence_band != confidence_band:
            return False
        return True

    def _build_summary(
        self,
        records: list[ReviewedTradeRecord],
        feedback: list[FeedbackItemSnapshot],
    ) -> SessionReviewSummary:
        resolved = [
            record for record in records if record.outcome_status != "unresolved"
        ]
        cumulative_pnl_pct = round(
            sum(record.pnl_pct or 0.0 for record in records),
            2,
        )
        if not records:
            status = "collecting"
            operator_message = "No reviewable session data yet."
        elif any(record.outcome_status == "mismatched" for record in records):
            status = "needs_operator_attention"
            operator_message = "Mismatched demo outcomes need operator review before trusting the evidence."
        elif any(record.outcome_status == "unresolved" for record in records):
            status = "waiting_for_resolution"
            operator_message = "Some demo outcomes are still unresolved."
        else:
            status = "review_ready"
            operator_message = (
                "Session evidence is coherent enough for post-session review."
            )

        return SessionReviewSummary(
            review_status=status,
            total_demo_records=len(records),
            resolved_demo_records=len(resolved),
            cumulative_pnl_pct=cumulative_pnl_pct,
            feedback_count=len(feedback),
            last_reviewed_at=feedback[0].created_at if feedback else None,
            operator_message=operator_message,
        )

    def _build_filter_options(
        self,
        records: list[ReviewedTradeRecord],
        feedback: list[FeedbackItemSnapshot],
    ) -> SessionReviewFilterOptions:
        pairs = sorted({record.symbol for record in records})
        strategies = sorted({record.strategy_mode for record in records})
        model_versions = sorted(
            {record.model_version for record in records if record.model_version}
            | {item.model_version for item in feedback if item.model_version}
        )
        confidence_bands = sorted({record.confidence_band for record in records})
        return SessionReviewFilterOptions(
            pairs=pairs,
            strategies=strategies,
            model_versions=model_versions,
            confidence_bands=confidence_bands,
        )

    def _serialize_feedback(self, item) -> FeedbackItemSnapshot:
        return FeedbackItemSnapshot(
            feedback_id=item.id,
            session_id=item.session_id,
            signal_id=item.signal_id,
            symbol=item.symbol,
            strategy_mode=item.strategy_mode,
            model_version=item.model_version,
            confidence_band=item.confidence_band,
            outcome_status=item.outcome_status,
            feedback_label=item.feedback_label,
            notes=item.notes,
            created_at=item.created_at.isoformat(),
            score=item.score,
        )

    def _read_audit_events(self, *, limit: int) -> list[NormalizedAuditEventSnapshot]:
        events_raw = self.audit_writer.read_recent(limit=limit)
        return [self._normalize_audit_event(payload) for payload in events_raw]

    def _normalize_audit_event(
        self, payload: dict[str, object]
    ) -> NormalizedAuditEventSnapshot:
        event_type = str(payload.get("event_type", "unknown"))
        event_payload = payload.get("payload", {})
        if not isinstance(event_payload, dict):
            event_payload = {}
        module = event_type.split(".", 1)[0] if "." in event_type else "system"
        object_id = (
            event_payload.get("session_id")
            or event_payload.get("signal_id")
            or event_payload.get("record_id")
            or event_payload.get("review_id")
        )
        severity = "info"
        if "mismatch" in event_type or "error" in event_type:
            severity = "warning"
        if "runtime.degraded" in event_type:
            severity = "critical"

        return NormalizedAuditEventSnapshot(
            timestamp=str(payload.get("timestamp")),
            actor="operator",
            module=module,
            event_type=event_type,
            object_id=str(object_id) if object_id is not None else None,
            explanation=self._build_explanation(event_type, event_payload),
            severity=severity,
        )

    def _build_explanation(self, event_type: str, payload: dict[str, object]) -> str:
        if event_type == "demo.trade.logged":
            return (
                f"Logged demo trade intent for {payload.get('symbol', 'unknown pair')}."
            )
        if event_type == "demo.result.ingested":
            return f"Ingested demo result for {payload.get('symbol', 'unknown pair')}."
        if event_type == "review.feedback.captured":
            return f"Captured feedback {payload.get('feedback_label', 'unknown')} for {payload.get('symbol', 'unknown pair')}."
        if event_type.startswith("session."):
            return f"Session event {event_type} recorded."
        if event_type.startswith("ai."):
            return "AI orchestration state changed and may affect review confidence."
        return f"Audit event {event_type} recorded."

    def _build_ai_review_cards(
        self,
        records: list[ReviewedTradeRecord],
        feedback: list[FeedbackItemSnapshot],
        audit_events: list[NormalizedAuditEventSnapshot],
    ) -> list[AIReviewCardSnapshot]:
        cards: list[AIReviewCardSnapshot] = []
        if any(record.outcome_status == "mismatched" for record in records):
            cards.append(
                AIReviewCardSnapshot(
                    card_id="mismatch-discipline",
                    severity="warning",
                    title="Operator discipline drift detected",
                    summary="At least one demo result was linked to an off-signal execution.",
                    recommendations=[
                        "Review why the operator deviated from the focused signal.",
                        "Do not promote strategy changes from this review without explicit confirmation.",
                    ],
                    confirmation_required_for_changes=True,
                )
            )
        if any(item.feedback_label == "needs_follow_up" for item in feedback):
            cards.append(
                AIReviewCardSnapshot(
                    card_id="follow-up-needed",
                    severity="info",
                    title="Follow-up review suggested",
                    summary="Captured feedback indicates unresolved operator questions.",
                    recommendations=[
                        "Inspect linked signal reasoning before the next demo session.",
                        "Keep strategy/model changes in review-only mode.",
                    ],
                    confirmation_required_for_changes=True,
                )
            )
        if not cards:
            cards.append(
                AIReviewCardSnapshot(
                    card_id="stable-review",
                    severity="info",
                    title="Review loop is stable",
                    summary="No critical review blockers detected in the current slice.",
                    recommendations=[
                        "Keep collecting demo evidence and feedback.",
                        "Any strategy change still requires operator confirmation.",
                    ],
                    confirmation_required_for_changes=True,
                )
            )
        if audit_events and all(event.severity == "info" for event in audit_events[:5]):
            cards.append(
                AIReviewCardSnapshot(
                    card_id="clean-audit-window",
                    severity="info",
                    title="Audit window looks clean",
                    summary="Recent audit activity shows no critical runtime anomalies.",
                    recommendations=[
                        "Use this window to compare feedback against demo outcomes.",
                    ],
                    confirmation_required_for_changes=False,
                )
            )
        return cards
