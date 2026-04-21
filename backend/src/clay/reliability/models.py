from typing import Literal

from pydantic import BaseModel

from clay.control_center.models import IncidentSnapshot


ReliabilityCheckStatus = Literal["pass", "warn", "fail"]
ReliabilityOverallStatus = Literal["healthy", "degraded"]
ReleaseReadinessStatus = Literal["blocked", "needs_attention", "ready_for_demo"]
TriggerSeverity = Literal["info", "warning", "critical"]


class ReliabilitySummary(BaseModel):
    overall_status: ReliabilityOverallStatus
    degraded_mode_active: bool
    release_readiness_status: ReleaseReadinessStatus
    blocking_gate_count: int
    warning_gate_count: int
    operator_message: str
    last_evaluated_at: str


class DegradedTriggerSnapshot(BaseModel):
    trigger_id: str
    severity: TriggerSeverity
    title: str
    description: str
    recommended_action: str


class LocalFallbackReadinessSnapshot(BaseModel):
    fallback_active: bool
    local_fallback_ready: bool
    degraded_roles: list[str]
    operator_message: str


class ReliabilityCheckSnapshot(BaseModel):
    check_id: str
    label: str
    status: ReliabilityCheckStatus
    detail: str


class ReleaseGateSnapshot(BaseModel):
    gate_id: str
    label: str
    status: ReliabilityCheckStatus
    detail: str
    blocks_release: bool


class ReliabilitySnapshot(BaseModel):
    summary: ReliabilitySummary
    degraded_triggers: list[DegradedTriggerSnapshot]
    fallback: LocalFallbackReadinessSnapshot
    readiness_checks: list[ReliabilityCheckSnapshot]
    release_gates: list[ReleaseGateSnapshot]
    incidents: list[IncidentSnapshot]
