from typing import Literal

from pydantic import BaseModel, Field


OverallAIStatus = Literal["healthy", "degraded"]
"""Aggregate health of all AI-control assignments: ``healthy`` when no degraded roles, ``degraded`` otherwise."""

AssignmentHealth = Literal["healthy", "review_required", "degraded"]
"""Per-role health: ``healthy`` (no issues), ``review_required`` (provider-mix conflict), or ``degraded`` (no fallback)."""

AssignmentMode = Literal["active", "fallback"]
"""Whether the role runs in normal ``active`` mode or ``fallback`` (degraded runtime, reduced scope)."""

ReviewSeverity = Literal["info", "warning", "critical"]
"""Operator-review severity: ``info`` (standard), ``warning`` (risks present), or ``critical`` (apply blocked)."""


class AIControlSummary(BaseModel):
    """Top-level health summary for the entire AI-control subsystem.

    Consumed by the frontend status badge and the chief-agent confidence
    gate. A ``healthy`` overall status means all roles are assigned to
    ready models; ``degraded`` triggers the confidence-penalty multiplier.
    """

    overall_status: OverallAIStatus
    chief_agent_model: str
    active_conflict_count: int
    degraded_role_count: int
    fallback_active: bool
    last_reviewed_at: str | None


class RoleDefinitionSnapshot(BaseModel):
    """Snapshot of a single AI role's definition from the code-only registry.

    Describes what the role does, its I/O contract, allowed actions, and
    hard constraints. The ``explanation_owner`` and ``synthesis_owner``
    flags mark the Chief Agent's special responsibilities.
    """

    role_id: str
    role_name: str
    responsibility: str
    inputs: list[str]
    outputs: list[str]
    allowed_actions: list[str]
    constraints: list[str]
    explanation_owner: bool = False
    synthesis_owner: bool = False


class ModelVersionSnapshot(BaseModel):
    """Snapshot of a registered AI model version.

    Captures provider, source, activation status, compatible roles, and
    fallback readiness for the operator dashboard's model registry view.
    """

    model_id: str
    display_name: str
    provider: str
    source: str
    training_date: str
    metrics_summary: str
    notes: str
    activation_status: str
    compatible_roles: list[str]
    fallback_ready: bool


class AssignmentSnapshot(BaseModel):
    """Current assignment of a model to a role with health and confidence state.

    The ``confidence_penalty`` is non-zero when the assignment is degraded
    or under provider-mix review. The ``reason`` field provides a
    human-readable explanation surfaced in the operator dashboard.
    """

    role_id: str
    role_name: str
    model_id: str
    model_display_name: str
    provider: str
    assignment_mode: AssignmentMode
    assignment_health: AssignmentHealth
    confidence_penalty: float = Field(ge=0.0, le=1.0)
    review_required: bool
    reason: str


class ConflictSnapshot(BaseModel):
    """Detected conflict between assignments that requires operator review.

    Conflicts arise from provider-mix mismatches (evidence model uses a
    different provider than the chief-agent) or runtime degradation.
    Each conflict carries a severity and recommended remediation action.
    """

    conflict_id: str
    severity: ReviewSeverity
    title: str
    description: str
    affected_roles: list[str]
    recommended_action: str


class ReviewCardSnapshot(BaseModel):
    """Operator review card for a proposed model-to-role assignment change.

    Created by ``review_assignment`` and consumed by the frontend review
    panel. The ``blocks_apply`` flag is ``True`` when preflight hard-fails
    or runtime is in active session, preventing the operator from applying
    the change until the blocking condition is resolved.
    """

    review_id: str
    role_id: str
    role_name: str
    current_model_id: str
    proposed_model_id: str
    proposed_model_name: str
    severity: ReviewSeverity
    approval_required: bool
    blocks_apply: bool
    summary: str
    risks: list[str]
    expected_effects: list[str]
    resulting_confidence_penalty: float = Field(ge=0.0, le=1.0)
    resulting_conflicts: list[ConflictSnapshot]


class FallbackSnapshot(BaseModel):
    """Fallback posture summary: whether fallback is active and which roles are degraded.

    The ``operator_message`` provides a human-readable status line for
    the dashboard. When ``fallback_active`` is true, the chief-agent's
    confidence is automatically reduced per the risk config penalty.
    """

    fallback_active: bool
    local_fallback_ready: bool
    degraded_roles: list[str]
    operator_message: str


class RoleRunSummary(BaseModel):
    """24-hour run statistics for a single AI role.

    Summarises the latest run outcome and aggregate error rate, used by
    the operator dashboard to surface role health at a glance. The
    ``error_rate_24h`` field drives the red/yellow/green indicator.
    """

    role_id: str
    latest_run_id: int | None
    latest_run_created_at: str | None
    latest_has_error: bool
    latest_content_length: int
    total_24h: int
    errored_24h: int
    error_rate_24h: float


class RPDBudget(BaseModel):
    """Requests-per-day budget tracking for a single model.

    Free-tier models have hard RPD limits; ``remaining`` counts down
    towards zero. ``None`` limit means unlimited (local models or
    paid-tier cloud). Used by the operator dashboard budget widget.
    """

    model_id: str
    limit: int | None
    used_24h: int
    remaining: int | None


class RegistryVersionInfo(BaseModel):
    """Fingerprint of the current model registry for change detection.

    The ``fingerprint`` is a SHA-256 hash of (model_id, transport,
    provider, activation_status) tuples, enabling the frontend to detect
    registry changes without polling the full model list.
    """

    fingerprint: str
    model_count: int


class AIControlSnapshot(BaseModel):
    """Complete AI-control snapshot: roles, models, assignments, conflicts, and review state.

    This is the root response model for the ``/api/ai-control`` endpoint.
    The frontend renders the entire dashboard from a single snapshot
    call. The ``pending_review`` field is ``None`` when no operator
    review is in progress.
    """

    summary: AIControlSummary
    roles: list[RoleDefinitionSnapshot]
    models: list[ModelVersionSnapshot]
    assignments: list[AssignmentSnapshot]
    conflicts: list[ConflictSnapshot]
    fallback: FallbackSnapshot
    pending_review: ReviewCardSnapshot | None
    runs_summary: list[RoleRunSummary] = []
    rpd_budgets: list[RPDBudget] = []
    registry_version: RegistryVersionInfo | None = None


class AssignmentReviewCommand(BaseModel):
    """Command to initiate operator review for assigning a model to a role.

    Sent by the frontend when the operator selects a new model for a role.
    The service validates compatibility and returns a ReviewCardSnapshot.
    """

    role_id: str
    model_id: str


class AssignmentApplyCommand(BaseModel):
    """Command to apply a previously reviewed assignment change.

    Sent by the frontend after the operator confirms the review card.
    The ``review_id`` must match a pending review; stale or missing
    reviews are rejected with a ValueError.
    """

    review_id: str
