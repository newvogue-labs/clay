from pydantic import BaseModel, Field


class RiskTriggerSnapshot(BaseModel):
    trigger_id: str
    severity: str
    title: str
    description: str
    response_action: str


class EvaluatedSignalSnapshot(BaseModel):
    signal_id: str
    symbol: str
    display_name: str
    direction: str
    state: str
    confidence: float = Field(ge=0.0, le=1.0)
    ranking_score: float = Field(ge=0.0, le=1.0)
    confidence_penalty: float = Field(ge=0.0, le=1.0)
    strategy_mode: str
    response_action: str
    setup_summary: str
    technical_context: list[str]
    execution_notes: list[str]
    risk_triggers: list[RiskTriggerSnapshot]
    risk_posture: str
    risk_reward_hint: str
    action_guidance: str
    directional_bias: str
    entry_hint: str
    target_hint: str
    invalidation_hint: str
    analyst_note: str
    last_updated_at: str


class SignalEngineSnapshot(BaseModel):
    runtime_state: str
    workspace_posture: str
    market_status: str
    context_status: str
    strategy_mode_proposal: str
    signals: list[EvaluatedSignalSnapshot]
