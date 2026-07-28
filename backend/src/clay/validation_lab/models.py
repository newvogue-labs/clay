from typing import Literal

from pydantic import BaseModel, Field

ValidationRunType = Literal["strategy_replay", "model_comparison", "signal_quality"]
ActivationTargetType = Literal["strategy_mode", "model_assignment"]
ActivationSeverity = Literal["info", "warning", "critical"]


class ValidationLabSummary(BaseModel):
    replay_ready: bool
    activation_review_status: str
    total_runs: int
    staged_review_count: int
    operator_message: str


class ValidationRunSnapshot(BaseModel):
    run_id: int
    run_type: ValidationRunType
    label: str
    strategy_mode: str
    model_version: str
    period_start: str
    period_end: str
    trades_simulated: int
    win_rate: float
    net_pnl_pct: float
    max_drawdown_pct: float
    decision_quality_score: float = Field(ge=0.0, le=1.0)
    summary: str
    created_at: str


class ActivationReviewSnapshot(BaseModel):
    review_id: str
    target_type: ActivationTargetType
    target_id: str
    current_value: str
    proposed_value: str
    status: str
    severity: ActivationSeverity
    summary: str
    evidence: dict[str, object]
    created_at: str
    applied_at: str | None


class ValidationLabSnapshot(BaseModel):
    summary: ValidationLabSummary
    runs: list[ValidationRunSnapshot]
    activation_reviews: list[ActivationReviewSnapshot]


class ValidationRunCommand(BaseModel):
    run_type: ValidationRunType
    label: str


class ActivationReviewCommand(BaseModel):
    target_type: ActivationTargetType
    target_id: str
    proposed_value: str


class ActivationApplyCommand(BaseModel):
    review_id: str
