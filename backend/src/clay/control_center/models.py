from typing import Any

from pydantic import BaseModel


class GlobalHealthSummary(BaseModel):
    runtime_state: str
    overall_status: str
    actionability: str
    active_incident_count: int
    critical_incident_count: int
    last_status_refresh_at: str
    blocking_reason: str | None


class RuntimeStatusSnapshot(BaseModel):
    state: str
    allowed_transitions: list[str]
    preflight_status: str
    blocking_reason: str | None


class ServiceCardSnapshot(BaseModel):
    service_id: str
    service_name: str
    service_kind: str
    lifecycle_class: str
    criticality: str
    status: str
    last_heartbeat_at: str | None
    last_error: str | None
    freshness_status: str | None
    allowed_actions: list[str]


class MarketFreshnessItem(BaseModel):
    symbol: str
    timeframe: str
    status: str
    evaluated_at: str
    latest_bar_open_time: str | None
    reason: str


class ConnectorStatusSnapshot(BaseModel):
    connector_id: str
    connector_type: str
    status: str
    observed_at: str


class IngestionHealthSnapshot(BaseModel):
    market_status: str
    context_status: str
    blocks_active_trading: bool
    market_items: list[MarketFreshnessItem]
    connectors: list[ConnectorStatusSnapshot]


class IncidentSnapshot(BaseModel):
    source_name: str
    severity: str
    lifecycle_status: str
    message: str
    recorded_at: str
    resolved_at: str | None = None
    resolution_message: str | None = None


class AuditEventSnapshot(BaseModel):
    timestamp: str
    event_type: str
    payload: dict[str, Any]


class ConfigScopeSnapshot(BaseModel):
    scope: str
    mutable: bool
    values: dict[str, Any]


class ActiveConfigurationSnapshot(BaseModel):
    config_dir: str
    scopes: list[ConfigScopeSnapshot]


class ControlCenterSnapshot(BaseModel):
    summary: GlobalHealthSummary
    runtime: RuntimeStatusSnapshot
    services: list[ServiceCardSnapshot]
    ingestion: IngestionHealthSnapshot
    incidents: list[IncidentSnapshot]
    audit: list[AuditEventSnapshot]
    config: ActiveConfigurationSnapshot
