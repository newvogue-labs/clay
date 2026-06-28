from __future__ import annotations

from sqlalchemy.orm import Session

from clay.alpha.models import (
    AlphaGateStatus,
    AlphaOperatorStepSnapshot,
    AlphaReadinessEvidence,
    AlphaReadinessGateSnapshot,
    AlphaReadinessSnapshot,
    AlphaReadinessSummary,
)
from clay.demo_trading.models import DemoTradingSnapshot
from clay.demo_trading.service import DemoTradingService
from clay.reliability.models import ReliabilitySnapshot
from clay.reliability.service import ReliabilityService
from clay.session_control.models import SessionControlSnapshot
from clay.session_control.service import SessionControlService
from clay.session_review.models import SessionReviewSnapshot
from clay.session_review.service import SessionReviewService
from clay.validation_lab.models import ValidationLabSnapshot
from clay.validation_lab.service import ValidationLabService
from clay.workspace.models import WorkspaceSnapshot
from clay.workspace.service import WorkspaceService


class AlphaReadinessService:
    def __init__(
        self,
        *,
        workspace_service: WorkspaceService,
        session_control_service: SessionControlService,
        demo_trading_service: DemoTradingService,
        session_review_service: SessionReviewService,
        validation_lab_service: ValidationLabService,
        reliability_service: ReliabilityService,
    ) -> None:
        self.workspace_service = workspace_service
        self.session_control_service = session_control_service
        self.demo_trading_service = demo_trading_service
        self.session_review_service = session_review_service
        self.validation_lab_service = validation_lab_service
        self.reliability_service = reliability_service

    def build_snapshot(self, session: Session) -> AlphaReadinessSnapshot:
        workspace_snapshot = self.workspace_service.build_snapshot(session)
        session_snapshot = self.session_control_service.build_snapshot(session)
        demo_snapshot = self.demo_trading_service.build_snapshot(session)
        review_snapshot = self.session_review_service.build_snapshot(session)
        validation_snapshot = self.validation_lab_service.build_snapshot(session)
        reliability_snapshot = self.reliability_service.build_snapshot(session)

        gates = self._build_gates(
            workspace_snapshot=workspace_snapshot,
            session_snapshot=session_snapshot,
            demo_snapshot=demo_snapshot,
            review_snapshot=review_snapshot,
            validation_snapshot=validation_snapshot,
            reliability_snapshot=reliability_snapshot,
        )
        operator_steps = self._build_operator_steps(
            workspace_snapshot=workspace_snapshot,
            session_snapshot=session_snapshot,
            demo_snapshot=demo_snapshot,
            review_snapshot=review_snapshot,
            validation_snapshot=validation_snapshot,
            reliability_snapshot=reliability_snapshot,
        )

        return AlphaReadinessSnapshot(
            summary=self._build_summary(gates, operator_steps),
            gates=gates,
            operator_steps=operator_steps,
            evidence=AlphaReadinessEvidence(
                runtime_state=workspace_snapshot.workspace_state.runtime_state,
                preflight_status=session_snapshot.preflight.status,
                workspace_posture=workspace_snapshot.workspace_state.workspace_posture,
                focus_symbol=workspace_snapshot.focus_pair.symbol,
                focused_signal_state=workspace_snapshot.workspace_state.focused_signal_state,
                session_lifecycle_state=session_snapshot.lifecycle.lifecycle_state,
                demo_readiness_status=demo_snapshot.readiness.status,
                demo_record_count=demo_snapshot.readiness.total_records,
                review_status=review_snapshot.summary.review_status,
                validation_replay_ready=validation_snapshot.summary.replay_ready,
                validation_run_count=validation_snapshot.summary.total_runs,
                release_readiness_status=reliability_snapshot.summary.release_readiness_status,
            ),
        )

    def _build_gates(
        self,
        *,
        workspace_snapshot: WorkspaceSnapshot,
        session_snapshot: SessionControlSnapshot,
        demo_snapshot: DemoTradingSnapshot,
        review_snapshot: SessionReviewSnapshot,
        validation_snapshot: ValidationLabSnapshot,
        reliability_snapshot: ReliabilitySnapshot,
    ) -> list[AlphaReadinessGateSnapshot]:
        preflight_passed = session_snapshot.preflight.status == "pass"
        focused_signal_ready = (
            workspace_snapshot.focus_pair.active_signal_id is not None
            and workspace_snapshot.workspace_state.focused_signal_state
            in {"active", "weakening"}
            and workspace_snapshot.workspace_state.can_log_decision
        )
        session_lifecycle_status: AlphaGateStatus = "pass"
        session_lifecycle_detail = (
            "Session lifecycle has already reached an operator path state."
        )
        if session_snapshot.lifecycle.lifecycle_state in {"idle", "pre_session"}:
            session_lifecycle_status = "warn"
            session_lifecycle_detail = (
                "Session can be started from Session Control."
                if session_snapshot.lifecycle.can_start
                else "Session cannot start until blocking preflight or focus conditions clear."
            )

        reliability_status: AlphaGateStatus = "pass"
        if reliability_snapshot.summary.release_readiness_status == "blocked":
            reliability_status = "fail"
        elif reliability_snapshot.summary.last_rechecked_at is None:
            reliability_status = "warn"

        return [
            AlphaReadinessGateSnapshot(
                gate_id="preflight-ready",
                label="Preflight ready",
                status="pass" if preflight_passed else "fail",
                blocks_alpha=not preflight_passed,
                detail=(
                    "Session preflight passes."
                    if preflight_passed
                    else session_snapshot.preflight.blocking_reason
                    or "Session preflight is blocked."
                ),
            ),
            AlphaReadinessGateSnapshot(
                gate_id="focused-signal",
                label="Focused signal",
                status="pass" if focused_signal_ready else "fail",
                blocks_alpha=not focused_signal_ready,
                detail=(
                    f"{workspace_snapshot.focus_pair.symbol} is actionable for demo logging."
                    if focused_signal_ready
                    else workspace_snapshot.workspace_state.blocking_reason
                    or "No actionable focused signal is available."
                ),
            ),
            AlphaReadinessGateSnapshot(
                gate_id="session-lifecycle",
                label="Session lifecycle",
                status=session_lifecycle_status,
                blocks_alpha=False,
                detail=session_lifecycle_detail,
            ),
            AlphaReadinessGateSnapshot(
                gate_id="demo-evidence",
                label="Demo evidence",
                status="pass"
                if demo_snapshot.readiness.status == "ready_for_review"
                else "warn",
                blocks_alpha=False,
                detail=demo_snapshot.readiness.operator_message,
            ),
            AlphaReadinessGateSnapshot(
                gate_id="review-loop",
                label="Review loop",
                status=(
                    "pass"
                    if review_snapshot.summary.resolved_demo_records > 0
                    and review_snapshot.summary.review_status != "collecting"
                    else "warn"
                ),
                blocks_alpha=False,
                detail=review_snapshot.summary.operator_message,
            ),
            AlphaReadinessGateSnapshot(
                gate_id="validation-replay",
                label="Validation replay",
                status="pass" if validation_snapshot.summary.replay_ready else "warn",
                blocks_alpha=False,
                detail=validation_snapshot.summary.operator_message,
            ),
            AlphaReadinessGateSnapshot(
                gate_id="reliability-posture",
                label="Reliability posture",
                status=reliability_status,
                blocks_alpha=reliability_status == "fail",
                detail=reliability_snapshot.summary.operator_message,
            ),
        ]

    def _build_operator_steps(
        self,
        *,
        workspace_snapshot: WorkspaceSnapshot,
        session_snapshot: SessionControlSnapshot,
        demo_snapshot: DemoTradingSnapshot,
        review_snapshot: SessionReviewSnapshot,
        validation_snapshot: ValidationLabSnapshot,
        reliability_snapshot: ReliabilitySnapshot,
    ) -> list[AlphaOperatorStepSnapshot]:
        session_is_active = session_snapshot.lifecycle.lifecycle_state in {
            "active_session",
            "paused",
            "review",
        }
        start_step_status: AlphaGateStatus = "pass" if session_is_active else "warn"
        if not session_is_active and not session_snapshot.lifecycle.can_start:
            start_step_status = "fail"

        demo_log_status: AlphaGateStatus = "warn"
        if demo_snapshot.readiness.total_records > 0:
            demo_log_status = "pass"
        elif demo_snapshot.active_session.can_log_decision:
            demo_log_status = "warn"
        elif (
            session_snapshot.lifecycle.lifecycle_state == "idle"
            and not session_snapshot.lifecycle.can_start
        ):
            demo_log_status = "fail"

        reliability_step_status: AlphaGateStatus = "pass"
        if reliability_snapshot.summary.release_readiness_status == "blocked":
            reliability_step_status = "fail"
        elif reliability_snapshot.summary.last_rechecked_at is None:
            reliability_step_status = "warn"

        steps = [
            AlphaOperatorStepSnapshot(
                step_id="check_preflight",
                label="Check preflight",
                status="pass"
                if session_snapshot.preflight.status == "pass"
                else "fail",
                detail=(
                    "Preflight is clear."
                    if session_snapshot.preflight.status == "pass"
                    else session_snapshot.preflight.blocking_reason
                    or "Preflight is blocked."
                ),
                target_screen="session-control",
                action_label="Review preflight",
                is_next=False,
            ),
            AlphaOperatorStepSnapshot(
                step_id="focus_signal",
                label="Focus signal",
                status=(
                    "pass"
                    if workspace_snapshot.focus_pair.active_signal_id is not None
                    and workspace_snapshot.workspace_state.focused_signal_state
                    in {"active", "weakening"}
                    else "fail"
                ),
                detail=(
                    f"Focused on {workspace_snapshot.focus_pair.symbol}."
                    if workspace_snapshot.focus_pair.active_signal_id is not None
                    else "No focused signal is available."
                ),
                target_screen="workspace",
                action_label="Open workspace",
                is_next=False,
            ),
            AlphaOperatorStepSnapshot(
                step_id="start_or_resume_session",
                label="Start or resume session",
                status=start_step_status,
                detail=(
                    f"Lifecycle is {session_snapshot.lifecycle.lifecycle_state}."
                    if session_is_active
                    else "Session is ready to start."
                    if session_snapshot.lifecycle.can_start
                    else session_snapshot.preflight.blocking_reason
                    or "Session start is blocked."
                ),
                target_screen="session-control",
                action_label="Start session",
                is_next=False,
            ),
            AlphaOperatorStepSnapshot(
                step_id="log_demo_decision",
                label="Log demo decision",
                status=demo_log_status,
                detail=(
                    "Demo decision logging is available or already evidenced."
                    if demo_log_status == "pass"
                    else "Demo decision logging is available; log the current operator decision."
                    if demo_snapshot.active_session.can_log_decision
                    else demo_snapshot.active_session.blocking_reason
                    or "Demo decision logging is waiting on an active session."
                ),
                target_screen="demo-validation",
                action_label="Log demo decision",
                is_next=False,
            ),
            AlphaOperatorStepSnapshot(
                step_id="resolve_demo_result",
                label="Resolve demo result",
                status="pass"
                if demo_snapshot.readiness.resolved_record_count > 0
                else "warn",
                detail=f"{demo_snapshot.readiness.resolved_record_count} demo records are resolved.",
                target_screen="demo-validation",
                action_label="Resolve demo result",
                is_next=False,
            ),
            AlphaOperatorStepSnapshot(
                step_id="review_feedback",
                label="Review feedback",
                status="pass" if review_snapshot.summary.feedback_count > 0 else "warn",
                detail=f"{review_snapshot.summary.feedback_count} review feedback items are captured.",
                target_screen="session-review",
                action_label="Capture review feedback",
                is_next=False,
            ),
            AlphaOperatorStepSnapshot(
                step_id="run_validation_replay",
                label="Run validation replay",
                status="pass" if validation_snapshot.summary.replay_ready else "warn",
                detail=validation_snapshot.summary.operator_message,
                target_screen="validation-lab",
                action_label="Run validation replay",
                is_next=False,
            ),
            AlphaOperatorStepSnapshot(
                step_id="recheck_reliability",
                label="Recheck reliability",
                status=reliability_step_status,
                detail=reliability_snapshot.summary.operator_message,
                target_screen="reliability",
                action_label="Recheck reliability",
                is_next=False,
            ),
        ]
        return self._mark_next_operator_step(steps)

    def _mark_next_operator_step(
        self,
        steps: list[AlphaOperatorStepSnapshot],
    ) -> list[AlphaOperatorStepSnapshot]:
        next_step = next((step for step in steps if step.status != "pass"), None)
        if next_step is None:
            return steps
        return [
            step.model_copy(update={"is_next": step.step_id == next_step.step_id})
            for step in steps
        ]

    def _build_summary(
        self,
        gates: list[AlphaReadinessGateSnapshot],
        operator_steps: list[AlphaOperatorStepSnapshot],
    ) -> AlphaReadinessSummary:
        blocking_gates = [
            gate for gate in gates if gate.status == "fail" and gate.blocks_alpha
        ]
        warning_gates = [gate for gate in gates if gate.status == "warn"]
        next_step = next((step for step in operator_steps if step.is_next), None)
        operator_path_ready = not blocking_gates
        if blocking_gates:
            readiness_status = "blocked"
            next_action = blocking_gates[0].detail
        elif next_step is None:
            readiness_status = "operator_path_ready"
            next_action = (
                "Alpha operator path is ready for a disciplined end-to-end run."
            )
        elif warning_gates:
            readiness_status = "needs_attention"
            next_action = warning_gates[0].detail
        else:
            readiness_status = "operator_path_ready"
            next_action = (
                "Alpha operator path is ready for a disciplined end-to-end run."
            )

        return AlphaReadinessSummary(
            readiness_status=readiness_status,
            operator_path_ready=operator_path_ready,
            blocking_gate_count=len(blocking_gates),
            warning_gate_count=len(warning_gates),
            next_action=next_action,
        )
