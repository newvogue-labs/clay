from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from clay.ai_control.service import AIControlService
from clay.audit.writer import AuditWriter
from clay.core.clock import Clock, SystemClock
from clay.control_center.models import ControlCenterSnapshot
from clay.control_center.service import ControlCenterService
from clay.demo_trading.models import DemoTradingSnapshot
from clay.demo_trading.service import DemoTradingService
from clay.events.bus import EventBus
from clay.db.repositories_runtime_state import ReliabilityStateRepository
from clay.reliability.models import (
    DegradedTriggerSnapshot,
    LocalFallbackReadinessSnapshot,
    ReliabilityCheckSnapshot,
    ReliabilityCheckStatus,
    ReliabilitySnapshot,
    ReliabilitySummary,
    ReleaseGateSnapshot,
    ReleaseReadinessStatus,
)
from clay.session_review.models import SessionReviewSnapshot
from clay.session_review.service import SessionReviewService
from clay.validation_lab.models import ValidationLabSnapshot
from clay.validation_lab.service import ValidationLabService


class ReliabilityService:
    def __init__(
        self,
        *,
        control_center_service: ControlCenterService,
        ai_control_service: AIControlService,
        demo_trading_service: DemoTradingService,
        session_review_service: SessionReviewService,
        validation_lab_service: ValidationLabService,
        audit_writer: AuditWriter,
        event_bus: EventBus,
        session_factory: sessionmaker | None = None,
        clock: Clock = SystemClock(),
    ) -> None:
        self.control_center_service = control_center_service
        self.ai_control_service = ai_control_service
        self.demo_trading_service = demo_trading_service
        self.session_review_service = session_review_service
        self.validation_lab_service = validation_lab_service
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self.session_factory = session_factory
        self._clock = clock
        # ``_last_rechecked_at`` is restored from the
        # ``ops.reliability_state`` singleton row when a ``session_factory``
        # is supplied. Without one (legacy callers and pre-A5 tests), the
        # service falls back to ``None`` (never rechecked) and stays
        # non-persistent.
        if session_factory is None:
            self._last_rechecked_at: datetime | None = None
        else:
            with session_factory() as session:
                state = ReliabilityStateRepository(session).get_or_create()
                self._last_rechecked_at = state.last_rechecked_at
                session.commit()

    def build_snapshot(self, session: Session) -> ReliabilitySnapshot:
        now = self._clock.now()
        control_snapshot = self.control_center_service.build_snapshot(session)
        ai_snapshot = self.ai_control_service.build_snapshot()
        demo_snapshot = self.demo_trading_service.build_snapshot(session)
        review_snapshot = self.session_review_service.build_snapshot(session)
        validation_snapshot = self.validation_lab_service.build_snapshot(session)

        degraded_triggers = self._build_degraded_triggers(
            control_snapshot=control_snapshot,
            ai_fallback=ai_snapshot.fallback,
        )
        fallback_snapshot = LocalFallbackReadinessSnapshot(
            fallback_active=ai_snapshot.fallback.fallback_active,
            local_fallback_ready=ai_snapshot.fallback.local_fallback_ready,
            degraded_roles=list(ai_snapshot.fallback.degraded_roles),
            operator_message=ai_snapshot.fallback.operator_message,
        )
        readiness_checks = self._build_readiness_checks(
            control_snapshot=control_snapshot,
            fallback_snapshot=fallback_snapshot,
            demo_snapshot=demo_snapshot,
            review_snapshot=review_snapshot,
            validation_snapshot=validation_snapshot,
        )
        release_gates = self._build_release_gates(readiness_checks)
        blocking_gate_count = sum(1 for gate in release_gates if gate.blocks_release)
        warning_gate_count = sum(1 for gate in release_gates if gate.status == "warn")

        return ReliabilitySnapshot(
            summary=ReliabilitySummary(
                overall_status=(
                    "degraded"
                    if control_snapshot.summary.overall_status == "degraded"
                    or any(
                        trigger.severity == "critical" for trigger in degraded_triggers
                    )
                    else "healthy"
                ),
                degraded_mode_active=control_snapshot.runtime.state == "degraded",
                release_readiness_status=self._resolve_release_status(
                    blocking_gate_count=blocking_gate_count,
                    warning_gate_count=warning_gate_count,
                ),
                blocking_gate_count=blocking_gate_count,
                warning_gate_count=warning_gate_count,
                operator_message=self._build_operator_message(
                    blocking_gate_count=blocking_gate_count,
                    warning_gate_count=warning_gate_count,
                    degraded_mode_active=control_snapshot.runtime.state == "degraded",
                ),
                last_evaluated_at=now.isoformat(),
                last_rechecked_at=(
                    self._last_rechecked_at.isoformat()
                    if self._last_rechecked_at is not None
                    else None
                ),
            ),
            degraded_triggers=degraded_triggers,
            fallback=fallback_snapshot,
            readiness_checks=readiness_checks,
            release_gates=release_gates,
            incidents=control_snapshot.incidents,
        )

    def recheck(self, session: Session, *, emit: bool = True) -> ReliabilitySnapshot:
        """Re-evaluate reliability and (optionally) publish a recheck event.

        ``emit=True`` (default) preserves the pre-B4 manual-route
        contract: one ``reliability.rechecked`` audit and one
        ``reliability.updated`` bus event per call, after the
        ``last_rechecked_at`` write-through.

        ``emit=False`` is the B4 scheduler-driven path: the
        ``ReliabilityRecheckJob`` calls ``recheck(session, emit=False)``
        and applies its own transition-only audit/bus policy via
        :meth:`emit_recheck_events`. ``last_rechecked_at`` is
        **always** persisted (in-memory + DB) regardless of
        ``emit`` — it is the timestamp the operator trusts for
        "how fresh is the latest recheck", and must survive a
        process restart (A5 persistence contract).
        """
        self._last_rechecked_at = self._clock.now()
        # write-through: persist the new timestamp before publishing.
        # A restart between recheck and the audit/event publish keeps the
        # timestamp in DB; consumers never see ``reliability.rechecked``
        # while the DB still has a stale value. This write is independent
        # of ``emit`` so the B4 scheduler-driven path (which calls
        # ``recheck(emit=False)``) still updates the durable timestamp.
        if self.session_factory is not None:
            ReliabilityStateRepository(session).save(
                last_rechecked_at=self._last_rechecked_at,
            )
        snapshot = self.build_snapshot(session)
        if emit:
            self.emit_recheck_events(snapshot)
        return snapshot

    def emit_recheck_events(self, snapshot: ReliabilitySnapshot) -> None:
        """Public entry point for the ``reliability.rechecked`` audit + bus events.

        Single source of truth for the ``reliability.rechecked`` /
        ``reliability.updated`` payloads — shared by the manual
        ``POST /reliability/recheck`` route (``recheck(emit=True)``)
        and the B4 ``ReliabilityRecheckJob`` (which calls
        ``recheck(emit=False)`` and then invokes this method
        directly on a transition). Keeping the payload shape in
        one place prevents manual-route / scheduler-driven
        drift (recon finding from
        ``obs-2026-06-02-002-b4-recon-side-effect-concern.md``).
        """
        self.audit_writer.write(
            "reliability.rechecked",
            {
                "release_readiness_status": snapshot.summary.release_readiness_status,
                "blocking_gate_count": snapshot.summary.blocking_gate_count,
                "warning_gate_count": snapshot.summary.warning_gate_count,
            },
        )
        self.event_bus.publish(
            "reliability.updated",
            {
                "event_type": "reliability.rechecked",
                "release_readiness_status": snapshot.summary.release_readiness_status,
            },
        )

    def _build_degraded_triggers(
        self,
        *,
        control_snapshot: ControlCenterSnapshot,
        ai_fallback,
    ) -> list[DegradedTriggerSnapshot]:
        triggers: list[DegradedTriggerSnapshot] = []

        if control_snapshot.runtime.state == "degraded":
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="runtime-degraded",
                    severity="critical",
                    title="Runtime degraded",
                    description="Runtime is already in degraded mode and should stay operator-first until stabilized.",
                    recommended_action="Stabilize critical services and return runtime to a non-degraded state only after review.",
                )
            )
        if control_snapshot.runtime.preflight_status == "hard_fail":
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="preflight-blocked",
                    severity="critical",
                    title="Preflight blocked",
                    description="Critical services failed preflight, so active trading posture is not trustworthy.",
                    recommended_action="Restore the blocked critical service before claiming runtime stability.",
                )
            )
        if control_snapshot.ingestion.blocks_active_trading:
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="market-data-blocked",
                    severity="critical",
                    title="Market data blocks active trading",
                    description="Market freshness no longer supports safe active trading decisions.",
                    recommended_action="Refresh ingest, inspect data freshness, and avoid active-session escalation until market data is fresh.",
                )
            )
        if control_snapshot.ingestion.context_status != "fresh":
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="context-degraded",
                    severity="warning",
                    title="Context feeds degraded",
                    description="News or sentiment coverage is degraded and should reduce confidence in operator-facing summaries.",
                    recommended_action="Keep context advisory and avoid trusting unsupported narrative shifts.",
                )
            )
        if ai_fallback.degraded_roles:
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="ai-fallback-gap",
                    severity="critical",
                    title="AI fallback gap detected",
                    description="At least one AI role has entered degraded posture without a safe local fallback path.",
                    recommended_action="Keep synthesis visible but degraded; do not promote strategy/model changes from this posture.",
                )
            )
        elif not ai_fallback.local_fallback_ready:
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="fallback-not-complete",
                    severity="warning",
                    title="Local fallback is incomplete",
                    description="Fallback visibility exists, but not every role has a complete local fallback path.",
                    recommended_action="Treat degraded-mode recovery as constrained and operator-reviewed.",
                )
            )
        if control_snapshot.summary.critical_incident_count > 0:
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="critical-incidents",
                    severity="critical",
                    title="Critical incidents active",
                    description="Operational incidents are still active and increase reliability risk.",
                    recommended_action="Clear the active incidents before any release-readiness claim.",
                )
            )
        elif control_snapshot.summary.active_incident_count > 0:
            triggers.append(
                DegradedTriggerSnapshot(
                    trigger_id="warning-incidents",
                    severity="warning",
                    title="Incidents require review",
                    description="Recent incidents exist even though the system can still be inspected.",
                    recommended_action="Review recent incidents and verify they are understood, not merely ignored.",
                )
            )
        return triggers

    def _build_readiness_checks(
        self,
        *,
        control_snapshot: ControlCenterSnapshot,
        fallback_snapshot: LocalFallbackReadinessSnapshot,
        demo_snapshot: DemoTradingSnapshot,
        review_snapshot: SessionReviewSnapshot,
        validation_snapshot: ValidationLabSnapshot,
    ) -> list[ReliabilityCheckSnapshot]:
        runtime_status = (
            "fail"
            if control_snapshot.runtime.preflight_status == "hard_fail"
            or control_snapshot.runtime.state == "degraded"
            else "pass"
        )
        data_status = "pass"
        if (
            control_snapshot.ingestion.blocks_active_trading
            or control_snapshot.ingestion.market_status != "fresh"
        ):
            data_status = "fail"
        elif control_snapshot.ingestion.context_status != "fresh":
            data_status = "warn"

        ai_status = "pass"
        if fallback_snapshot.degraded_roles:
            ai_status = "fail"
        elif (
            fallback_snapshot.fallback_active
            or not fallback_snapshot.local_fallback_ready
        ):
            ai_status = "warn"

        demo_status_map: dict[str, ReliabilityCheckStatus] = {
            "collecting": "warn",
            "at_risk": "fail",
            "ready_for_review": "pass",
        }
        review_status_map: dict[str, ReliabilityCheckStatus] = {
            "collecting": "warn",
            "waiting_for_resolution": "warn",
            "needs_operator_attention": "fail",
            "review_ready": "pass",
        }
        validation_status = "pass"
        if validation_snapshot.summary.total_runs == 0:
            validation_status = "warn"
        elif validation_snapshot.summary.activation_review_status == "blocked":
            validation_status = "fail"
        elif validation_snapshot.summary.activation_review_status in {
            "staged",
            "collecting",
        }:
            validation_status = "warn"

        incident_status = "pass"
        if control_snapshot.summary.critical_incident_count > 0:
            incident_status = "fail"
        elif control_snapshot.summary.active_incident_count > 0:
            incident_status = "warn"

        return [
            ReliabilityCheckSnapshot(
                check_id="runtime-stability",
                label="Runtime stability",
                status=runtime_status,
                detail=(
                    "Runtime is stable enough for operator work."
                    if runtime_status == "pass"
                    else "Runtime is degraded or preflight is blocked."
                ),
            ),
            ReliabilityCheckSnapshot(
                check_id="data-freshness",
                label="Data freshness",
                status=data_status,
                detail=(
                    f"Market={control_snapshot.ingestion.market_status}, context={control_snapshot.ingestion.context_status}."
                ),
            ),
            ReliabilityCheckSnapshot(
                check_id="local-fallback",
                label="Local fallback posture",
                status=ai_status,
                detail=fallback_snapshot.operator_message,
            ),
            ReliabilityCheckSnapshot(
                check_id="demo-discipline",
                label="Demo discipline",
                status=demo_status_map[demo_snapshot.readiness.status],
                detail=demo_snapshot.readiness.operator_message,
            ),
            ReliabilityCheckSnapshot(
                check_id="review-evidence",
                label="Session review evidence",
                status=review_status_map.get(
                    review_snapshot.summary.review_status, "warn"
                ),
                detail=review_snapshot.summary.operator_message,
            ),
            ReliabilityCheckSnapshot(
                check_id="validation-gate",
                label="Validation gate",
                status=validation_status,
                detail=validation_snapshot.summary.operator_message,
            ),
            ReliabilityCheckSnapshot(
                check_id="incident-budget",
                label="Incident budget",
                status=incident_status,
                detail=(
                    f"{control_snapshot.summary.active_incident_count} incidents, "
                    f"{control_snapshot.summary.critical_incident_count} critical."
                ),
            ),
        ]

    def _build_release_gates(
        self,
        readiness_checks: list[ReliabilityCheckSnapshot],
    ) -> list[ReleaseGateSnapshot]:
        labels = {
            "runtime-stability": "Runtime and preflight gate",
            "data-freshness": "Market/context freshness gate",
            "local-fallback": "Local fallback gate",
            "demo-discipline": "Demo discipline gate",
            "review-evidence": "Session review gate",
            "validation-gate": "Replay and activation gate",
            "incident-budget": "Incident budget gate",
        }
        return [
            ReleaseGateSnapshot(
                gate_id=check.check_id,
                label=labels[check.check_id],
                status=check.status,
                detail=check.detail,
                blocks_release=check.status == "fail",
            )
            for check in readiness_checks
        ]

    def _resolve_release_status(
        self,
        *,
        blocking_gate_count: int,
        warning_gate_count: int,
    ) -> ReleaseReadinessStatus:
        if blocking_gate_count > 0:
            return "blocked"
        if warning_gate_count > 0:
            return "needs_attention"
        return "ready_for_demo"

    def _build_operator_message(
        self,
        *,
        blocking_gate_count: int,
        warning_gate_count: int,
        degraded_mode_active: bool,
    ) -> str:
        if blocking_gate_count > 0 and degraded_mode_active:
            return "Runtime is degraded and release gates are blocked. Stabilize the system before claiming demo readiness."
        if blocking_gate_count > 0:
            return "Release gates are blocked. Fix failing reliability checks before any demo-ready claim."
        if warning_gate_count > 0:
            return "System is usable, but reliability still needs operator attention before a calm demo launch."
        return "Reliability posture is stable enough for a disciplined demo release rehearsal."
