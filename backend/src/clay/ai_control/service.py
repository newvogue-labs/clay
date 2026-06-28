from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from clay.db.models_ops import AIAgentRun

from clay.core.clock import Clock, SystemClock

from clay.ai_control.models import (
    AIControlSnapshot,
    AIControlSummary,
    AssignmentSnapshot,
    ConflictSnapshot,
    FallbackSnapshot,
    ModelVersionSnapshot,
    RPDBudget,
    RegistryVersionInfo,
    ReviewCardSnapshot,
    RoleDefinitionSnapshot,
    RoleRunSummary,
)
from clay.db.repositories_ops import OpsRepository
from clay.audit.writer import AuditWriter
from clay.config.loader import ConfigLoader
from clay.db.repositories_runtime_state import (
    AIAssignmentRepository,
    AIControlStateRepository,
    INITIAL_ASSIGNMENTS,
)
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
    transport: str  # "local" | "cloud" — per-call routing hint for RoutingModelClient
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


# Static RPD limit map for free-tier models (см. blueprint §10.4).
# Models without a limit (TokenRouter, local) have None.
RPD_LIMITS: dict[str, int | None] = {
    "gemma-4-31b": 1500,
    "gemini-3.1-flash-lite": 500,
    "gemini-2.5-flash": 20,
    "minimax-m3": None,
    "forecast-lite-v1": None,
    "gemma4:e2b-it-qat": None,
}


