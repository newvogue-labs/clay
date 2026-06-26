from typing import Any

from pydantic import BaseModel


class FocusPairSnapshot(BaseModel):
    symbol: str
    display_name: str
    is_focused: bool
    role: str
    last_price: float
    pct_change_24h: float
    volatility: float
    last_scan_at: str
    active_signal_id: str | None
    focus_source: str


class WorkspaceStateSnapshot(BaseModel):
    runtime_state: str
    workspace_posture: str
    focused_signal_state: str
    can_open_binance: bool
    can_log_decision: bool
    blocking_reason: str | None = None
    execution_mode: str | None = None
    execution_override_state: str | None = None


class WorkspaceSignalSummary(BaseModel):
    signal_id: str
    pair: str
    direction: str
    state: str
    confidence: float
    ranking_score: float
    confidence_penalty: float
    response_action: str
    strategy_mode: str
    setup_summary: str
    last_updated_at: str


class MonitoringPoolItem(BaseModel):
    symbol: str
    display_name: str
    role: str
    availability_status: str
    last_price: float
    pct_change_24h: float
    volatility: float
    has_active_signal: bool
    is_focused: bool


class SituationMapSnapshot(BaseModel):
    directional_bias: str
    entry_hint: str
    target_hint: str
    invalidation_hint: str
    analyst_note: str


class ReasoningSnapshot(BaseModel):
    thesis: str
    technical_context: list[str]
    execution_notes: list[str]


class RiskSnapshot(BaseModel):
    risk_posture: str
    confidence_label: str
    confidence_penalty: float
    response_action: str
    strategy_mode: str
    risk_reward_hint: str
    action_guidance: str
    active_triggers: list[str]


class NewsContextItem(BaseModel):
    headline: str
    summary: str | None
    source_name: str
    published_at: str
    source_url: str | None


class SentimentContextItem(BaseModel):
    source_name: str
    sentiment_label: str
    sentiment_score: float
    captured_at: str


class UpdateMetaSnapshot(BaseModel):
    focus_last_updated_at: str
    market_status: str
    context_status: str
    last_ingestion_at: str | None


class WorkspaceSnapshot(BaseModel):
    focus_pair: FocusPairSnapshot
    workspace_state: WorkspaceStateSnapshot
    signals: list[WorkspaceSignalSummary]
    monitoring_pool: list[MonitoringPoolItem]
    situation_map: SituationMapSnapshot
    reasoning: ReasoningSnapshot
    risk: RiskSnapshot
    news: list[NewsContextItem]
    sentiment: list[SentimentContextItem]
    update_meta: UpdateMetaSnapshot


class FocusSelectionSnapshot(BaseModel):
    focus_pair: FocusPairSnapshot
    workspace_state: WorkspaceStateSnapshot


class FocusCommand(BaseModel):
    symbol: str
    focus_source: str
    signal_id: str | None = None


class WorkspaceEventPayload(BaseModel):
    event_type: str
    payload: dict[str, Any]
