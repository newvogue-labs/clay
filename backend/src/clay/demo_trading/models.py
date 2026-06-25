from typing import Literal

from pydantic import BaseModel

OperatorAction = Literal["entered", "skipped", "off_signal", "entered_late"]

OutcomeStatus = Literal["matched", "missed", "late_matched", "mismatched", "unresolved"]

ProvenanceSource = Literal["baseline", "live", "replay"]
ReadinessGateStatus = Literal["pass", "warn", "fail"]
ReadinessStatus = Literal["collecting", "at_risk", "ready_for_review"]


class DemoReadinessGateSnapshot(BaseModel):
    gate_id: str
    label: str
    status: ReadinessGateStatus
    detail: str


class DemoReadinessSnapshot(BaseModel):
    status: ReadinessStatus
    operator_message: str
    distinct_session_count: int
    total_records: int
    resolved_record_count: int
    profitable_record_count: int
    cumulative_pnl_pct: float
    outcome_counts: dict[str, int]
    gates: list[DemoReadinessGateSnapshot]


class DemoActiveSessionSnapshot(BaseModel):
    lifecycle_state: str
    session_id: str | None
    current_pair_symbol: str | None
    current_signal_id: str | None
    can_log_decision: bool
    blocking_reason: str | None


class DemoTradeRecordSnapshot(BaseModel):
    record_id: int
    session_id: str
    signal_id: str
    symbol: str
    executed_symbol: str | None
    operator_action: OperatorAction
    operator_notes: str | None
    recorded_at: str
    external_trade_id: str | None
    broker_status: str | None
    entry_price: float | None
    exit_price: float | None
    pnl_pct: float | None
    observed_at: str | None
    outcome_status: OutcomeStatus
    awaiting_result: bool
    advisory_size_pct: float | None = None


class DemoTradingSnapshot(BaseModel):
    readiness: DemoReadinessSnapshot
    active_session: DemoActiveSessionSnapshot
    records: list[DemoTradeRecordSnapshot]


class DemoTradeLogCommand(BaseModel):
    operator_action: OperatorAction
    operator_notes: str | None = None
    executed_symbol: str | None = None


class DemoResultIngestCommand(BaseModel):
    record_id: int
    external_trade_id: str | None = None
    broker_status: str = "closed"
    entry_price: float | None = None
    exit_price: float | None = None
    pnl_pct: float
