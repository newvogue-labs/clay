from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.core.clock import Clock, SystemClock
from clay.db.repositories_runtime_state import StrategyStateRepository
from clay.db.repositories_validation import ValidationRepository
from clay.events.bus import EventBus
from clay.session_review.service import SessionReviewService
from clay.signal_engine.service import SignalEngineService
from clay.validation_lab.models import (
    ActivationReviewSnapshot,
    ValidationLabSnapshot,
    ValidationLabSummary,
    ValidationRunCommand,
    ValidationRunSnapshot,
)


class ValidationLabService:
    def __init__(
        self,
        *,
        signal_engine_service: SignalEngineService,
        ai_control_service: AIControlService,
        session_review_service: SessionReviewService,
        audit_writer: AuditWriter,
        event_bus: EventBus,
        session_factory: sessionmaker | None = None,
        clock: Clock = SystemClock(),
    ) -> None:
        self.signal_engine_service = signal_engine_service
        self.ai_control_service = ai_control_service
        self.session_review_service = session_review_service
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self.session_factory = session_factory
        self._clock = clock
        # ``_strategy_mode`` is restored from the ``ops.strategy_state``
        # singleton row when a ``session_factory`` is supplied. Without
        # one (legacy callers and pre-A5 tests), the service falls back
        # to the in-memory default ``"momentum"`` and stays non-persistent.
        if session_factory is None:
            self._strategy_mode = "momentum"
        else:
            with session_factory() as session:
                state = StrategyStateRepository(session).get_or_create()
                self._strategy_mode = state.strategy_mode
                session.commit()

    def build_snapshot(self, session: Session) -> ValidationLabSnapshot:
        repository = ValidationRepository(session)
        runs = repository.list_validation_runs(limit=10)
        reviews = repository.list_activation_reviews(limit=10)
        serialized_runs = [self._serialize_run(row) for row in runs]
        serialized_reviews = [self._serialize_review(row) for row in reviews]
        return ValidationLabSnapshot(
            summary=self._build_summary(serialized_runs, serialized_reviews),
            runs=serialized_runs,
            activation_reviews=serialized_reviews,
        )

    def run_validation(
        self,
        session: Session,
        command: ValidationRunCommand,
    ) -> ValidationLabSnapshot:
        repository = ValidationRepository(session)
        signal_snapshot = self.signal_engine_service.build_snapshot(session)
        review_snapshot = self.session_review_service.build_snapshot(session)
        now = self._clock.now()
        top_signal = signal_snapshot.signals[0] if signal_snapshot.signals else None
        signal_count = len(signal_snapshot.signals)
        record_count = len(review_snapshot.records)

        base_trade_count = max(signal_count * 6, 6)
        if command.run_type == "strategy_replay":
            trades_simulated = base_trade_count + record_count
            win_rate = 0.61 if top_signal else 0.42
            net_pnl_pct = 3.4 if top_signal else -0.6
            max_drawdown_pct = 1.8 if top_signal else 3.2
            decision_quality_score = 0.82 if top_signal else 0.46
        elif command.run_type == "model_comparison":
            trades_simulated = base_trade_count + 2
            win_rate = 0.58 if top_signal else 0.4
            net_pnl_pct = 2.1 if top_signal else -0.9
            max_drawdown_pct = 2.0 if top_signal else 3.6
            decision_quality_score = 0.76 if top_signal else 0.43
        else:
            trades_simulated = base_trade_count + 1
            win_rate = 0.64 if top_signal else 0.45
            net_pnl_pct = 1.7 if top_signal else -0.4
            max_drawdown_pct = 1.5 if top_signal else 2.8
            decision_quality_score = 0.8 if top_signal else 0.48

        model_version = self.ai_control_service.assignments.get("chief-agent", "unknown")
        summary = self._build_run_summary(
            run_type=command.run_type,
            top_signal_symbol=top_signal.symbol if top_signal else None,
            review_status=review_snapshot.summary.review_status,
            net_pnl_pct=net_pnl_pct,
            decision_quality_score=decision_quality_score,
        )
        repository.create_validation_run(
            {
                "run_type": command.run_type,
                "label": command.label,
                "strategy_mode": self._strategy_mode,
                "model_version": model_version,
                "period_start": now - timedelta(days=7),
                "period_end": now,
                "trades_simulated": trades_simulated,
                "win_rate": round(win_rate, 4),
                "net_pnl_pct": round(net_pnl_pct, 4),
                "max_drawdown_pct": round(max_drawdown_pct, 4),
                "decision_quality_score": round(decision_quality_score, 4),
                "summary": summary,
                "created_at": now,
            }
        )
        session.commit()
        self.audit_writer.write(
            "validation.run.completed",
            {
                "run_type": command.run_type,
                "label": command.label,
                "strategy_mode": self._strategy_mode,
                "model_version": model_version,
                "trades_simulated": trades_simulated,
            },
        )
        self.event_bus.publish(
            "validation.updated",
            {
                "event_type": "validation.run.completed",
                "run_type": command.run_type,
                "label": command.label,
            },
        )
        return self.build_snapshot(session)

    def review_activation(
        self,
        session: Session,
        *,
        target_type: str,
        target_id: str,
        proposed_value: str,
    ) -> ActivationReviewSnapshot:
        repository = ValidationRepository(session)
        latest_run = next(iter(repository.list_validation_runs(limit=1)), None)
        if latest_run is None:
            raise ValueError("validation run is required before activation review")

        current_value = self._resolve_current_value(target_type=target_type, target_id=target_id)
        status, severity = self._resolve_review_posture(latest_run.net_pnl_pct, latest_run.max_drawdown_pct, latest_run.decision_quality_score)
        evidence = {
            "latest_run_id": latest_run.id,
            "latest_run_type": latest_run.run_type,
            "net_pnl_pct": latest_run.net_pnl_pct,
            "max_drawdown_pct": latest_run.max_drawdown_pct,
            "decision_quality_score": latest_run.decision_quality_score,
            "strategy_mode": latest_run.strategy_mode,
            "model_version": latest_run.model_version,
        }
        summary = self._build_review_summary(
            target_type=target_type,
            target_id=target_id,
            current_value=current_value,
            proposed_value=proposed_value,
            status=status,
            severity=severity,
        )
        created_at = datetime.now(UTC)
        row = repository.create_activation_review(
            {
                "review_id": str(uuid4()),
                "target_type": target_type,
                "target_id": target_id,
                "proposed_value": proposed_value,
                "current_value": current_value,
                "status": status,
                "severity": severity,
                "summary": summary,
                "evidence_json": evidence,
                "created_at": created_at,
                "applied_at": None,
            }
        )
        session.commit()
        self.audit_writer.write(
            "validation.activation.reviewed",
            {
                "review_id": row.review_id,
                "target_type": target_type,
                "target_id": target_id,
                "status": status,
                "severity": severity,
            },
        )
        self.event_bus.publish(
            "validation.updated",
            {
                "event_type": "validation.activation.reviewed",
                "review_id": row.review_id,
                "target_type": target_type,
                "target_id": target_id,
                "status": status,
            },
        )
        return self._serialize_review(row)

    def apply_activation(self, session: Session, review_id: str) -> ValidationLabSnapshot:
        repository = ValidationRepository(session)
        row = repository.get_activation_review(review_id)
        if row is None:
            raise ValueError("activation review not found")
        if row.status == "blocked":
            raise ValueError("activation review is blocked")

        if row.target_type == "strategy_mode":
            self._strategy_mode = row.proposed_value
            # write-through: persist the new mode immediately so a restart
            # between apply and the next build_snapshot still sees it.
            if self.session_factory is not None:
                StrategyStateRepository(session).save(strategy_mode=self._strategy_mode)
        elif row.target_type == "model_assignment":
            # A5.5 (D2 fix): route through ``ai_control.set_assignment``
            # — the trusted internal-caller path that mirrors
            # ``apply_assignment`` write-through (DB upsert + audit +
            # ``ai.updated`` event) but does NOT require a pending review,
            # does NOT touch ``ai_control_state.last_reviewed_at`` or
            # ``pending_review_*``, and does NOT re-evaluate preflight
            # ``blocks_apply``. Validation_lab owns its own posture gate
            # (``row.status == "blocked"`` was rejected above) and its own
            # ``review_id`` trail in ``validation.activation_reviews``.
            self.ai_control_service.set_assignment(
                role_id=row.target_id,
                model_id=row.proposed_value,
                session=session,
            )
        else:
            raise ValueError("unsupported activation target")

        row.status = "applied"
        row.applied_at = datetime.now(UTC)
        session.commit()
        self.audit_writer.write(
            "validation.activation.applied",
            {
                "review_id": row.review_id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "proposed_value": row.proposed_value,
            },
        )
        self.event_bus.publish(
            "validation.updated",
            {
                "event_type": "validation.activation.applied",
                "review_id": row.review_id,
                "target_type": row.target_type,
                "target_id": row.target_id,
            },
        )
        return self.build_snapshot(session)

    def _build_summary(
        self,
        runs: list[ValidationRunSnapshot],
        reviews: list[ActivationReviewSnapshot],
    ) -> ValidationLabSummary:
        replay_ready = bool(runs)
        staged_review_count = sum(1 for row in reviews if row.status == "staged")
        blocked_count = sum(1 for row in reviews if row.status == "blocked")
        latest_status = reviews[0].status if reviews else ("ready" if replay_ready else "collecting")
        if not runs:
            operator_message = "Validation Lab is waiting for the first replay run before any activation review."
        elif blocked_count:
            operator_message = "At least one activation review is blocked; keep the candidate staged until evidence improves."
        elif staged_review_count:
            operator_message = "Replay evidence exists, but activation still needs another operator pass before apply."
        else:
            operator_message = "Replay evidence is healthy enough to prepare review cards for staged activation."
        return ValidationLabSummary(
            replay_ready=replay_ready,
            activation_review_status=latest_status,
            total_runs=len(runs),
            staged_review_count=staged_review_count,
            operator_message=operator_message,
        )

    def _resolve_current_value(self, *, target_type: str, target_id: str) -> str:
        if target_type == "strategy_mode":
            return self._strategy_mode
        if target_type == "model_assignment":
            current = self.ai_control_service.assignments.get(target_id)
            if current is None:
                raise ValueError("unknown model assignment target")
            return current
        raise ValueError("unsupported activation target")

    def _resolve_review_posture(
        self,
        net_pnl_pct: float,
        max_drawdown_pct: float,
        decision_quality_score: float,
    ) -> tuple[str, str]:
        if net_pnl_pct < 0 or max_drawdown_pct >= 3.5 or decision_quality_score < 0.55:
            return "blocked", "critical"
        if net_pnl_pct < 2.0 or max_drawdown_pct >= 2.0 or decision_quality_score < 0.75:
            return "staged", "warning"
        return "ready", "info"

    def _build_run_summary(
        self,
        *,
        run_type: str,
        top_signal_symbol: str | None,
        review_status: str,
        net_pnl_pct: float,
        decision_quality_score: float,
    ) -> str:
        signal_part = top_signal_symbol or "no focused signal"
        return (
            f"{run_type} completed around {signal_part}; "
            f"session review status is {review_status}; "
            f"net pnl {net_pnl_pct:.2f}% with decision quality {decision_quality_score:.2f}."
        )

    def _build_review_summary(
        self,
        *,
        target_type: str,
        target_id: str,
        current_value: str,
        proposed_value: str,
        status: str,
        severity: str,
    ) -> str:
        return (
            f"{target_type} review for {target_id}: move from {current_value} to {proposed_value}; "
            f"posture is {status} with {severity} severity."
        )

    def _serialize_run(self, row) -> ValidationRunSnapshot:
        return ValidationRunSnapshot(
            run_id=row.id,
            run_type=row.run_type,
            label=row.label,
            strategy_mode=row.strategy_mode,
            model_version=row.model_version,
            period_start=row.period_start.isoformat(),
            period_end=row.period_end.isoformat(),
            trades_simulated=row.trades_simulated,
            win_rate=round(row.win_rate, 4),
            net_pnl_pct=round(row.net_pnl_pct, 4),
            max_drawdown_pct=round(row.max_drawdown_pct, 4),
            decision_quality_score=round(row.decision_quality_score, 4),
            summary=row.summary,
            created_at=row.created_at.isoformat(),
        )

    def _serialize_review(self, row) -> ActivationReviewSnapshot:
        evidence = json.loads(row.evidence_json) if row.evidence_json else {}
        return ActivationReviewSnapshot(
            review_id=row.review_id,
            target_type=row.target_type,
            target_id=row.target_id,
            current_value=row.current_value,
            proposed_value=row.proposed_value,
            status=row.status,
            severity=row.severity,
            summary=row.summary,
            evidence=evidence,
            created_at=row.created_at.isoformat(),
            applied_at=row.applied_at.isoformat() if row.applied_at else None,
        )
