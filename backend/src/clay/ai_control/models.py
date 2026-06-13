from typing import Literal

from pydantic import BaseModel, Field


OverallAIStatus = Literal["healthy", "degraded"]
AssignmentHealth = Literal["healthy", "review_required", "degraded"]
AssignmentMode = Literal["active", "fallback"]
ReviewSeverity = Literal["info", "warning", "critical"]


class AIControlSummary(BaseModel):
    overall_status: OverallAIStatus
    chief_agent_model: str
    active_conflict_count: int
    degraded_role_count: int
    fallback_active: bool
    last_reviewed_at: str | None


class RoleDefinitionSnapshot(BaseModel):
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
    conflict_id: str
    severity: ReviewSeverity
    title: str
    description: str
    affected_roles: list[str]
    recommended_action: str


class ReviewCardSnapshot(BaseModel):
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
    fallback_active: bool
    local_fallback_ready: bool
    degraded_roles: list[str]
    operator_message: str


class RoleRunSummary(BaseModel):
    role_id: str
    latest_run_id: int | None
    latest_run_created_at: str | None
    latest_has_error: bool
    latest_content_length: int
    total_24h: int
    errored_24h: int
    error_rate_24h: float


class RPDBudget(BaseModel):
    model_id: str
    limit: int | None
    used_24h: int
    remaining: int | None


class RegistryVersionInfo(BaseModel):
    fingerprint: str
    model_count: int


class AIControlSnapshot(BaseModel):
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
    role_id: str
    model_id: str


class AssignmentApplyCommand(BaseModel):
    review_id: str

