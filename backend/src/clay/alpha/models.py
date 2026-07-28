from typing import Literal

from pydantic import BaseModel

AlphaGateStatus = Literal["pass", "warn", "fail"]
AlphaReadinessStatus = Literal["blocked", "needs_attention", "operator_path_ready"]


class AlphaReadinessSummary(BaseModel):
    readiness_status: AlphaReadinessStatus
    operator_path_ready: bool
    blocking_gate_count: int
    warning_gate_count: int
    next_action: str


class AlphaReadinessGateSnapshot(BaseModel):
    gate_id: str
    label: str
    status: AlphaGateStatus
    blocks_alpha: bool
    detail: str


class AlphaOperatorStepSnapshot(BaseModel):
    step_id: str
    label: str
    status: AlphaGateStatus
    detail: str
    target_screen: str
    action_label: str
    is_next: bool


class AlphaReadinessEvidence(BaseModel):
    runtime_state: str
    preflight_status: str
    workspace_posture: str
    focus_symbol: str | None
    focused_signal_state: str
    session_lifecycle_state: str
    demo_readiness_status: str
    demo_record_count: int
    review_status: str
    validation_replay_ready: bool
    validation_run_count: int
    release_readiness_status: str


class AlphaReadinessSnapshot(BaseModel):
    summary: AlphaReadinessSummary
    gates: list[AlphaReadinessGateSnapshot]
    operator_steps: list[AlphaOperatorStepSnapshot]
    evidence: AlphaReadinessEvidence
