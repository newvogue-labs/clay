from typing import Literal

from pydantic import BaseModel, Field

from clay.signal_engine.models import AppliedPenalty


PreflightCheckStatus = Literal["ok", "hard_fail"]
SessionLifecycleState = Literal["idle", "pre_session", "active_session", "paused", "review"]
ReviewSeverity = Literal["info", "warning", "critical"]


class SessionPreflightCheck(BaseModel):
    check_id: str
    label: str
    status: PreflightCheckStatus
    reason: str
    blocks_start: bool


class SessionPreflightSnapshot(BaseModel):
    status: str
    blocking_reason: str | None
    checks: list[SessionPreflightCheck]


class SessionBriefingSignal(BaseModel):
    signal_id: str
    symbol: str
    direction: str
    state: str
    confidence: float = Field(ge=0.0, le=1.0)
    ranking_score: float = Field(ge=0.0, le=1.0)
    setup_summary: str
    applied_penalties: list[AppliedPenalty] = Field(default_factory=list)
    stale_timeframes: list[str] = Field(default_factory=list)
    leader_quote_volume: float = 0.0
    low_quote_volume: bool = False


class SessionBriefingSnapshot(BaseModel):
    shortlist: list[SessionBriefingSignal]
    market_context: str
    sentiment_summary: str
    active_strategy: str
    risk_alerts: list[str]
    ai_summary: str


class SessionLifecycleSnapshot(BaseModel):
    lifecycle_state: SessionLifecycleState
    runtime_state: str
    session_id: str | None
    current_pair_symbol: str | None
    current_signal_id: str | None
    started_at: str | None
    paused_at: str | None
    resume_ready: bool
    can_start: bool
    can_pause: bool
    can_resume: bool
    can_complete: bool


class PairReplacementReviewSnapshot(BaseModel):
    review_id: str
    current_symbol: str
    proposed_symbol: str
    severity: ReviewSeverity
    summary: str
    reasons_to_switch: list[str]
    risks: list[str]
    approval_required: bool
    blocks_apply: bool


class SessionControlSnapshot(BaseModel):
    preflight: SessionPreflightSnapshot
    briefing: SessionBriefingSnapshot
    lifecycle: SessionLifecycleSnapshot
    pending_pair_replacement: PairReplacementReviewSnapshot | None


class PairReplacementReviewCommand(BaseModel):
    proposed_symbol: str | None = None


class PairReplacementApplyCommand(BaseModel):
    review_id: str
