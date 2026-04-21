from typing import Literal

from pydantic import BaseModel


FeedbackLabel = Literal["useful", "noise", "needs_follow_up"]


class SessionReviewSummary(BaseModel):
    review_status: str
    total_demo_records: int
    resolved_demo_records: int
    cumulative_pnl_pct: float
    feedback_count: int
    last_reviewed_at: str | None
    operator_message: str


class SessionReviewFilterOptions(BaseModel):
    pairs: list[str]
    strategies: list[str]
    model_versions: list[str]
    confidence_bands: list[str]


class SessionReviewFilterState(BaseModel):
    pair: str | None
    strategy: str | None
    model_version: str | None
    confidence_band: str | None


class ReviewedTradeRecord(BaseModel):
    record_id: int
    session_id: str
    signal_id: str
    symbol: str
    strategy_mode: str
    model_version: str
    confidence_band: str
    operator_action: str
    outcome_status: str
    pnl_pct: float | None
    recorded_at: str
    observed_at: str | None


class FeedbackItemSnapshot(BaseModel):
    feedback_id: int
    session_id: str
    signal_id: str
    symbol: str
    strategy_mode: str | None
    model_version: str | None
    confidence_band: str | None
    outcome_status: str | None
    feedback_label: str
    notes: str | None
    created_at: str
    score: float | None


class NormalizedAuditEventSnapshot(BaseModel):
    timestamp: str
    actor: str
    module: str
    event_type: str
    object_id: str | None
    explanation: str
    severity: str


class AIReviewCardSnapshot(BaseModel):
    card_id: str
    severity: str
    title: str
    summary: str
    recommendations: list[str]
    confirmation_required_for_changes: bool


class SessionReviewSnapshot(BaseModel):
    summary: SessionReviewSummary
    filters: SessionReviewFilterState
    filter_options: SessionReviewFilterOptions
    records: list[ReviewedTradeRecord]
    feedback: list[FeedbackItemSnapshot]
    audit: list[NormalizedAuditEventSnapshot]
    ai_review_cards: list[AIReviewCardSnapshot]


class FeedbackCreateCommand(BaseModel):
    record_id: int
    feedback_label: FeedbackLabel
    notes: str | None = None
