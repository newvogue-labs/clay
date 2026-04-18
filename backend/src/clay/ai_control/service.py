from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from clay.ai_control.models import (
    AIControlSnapshot,
    AIControlSummary,
    AssignmentSnapshot,
    ConflictSnapshot,
    FallbackSnapshot,
    ModelVersionSnapshot,
    ReviewCardSnapshot,
    RoleDefinitionSnapshot,
)
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.events.bus import EventBus
from clay.preflight.service import PreflightService
from clay.runtime.manager import RuntimeManager
from clay.runtime.states import RuntimeState


@dataclass(frozen=True)
class RoleDefinition:
    role_id: str
    role_name: str
    responsibility: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    constraints: tuple[str, ...]
    explanation_owner: bool = False
    synthesis_owner: bool = False


@dataclass(frozen=True)
class ModelVersion:
    model_id: str
    display_name: str
    provider: str
    source: str
    training_date: str
    metrics_summary: str
    notes: str
    activation_status: str
    compatible_roles: tuple[str, ...]
    fallback_ready: bool
    capability_tags: tuple[str, ...]


@dataclass
class PendingReview:
    review_id: str
    role_id: str
    model_id: str
    created_at: datetime


class AIControlService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        preflight_service: PreflightService,
        config_loader: ConfigLoader,
        audit_writer: AuditWriter,
        event_bus: EventBus,
    ) -> None:
        self.runtime_manager = runtime_manager
        self.preflight_service = preflight_service
        self.config_loader = config_loader
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self.roles = self._build_role_registry()
        self.models = self._build_model_registry()
        self.assignments: dict[str, str] = {
            "chief-agent": "openai-gpt-5.4",
            "market-scanner": "openai-gpt-5.4-mini",
            "news-sentiment-agent": "anthropic-claude-sonnet-4.5",
            "forecast-model": "gemini-2.5-flash",
        }
        self._last_reviewed_at: datetime | None = None
        self._pending_review: PendingReview | None = None

    def build_snapshot(self, session: Session | None = None) -> AIControlSnapshot:
        del session  # `E5` storage layer is intentionally in-memory for v1 bootstrap.
        now = datetime.now(UTC)
        conflicts = self._build_conflicts()
        assignments = self._build_assignments(conflicts=conflicts)
        degraded_roles = [row.role_id for row in assignments if row.assignment_health == "degraded"]
        fallback_active = any(row.assignment_mode == "fallback" for row in assignments)
        chief_model = self.models[self.assignments["chief-agent"]]

        pending_review = self._build_review_card(self._pending_review) if self._pending_review else None

        return AIControlSnapshot(
            summary=AIControlSummary(
                overall_status="degraded" if degraded_roles else "healthy",
                chief_agent_model=chief_model.display_name,
                active_conflict_count=len(conflicts),
                degraded_role_count=len(degraded_roles),
                fallback_active=fallback_active,
                last_reviewed_at=(
                    self._last_reviewed_at.isoformat() if self._last_reviewed_at is not None else None
                ),
            ),
            roles=[
                RoleDefinitionSnapshot(
                    role_id=role.role_id,
                    role_name=role.role_name,
                    responsibility=role.responsibility,
                    inputs=list(role.inputs),
                    outputs=list(role.outputs),
                    allowed_actions=list(role.allowed_actions),
                    constraints=list(role.constraints),
                    explanation_owner=role.explanation_owner,
                    synthesis_owner=role.synthesis_owner,
                )
                for role in self.roles.values()
            ],
            models=[
                ModelVersionSnapshot(
                    model_id=model.model_id,
                    display_name=model.display_name,
                    provider=model.provider,
                    source=model.source,
                    training_date=model.training_date,
                    metrics_summary=model.metrics_summary,
                    notes=model.notes,
                    activation_status=model.activation_status,
                    compatible_roles=list(model.compatible_roles),
                    fallback_ready=model.fallback_ready,
                )
                for model in self.models.values()
            ],
            assignments=assignments,
            conflicts=conflicts,
            fallback=self._build_fallback_snapshot(degraded_roles=degraded_roles, fallback_active=fallback_active),
            pending_review=pending_review,
        )

    def review_assignment(self, role_id: str, model_id: str) -> ReviewCardSnapshot:
        self._validate_role_and_model(role_id, model_id)
        self._pending_review = PendingReview(
            review_id=str(uuid4()),
            role_id=role_id,
            model_id=model_id,
            created_at=datetime.now(UTC),
        )
        self._last_reviewed_at = self._pending_review.created_at
        return self._build_review_card(self._pending_review)

    def apply_assignment(self, review_id: str) -> AIControlSnapshot:
        if self._pending_review is None or self._pending_review.review_id != review_id:
            raise ValueError("review card is missing or stale")

        review_card = self._build_review_card(self._pending_review)
        if review_card.blocks_apply:
            raise ValueError("review card blocks apply")

        previous_model_id = self.assignments[self._pending_review.role_id]
        self.assignments[self._pending_review.role_id] = self._pending_review.model_id
        self.audit_writer.write(
            "ai.assignment.applied",
            {
                "role_id": self._pending_review.role_id,
                "previous_model_id": previous_model_id,
                "model_id": self._pending_review.model_id,
                "review_id": self._pending_review.review_id,
            },
        )
        self.event_bus.publish(
            "ai.updated",
            {
                "role_id": self._pending_review.role_id,
                "previous_model_id": previous_model_id,
                "model_id": self._pending_review.model_id,
                "review_id": self._pending_review.review_id,
            },
        )
        self._pending_review = None
        return self.build_snapshot()

    def _validate_role_and_model(self, role_id: str, model_id: str) -> None:
        if role_id not in self.roles:
            raise ValueError("unknown role")
        if model_id not in self.models:
            raise ValueError("unknown model")
        if role_id not in self.models[model_id].compatible_roles:
            raise ValueError("model is not compatible with role")

    def _build_assignments(self, *, conflicts: list[ConflictSnapshot]) -> list[AssignmentSnapshot]:
        runtime_state = self.runtime_manager.snapshot().state
        preflight = self.preflight_service.run()
        conflict_roles = {role_id for conflict in conflicts for role_id in conflict.affected_roles}
        runtime_degraded = runtime_state == RuntimeState.DEGRADED or preflight.status == "hard_fail"
        confidence_penalty = self.config_loader.load_scope("risk").degraded_confidence_penalty

        rows: list[AssignmentSnapshot] = []
        for role in self.roles.values():
            model = self.models[self.assignments[role.role_id]]
            mode = "fallback" if runtime_degraded and model.fallback_ready else "active"
            assignment_health = "healthy"
            reason = f"{model.display_name} is assigned and ready."
            review_required = role.role_id in conflict_roles
            penalty = 0.0

            if runtime_degraded and not model.fallback_ready:
                assignment_health = "degraded"
                review_required = True
                penalty = confidence_penalty
                reason = f"{model.display_name} has no local fallback while runtime is degraded."
            elif review_required:
                assignment_health = "review_required"
                penalty = round(confidence_penalty / 2, 2)
                reason = f"{model.display_name} is active, but provider mix creates a reviewable conflict."
            elif mode == "fallback":
                reason = f"{model.display_name} stays active in fallback mode with reduced scope."

            rows.append(
                AssignmentSnapshot(
                    role_id=role.role_id,
                    role_name=role.role_name,
                    model_id=model.model_id,
                    model_display_name=model.display_name,
                    provider=model.provider,
                    assignment_mode=mode,
                    assignment_health=assignment_health,
                    confidence_penalty=penalty,
                    review_required=review_required,
                    reason=reason,
                ),
            )

        return rows

    def _build_conflicts(self) -> list[ConflictSnapshot]:
        conflicts: list[ConflictSnapshot] = []
        chief_provider = self.models[self.assignments["chief-agent"]].provider
        evidence_roles = ("market-scanner", "news-sentiment-agent", "forecast-model")

        for role_id in evidence_roles:
            model = self.models[self.assignments[role_id]]
            if model.provider == chief_provider:
                continue
            conflicts.append(
                ConflictSnapshot(
                    conflict_id=f"provider-mix-{role_id}",
                    severity="warning",
                    title="Provider mix needs review",
                    description=(
                        f"{self.roles[role_id].role_name} uses {model.provider}, while Chief Agent uses "
                        f"{chief_provider}. Synthesis stays allowed, but confidence should be reviewed."
                    ),
                    affected_roles=["chief-agent", role_id],
                    recommended_action="Review the provider split before changing active strategy assumptions.",
                )
            )

        runtime_state = self.runtime_manager.snapshot().state
        if runtime_state == RuntimeState.DEGRADED:
            conflicts.append(
                ConflictSnapshot(
                    conflict_id="runtime-degraded",
                    severity="critical",
                    title="Runtime degraded",
                    description="Assignments remain visible, but active synthesis is constrained by degraded mode.",
                    affected_roles=list(self.roles.keys()),
                    recommended_action="Stabilize runtime or switch to operator-reviewed fallback behavior.",
                )
            )
        return conflicts

    def _build_fallback_snapshot(
        self,
        *,
        degraded_roles: list[str],
        fallback_active: bool,
    ) -> FallbackSnapshot:
        local_fallback_ready = all(
            self.models[self.assignments[role_id]].fallback_ready for role_id in self.roles
        )
        if fallback_active:
            message = "Fallback mode is active. Operator review is required before trusting full-confidence synthesis."
        elif degraded_roles:
            message = "Some roles have no safe fallback path. Keep assignments visible but treat them as degraded."
        else:
            message = "Fallback posture is prepared and currently inactive."

        return FallbackSnapshot(
            fallback_active=fallback_active,
            local_fallback_ready=local_fallback_ready,
            degraded_roles=degraded_roles,
            operator_message=message,
        )

    def _build_review_card(self, pending_review: PendingReview) -> ReviewCardSnapshot:
        role = self.roles[pending_review.role_id]
        current_model = self.models[self.assignments[pending_review.role_id]]
        proposed_model = self.models[pending_review.model_id]
        runtime_state = self.runtime_manager.snapshot().state
        preflight = self.preflight_service.run()

        severity: str = "info"
        risks: list[str] = []
        expected_effects = [
            f"{role.role_name} will switch from {current_model.display_name} to {proposed_model.display_name}.",
        ]
        blocks_apply = False
        approval_required = True
        resulting_penalty = 0.0

        if runtime_state == RuntimeState.ACTIVE_SESSION:
            severity = "critical"
            risks.append("Runtime is in active_session; changing a model now can reshape live synthesis behavior.")

        if preflight.status == "hard_fail":
            severity = "critical"
            blocks_apply = True
            risks.append("Preflight is hard-failed; model changes are blocked until operator issues are resolved.")

        if not proposed_model.fallback_ready:
            severity = "warning" if severity != "critical" else severity
            resulting_penalty = self.config_loader.load_scope("risk").degraded_confidence_penalty
            risks.append("Proposed model has no safe local fallback path.")

        if proposed_model.provider != current_model.provider:
            severity = "warning" if severity == "info" else severity
            risks.append("Provider switch changes latency/error/fallback profile for this role.")

        resulting_assignments = dict(self.assignments)
        resulting_assignments[pending_review.role_id] = pending_review.model_id
        resulting_conflicts = self._simulate_conflicts(resulting_assignments)

        if any(conflict.severity == "critical" for conflict in resulting_conflicts):
            severity = "critical"

        summary = f"Review required before assigning {proposed_model.display_name} to {role.role_name}."

        return ReviewCardSnapshot(
            review_id=pending_review.review_id,
            role_id=role.role_id,
            role_name=role.role_name,
            current_model_id=current_model.model_id,
            proposed_model_id=proposed_model.model_id,
            proposed_model_name=proposed_model.display_name,
            severity=severity,
            approval_required=approval_required,
            blocks_apply=blocks_apply,
            summary=summary,
            risks=risks or ["No material risks detected beyond standard operator review."],
            expected_effects=expected_effects,
            resulting_confidence_penalty=resulting_penalty,
            resulting_conflicts=resulting_conflicts,
        )

    def _simulate_conflicts(self, assignments: dict[str, str]) -> list[ConflictSnapshot]:
        chief_provider = self.models[assignments["chief-agent"]].provider
        conflicts: list[ConflictSnapshot] = []
        for role_id in ("market-scanner", "news-sentiment-agent", "forecast-model"):
            model = self.models[assignments[role_id]]
            if model.provider == chief_provider:
                continue
            conflicts.append(
                ConflictSnapshot(
                    conflict_id=f"provider-mix-{role_id}",
                    severity="warning",
                    title="Provider mix needs review",
                    description=(
                        f"{self.roles[role_id].role_name} would use {model.provider}, while Chief Agent would use "
                        f"{chief_provider}."
                    ),
                    affected_roles=["chief-agent", role_id],
                    recommended_action="Operator review remains required before relying on merged synthesis.",
                )
            )
        return conflicts

    def _build_role_registry(self) -> dict[str, RoleDefinition]:
        return {
            "chief-agent": RoleDefinition(
                role_id="chief-agent",
                role_name="Chief Agent",
                responsibility="Final synthesis, operator-facing summary, and final conflict resolution.",
                inputs=("ranked signals", "news sentiment", "forecast output", "runtime posture"),
                outputs=("session thesis", "final confidence", "explanation layer"),
                allowed_actions=("synthesize", "downgrade_confidence", "request_review"),
                constraints=("cannot silent-switch", "must expose conflicts", "must explain final decision"),
                explanation_owner=True,
                synthesis_owner=True,
            ),
            "market-scanner": RoleDefinition(
                role_id="market-scanner",
                role_name="Market Scanner",
                responsibility="Scan market structure and shortlist tradable candidates.",
                inputs=("bars", "freshness", "shortlist metrics"),
                outputs=("candidate pairs", "market bias"),
                allowed_actions=("scan", "rank", "flag_stale_data"),
                constraints=("cannot finalize signal",),
            ),
            "news-sentiment-agent": RoleDefinition(
                role_id="news-sentiment-agent",
                role_name="News/Sentiment Agent",
                responsibility="Transform context feeds into operator-readable pressure and narrative.",
                inputs=("news items", "sentiment snapshots"),
                outputs=("context summary", "sentiment pressure"),
                allowed_actions=("summarize", "flag_headlines", "surface_conflicts"),
                constraints=("cannot override market signal",),
            ),
            "forecast-model": RoleDefinition(
                role_id="forecast-model",
                role_name="Forecast Model",
                responsibility="Produce directional forecast hints for ranking and review.",
                inputs=("market features", "context features"),
                outputs=("forecast bias", "forecast confidence"),
                allowed_actions=("forecast", "downgrade_confidence"),
                constraints=("cannot auto-activate strategy",),
            ),
        }

    def _build_model_registry(self) -> dict[str, ModelVersion]:
        return {
            "openai-gpt-5.4": ModelVersion(
                model_id="openai-gpt-5.4",
                display_name="GPT-5.4",
                provider="OpenAI",
                source="cloud",
                training_date="2026-02-01",
                metrics_summary="Strong synthesis, stable reasoning, high operator-facing clarity.",
                notes="Preferred for final synthesis and review-card generation.",
                activation_status="active",
                compatible_roles=("chief-agent", "market-scanner"),
                fallback_ready=True,
                capability_tags=("synthesis", "reasoning", "explanations"),
            ),
            "openai-gpt-5.4-mini": ModelVersion(
                model_id="openai-gpt-5.4-mini",
                display_name="GPT-5.4 Mini",
                provider="OpenAI",
                source="cloud",
                training_date="2026-02-01",
                metrics_summary="Lower cost scanner-grade reasoning with good latency.",
                notes="Good default for scanner workloads and light reconciliation.",
                activation_status="active",
                compatible_roles=("market-scanner",),
                fallback_ready=True,
                capability_tags=("scan", "summaries"),
            ),
            "anthropic-claude-sonnet-4.5": ModelVersion(
                model_id="anthropic-claude-sonnet-4.5",
                display_name="Claude Sonnet 4.5",
                provider="Anthropic",
                source="cloud",
                training_date="2026-01-15",
                metrics_summary="Strong context synthesis and nuanced sentiment summaries.",
                notes="Best fit for news-heavy review and sentiment framing.",
                activation_status="active",
                compatible_roles=("news-sentiment-agent", "chief-agent"),
                fallback_ready=False,
                capability_tags=("context", "summaries", "reasoning"),
            ),
            "gemini-2.5-flash": ModelVersion(
                model_id="gemini-2.5-flash",
                display_name="Gemini 2.5 Flash",
                provider="Google",
                source="cloud",
                training_date="2026-01-20",
                metrics_summary="Fast forecast-oriented inference with acceptable explanation quality.",
                notes="Default forecast assistant for v1 validation loops.",
                activation_status="active",
                compatible_roles=("forecast-model", "market-scanner"),
                fallback_ready=True,
                capability_tags=("forecast", "scan"),
            ),
            "forecast-lite-v1": ModelVersion(
                model_id="forecast-lite-v1",
                display_name="Forecast Lite v1",
                provider="Local",
                source="local",
                training_date="2025-12-10",
                metrics_summary="Compact local fallback for degraded operation.",
                notes="Not a first-choice model, but safe for fallback posture.",
                activation_status="standby",
                compatible_roles=("forecast-model",),
                fallback_ready=True,
                capability_tags=("forecast", "fallback"),
            ),
        }
