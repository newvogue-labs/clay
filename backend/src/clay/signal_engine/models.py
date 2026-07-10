from pydantic import BaseModel, Field


class RiskTriggerSnapshot(BaseModel):
    """A single risk trigger detected during signal evaluation.

    Triggers are raised when market freshness, context quality, AI health,
    runtime posture, or volume thresholds violate safety constraints.
    Each trigger carries a severity and a prescribed response action
    (e.g. ``block_signal``, ``lower_confidence``, ``switch_to_defensive``).
    """

    trigger_id: str
    severity: str
    title: str
    description: str
    response_action: str


class AppliedPenalty(BaseModel):
    """A ranking penalty applied to a signal during evaluation.

    Records the trigger that caused the penalty, the score delta, and
    a human-readable note explaining the adjustment.
    """

    trigger: str
    delta: float
    note: str


class EvaluatedSignalSnapshot(BaseModel):
    """A single evaluated signal with ranking, risk metadata, and advisory sizing.

    Contains the full decision-support context for one trading pair:
    direction, state lifecycle, confidence, risk triggers, Kelly sizing
    estimates, and human-readable guidance.  Advisory-only — never an
    execution instruction.
    """

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
    applied_penalties: list[AppliedPenalty] = Field(default_factory=list)
    stale_timeframes: list[str] = Field(default_factory=list)
    leader_quote_volume: float = 0.0
    low_quote_volume: bool = False
    probability_estimate: float | None = None
    payoff_estimate: float | None = None
    kelly_fraction: float | None = None
    advisory_position_size: float | None = None
    ev_value: float | None = None
    ev_gate_triggered: bool = False


class SignalEngineSnapshot(BaseModel):
    """Top-level snapshot produced by :class:`SignalEngineService.build_snapshot`.

    Aggregates runtime posture, market/context freshness, strategy-mode
    proposal, and the ranked list of evaluated signals for the current
    cycle.
    """

    runtime_state: str
    workspace_posture: str
    market_status: str
    context_status: str
    strategy_mode_proposal: str
    signals: list[EvaluatedSignalSnapshot]