class AIControlService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        preflight_service: PreflightService,
        config_loader: ConfigLoader,
        audit_writer: AuditWriter,
        event_bus: EventBus,
        session_factory: sessionmaker | None = None,
        clock: Clock = SystemClock(),
    ) -> None:
        self.runtime_manager = runtime_manager
        self.preflight_service = preflight_service
        self.config_loader = config_loader
        self.audit_writer = audit_writer
        self.event_bus = event_bus
        self.session_factory = session_factory
        self._clock = clock
        self.roles = self._build_role_registry()
        self.models = self._build_model_registry()
        # ``assignments``, ``_last_reviewed_at`` and ``_pending_review`` are
        # restored from the ``ops`` runtime-state tables when a
        # ``session_factory`` is supplied. Without one (legacy callers and
        # pre-A3 tests), the service falls back to the in-memory defaults
        # and stays non-persistent.
        # ``roles`` and ``models`` remain code-only registries.
        if session_factory is None:
            # Use the canonical INITIAL_ASSIGNMENTS map so the in-memory
            # fallback never drifts from the source of truth (A3 follow-up).
            self.assignments: dict[str, str] = dict(INITIAL_ASSIGNMENTS)
            self._last_reviewed_at: datetime | None = None
            self._pending_review: PendingReview | None = None
        else:
            with session_factory() as session:
                assignments_repo = AIAssignmentRepository(session)
                state_repo = AIControlStateRepository(session)

                persisted_assignments = assignments_repo.read_all()
                if not persisted_assignments:
                    assignments_repo.bulk_upsert(INITIAL_ASSIGNMENTS)
                    persisted_assignments = dict(INITIAL_ASSIGNMENTS)
                self.assignments = persisted_assignments

                state = state_repo.get_or_create()
                self._last_reviewed_at = state.last_reviewed_at
                if state.pending_review_id is not None:
                    # The 4 pending_* columns are written/cleared together,
                    # so a non-null ``pending_review_id`` implies the rest
                    # are also populated. The fallbacks below are defensive
                    # only.
                    self._pending_review = PendingReview(
                        review_id=state.pending_review_id,
                        role_id=state.pending_review_role_id or "",
                        model_id=state.pending_review_model_id or "",
                        created_at=state.pending_review_created_at or datetime.now(UTC),
                    )
                else:
                    self._pending_review = None
                session.commit()

    def build_snapshot(self, session: Session | None = None) -> AIControlSnapshot:
        # ``session`` is accepted for API uniformity with the other
        # ``build_snapshot(session)`` services in the project and because
        # ``apply_assignment`` forwards it through. Snapshot construction
        # itself only reads the in-memory state restored at __init__, so
        # a missing session is still valid (e.g. ``signal_engine`` calls
        # us without one).
        conflicts = self._build_conflicts()
        assignments = self._build_assignments(conflicts=conflicts)
        degraded_roles = [
            row.role_id for row in assignments if row.assignment_health == "degraded"
        ]
        fallback_active = any(row.assignment_mode == "fallback" for row in assignments)
        chief_model = self.models[self.assignments["chief-agent"]]

        pending_review = (
            self._build_review_card(self._pending_review)
            if self._pending_review
            else None
        )

        runs_summary = self._build_runs_summary(session)
        rpd_budgets = self._build_rpd_budgets(session)
        registry_version = self._build_registry_version()

        return AIControlSnapshot(
            summary=AIControlSummary(
                overall_status="degraded" if degraded_roles else "healthy",
                chief_agent_model=chief_model.display_name,
                active_conflict_count=len(conflicts),
                degraded_role_count=len(degraded_roles),
                fallback_active=fallback_active,
                last_reviewed_at=(
                    self._last_reviewed_at.isoformat()
                    if self._last_reviewed_at is not None
                    else None
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
            fallback=self._build_fallback_snapshot(
                degraded_roles=degraded_roles, fallback_active=fallback_active
            ),
            pending_review=pending_review,
            runs_summary=runs_summary,
            rpd_budgets=rpd_budgets,
            registry_version=registry_version,
        )

    def _build_runs_summary(self, session: Session | None) -> list[RoleRunSummary]:
        if session is None:
            return []
        now = self._clock.now()
        since_24h = now.replace(hour=0, minute=0, second=0, microsecond=0)
        role_ids = list(self.roles.keys())
        latest = OpsRepository(session).list_latest_agent_runs(role_ids)
        stats = OpsRepository(session).agent_runs_stats(role_ids, since=since_24h)
        result: list[RoleRunSummary] = []
        for role_id in role_ids:
            run = latest.get(role_id)
            role_stats = stats.get(role_id, {"total": 0, "errored": 0})
            total = role_stats["total"]
            errored = role_stats["errored"]
            result.append(
                RoleRunSummary(
                    role_id=role_id,
                    latest_run_id=run.id if run else None,
                    latest_run_created_at=run.created_at.isoformat() if run else None,
                    latest_has_error=run.error is not None if run else False,
                    latest_content_length=len(run.content or "") if run else 0,
                    total_24h=total,
                    errored_24h=errored,
                    error_rate_24h=errored / total if total > 0 else 0.0,
                )
            )
        return result

    def _build_rpd_budgets(self, session: Session | None) -> list[RPDBudget]:
        if session is None:
            return []
        now = self._clock.now()
        since_24h = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result: list[RPDBudget] = []
        for model_id in self.models:
            limit = RPD_LIMITS.get(model_id)
            stmt = select(func.count(AIAgentRun.id)).where(
                AIAgentRun.model_id == model_id,
                AIAgentRun.created_at >= since_24h,
            )
            used = 0
            if session is not None:
                used = session.scalar(stmt) or 0
            remaining = (limit - used) if limit is not None else None
            result.append(
                RPDBudget(
                    model_id=model_id,
                    limit=limit,
                    used_24h=used,
                    remaining=remaining,
                )
            )
        return result

    def _build_registry_version(self) -> RegistryVersionInfo:
        sorted_models = sorted(
            self.models.values(),
            key=lambda m: m.model_id,
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    (m.model_id, m.transport, m.provider, m.activation_status)
                    for m in sorted_models
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12]
        return RegistryVersionInfo(
            fingerprint=fingerprint,
            model_count=len(self.models),
        )

    def review_assignment(
        self,
        role_id: str,
        model_id: str,
        *,
        session: Session,
    ) -> ReviewCardSnapshot:
        self._validate_role_and_model(role_id, model_id)
        self._pending_review = PendingReview(
            review_id=str(uuid4()),
            role_id=role_id,
            model_id=model_id,
            created_at=datetime.now(UTC),
        )
        self._last_reviewed_at = self._pending_review.created_at
        # write-through: persist the new pending review and last_reviewed_at
        # immediately so a restart between review and apply still sees them.
        AIControlStateRepository(session).save(
            last_reviewed_at=self._last_reviewed_at,
            pending_review_id=self._pending_review.review_id,
            pending_review_role_id=self._pending_review.role_id,
            pending_review_model_id=self._pending_review.model_id,
            pending_review_created_at=self._pending_review.created_at,
        )
        return self._build_review_card(self._pending_review)

    def apply_assignment(
        self, review_id: str, *, session: Session
    ) -> AIControlSnapshot:
        if self._pending_review is None or self._pending_review.review_id != review_id:
            raise ValueError("review card is missing or stale")

        review_card = self._build_review_card(self._pending_review)
        if review_card.blocks_apply:
            raise ValueError("review card blocks apply")

        previous_model_id = self.assignments[self._pending_review.role_id]
        new_model_id = self._pending_review.model_id
        # write-through: persist the new assignment and clear the pending
        # review row before mutating in-memory state. If the DB write
        # raises, in-memory state stays consistent with the previous
        # commit, so the caller can safely retry.
        AIAssignmentRepository(session).upsert(
            self._pending_review.role_id,
            new_model_id,
        )
        AIControlStateRepository(session).save(
            last_reviewed_at=self._last_reviewed_at,
            pending_review_id=None,
            pending_review_role_id=None,
            pending_review_model_id=None,
            pending_review_created_at=None,
        )
        self.assignments[self._pending_review.role_id] = new_model_id
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
        return self.build_snapshot(session)

    def set_assignment(
        self,
        *,
        role_id: str,
        model_id: str,
        session: Session,
    ) -> None:
        """Promote ``model_id`` to the active model for ``role_id`` and persist.

        **Trusted internal-caller path** — used by
        ``validation_lab.apply_activation(target_type='model_assignment')``
        (A5.5) to route activation-promotion through the A3 write-through
        layer.

        Unlike ``apply_assignment``, this method:

        - does **not** require a pending review (``_pending_review`` is
          untouched);
        - does **not** mutate ``ai_control_state.last_reviewed_at`` (that
          is owned by the operator-review workflow);
        - does **not** mutate ``ai_control_state.pending_review_*``;
        - does **not** re-evaluate ``preflight.blocks_apply`` (validation_lab
          owns its own ``blocked``/``staged``/``ready`` posture gate
          before reaching this method).

        It **does** run the same role/model compatibility validation as
        ``apply_assignment`` (``_validate_role_and_model``) so a single
        source of truth governs what constitutes a valid assignment, and
        it publishes on the same ``ai.updated`` event topic so downstream
        subscribers (frontend snapshot refresh, runtime) react
        identically. The audit verb is split (``ai.assignment.set`` vs
        ``ai.assignment.applied``) so the trail distinguishes operator
        applies from validation promotions, with ``source='validation_lab'``
        in both audit and event payloads for unambiguous triage.

        Idempotent: if ``model_id == previous_model_id`` the DB upsert
        and audit/event emission still run (the upsert is idempotent, and
        the trail is the same regardless of whether the in-memory value
        changed).

        Ordering follows the A3/A5 invariant: ``_validate_role_and_model``
        → DB upsert (write-through, ``flush()`` only) → in-memory
        mutation → audit → event. The caller owns the ``Session`` and
        the surrounding ``commit()`` (see ``validation_lab.apply_activation``).
        """
        self._validate_role_and_model(role_id, model_id)
        previous_model_id = self.assignments[role_id]
        # write-through: DB upsert before in-memory mutation. If the DB
        # write raises, in-memory state stays consistent with the last
        # commit and the caller can safely retry.
        AIAssignmentRepository(session).upsert(role_id, model_id)
        self.assignments[role_id] = model_id
        self.audit_writer.write(
            "ai.assignment.set",
            {
                "role_id": role_id,
                "previous_model_id": previous_model_id,
                "model_id": model_id,
                "source": "validation_lab",
            },
        )
        self.event_bus.publish(
            "ai.updated",
            {
                "role_id": role_id,
                "previous_model_id": previous_model_id,
                "model_id": model_id,
                "source": "validation_lab",
            },
        )

    def _validate_role_and_model(self, role_id: str, model_id: str) -> None:
        if role_id not in self.roles:
            raise ValueError("unknown role")
        if model_id not in self.models:
            raise ValueError("unknown model")
        if role_id not in self.models[model_id].compatible_roles:
            raise ValueError("model is not compatible with role")

    def _build_assignments(
        self, *, conflicts: list[ConflictSnapshot]
    ) -> list[AssignmentSnapshot]:
        runtime_state = self.runtime_manager.snapshot().state
        preflight = self.preflight_service.run()
        conflict_roles = {
            role_id for conflict in conflicts for role_id in conflict.affected_roles
        }
        runtime_degraded = (
            runtime_state == RuntimeState.DEGRADED or preflight.status == "hard_fail"
        )
        confidence_penalty = self.config_loader.load_scope(
            "risk"
        ).degraded_confidence_penalty

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
            self.models[self.assignments[role_id]].fallback_ready
            for role_id in self.roles
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
            risks.append(
                "Runtime is in active_session; changing a model now can reshape live synthesis behavior."
            )

        if preflight.status == "hard_fail":
            severity = "critical"
            blocks_apply = True
            risks.append(
                "Preflight is hard-failed; model changes are blocked until operator issues are resolved."
            )

        if not proposed_model.fallback_ready:
            severity = "warning" if severity != "critical" else severity
            resulting_penalty = self.config_loader.load_scope(
                "risk"
            ).degraded_confidence_penalty
            risks.append("Proposed model has no safe local fallback path.")

        if proposed_model.provider != current_model.provider:
            severity = "warning" if severity == "info" else severity
            risks.append(
                "Provider switch changes latency/error/fallback profile for this role."
            )

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
            risks=risks
            or ["No material risks detected beyond standard operator review."],
            expected_effects=expected_effects,
            resulting_confidence_penalty=resulting_penalty,
            resulting_conflicts=resulting_conflicts,
        )

    def _simulate_conflicts(
        self, assignments: dict[str, str]
    ) -> list[ConflictSnapshot]:
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
                inputs=(
                    "ranked signals",
                    "news sentiment",
                    "forecast output",
                    "runtime posture",
                ),
                outputs=("session thesis", "final confidence", "explanation layer"),
                allowed_actions=(
                    "synthesize",
                    "downgrade_confidence",
                    "request_review",
                ),
                constraints=(
                    "cannot silent-switch",
                    "must expose conflicts",
                    "must explain final decision",
                ),
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

    def transport_for(self, model_id: str) -> str:
        """Return ``"local"`` or ``"cloud"`` for *model_id*.

        Raises ``ModelUnavailableError`` if the model is not in the registry
        (fail-loud — never silently fall back to a default transport).
        """
        entry = self.models.get(model_id)
        if entry is None:
            from clay.ai_control.runner import ModelUnavailableError

            raise ModelUnavailableError(
                f"model {model_id!r} not found in registry; "
                f"no transport can be resolved"
            )
        return entry.transport

    def _build_model_registry(self) -> dict[str, ModelVersion]:
        return {
            "minimax-m3": ModelVersion(
                model_id="minimax-m3",
                display_name="MiniMax-M3",
                provider="TokenRouter (MiniMax)",
                source="cloud",
                transport="cloud",
                training_date="2026-03-01",
                metrics_summary="Multi-provider routing via TokenRouter; fast reasoning with chain-of-thought.",
                notes="Primary chief-agent model for v1 after gpt-5.4 placeholder replacement.",
                activation_status="active",
                compatible_roles=("chief-agent", "market-scanner"),
                fallback_ready=True,
                capability_tags=("reasoning", "routing", "synthesis"),
            ),
            "gemma-4-31b": ModelVersion(
                model_id="gemma-4-31b",
                display_name="Gemma 4 31B IT",
                provider="Google (AI Studio)",
                source="cloud",
                transport="cloud",
                training_date="2026-04-01",
                metrics_summary="Free-tier 1500 RPD, 256K context, supports system prompt via LiteLLM.",
                notes="Subagent workhorse: market-scanner + news-sentiment-agent on free tier.",
                activation_status="active",
                compatible_roles=(
                    "market-scanner",
                    "news-sentiment-agent",
                    "chief-agent",
                ),
                fallback_ready=True,
                capability_tags=("reasoning", "scan", "context"),
            ),
            "gemini-2.5-flash": ModelVersion(
                model_id="gemini-2.5-flash",
                display_name="Gemini 2.5 Flash",
                provider="Google (AI Studio)",
                source="cloud",
                transport="cloud",
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
                transport="local",
                training_date="2025-12-10",
                metrics_summary="Compact local fallback for degraded operation.",
                notes="Not a first-choice model, but safe for fallback posture.",
                activation_status="standby",
                compatible_roles=("forecast-model",),
                fallback_ready=True,
                capability_tags=("forecast", "fallback"),
            ),
            "gemini-3.1-flash-lite": ModelVersion(
                model_id="gemini-3.1-flash-lite",
                display_name="Gemini 3.1 Flash Lite",
                provider="Google (AI Studio)",
                source="cloud",
                transport="cloud",
                training_date="2026-05-01",
                metrics_summary="Ultra-low-latency cloud inference, 500 RPD free tier.",
                notes="Default forecast model. Replaces gemini-2.5-flash (RPD=20 limit).",
                activation_status="active",
                compatible_roles=("forecast-model", "market-scanner"),
                fallback_ready=True,
                capability_tags=("forecast", "low-latency"),
            ),
            "gemma4:e2b-it-qat": ModelVersion(
                model_id="gemma4:e2b-it-qat",
                display_name="Gemma 4 2B IT QAT",
                provider="Google (local Ollama)",
                source="local",
                transport="local",
                training_date="2026-03-01",
                metrics_summary="Dev-local reasoning agent with thinking trace support.",
                notes="Primary dev model for ai-agent-cycle. Native Ollama API.",
                activation_status="active",
                compatible_roles=("chief-agent", "forecast-model", "market-scanner"),
                fallback_ready=False,
                capability_tags=("reasoning", "thinking"),
            ),
        }
