import type { RuntimeState, ServiceAction } from './runtime'

export type OverallStatus = 'healthy' | 'degraded'
export type Actionability = 'normal' | 'limited' | 'blocked'

export interface GlobalHealthSummary {
  runtime_state: RuntimeState
  overall_status: OverallStatus
  actionability: Actionability
  active_incident_count: number
  critical_incident_count: number
  last_status_refresh_at: string
  blocking_reason: string | null
}

export interface RuntimeStatusSnapshot {
  state: RuntimeState
  allowed_transitions: RuntimeState[]
  preflight_status: string
  blocking_reason: string | null
}

export interface ServiceCardSnapshot {
  service_id: string
  service_name: string
  service_kind: string
  lifecycle_class: string
  criticality: string
  status: string
  last_heartbeat_at: string | null
  last_error: string | null
  freshness_status: string | null
  allowed_actions: ServiceAction[]
}

export interface MarketFreshnessItem {
  symbol: string
  timeframe: string
  status: string
  evaluated_at: string
  latest_bar_open_time: string | null
  reason: string
}

export interface ConnectorStatusSnapshot {
  connector_id: string
  connector_type: string
  status: string
  observed_at: string
}

export interface IngestionHealthSnapshot {
  market_status: string
  context_status: string
  blocks_active_trading: boolean
  market_items: MarketFreshnessItem[]
  connectors: ConnectorStatusSnapshot[]
}

export interface IncidentSnapshot {
  source_name: string
  severity: string
  lifecycle_status?: string
  message: string
  recorded_at: string
  resolved_at?: string | null
  resolution_message?: string | null
}

export interface AuditEventSnapshot {
  timestamp: string
  event_type: string
  payload: Record<string, unknown>
}

export interface ConfigScopeSnapshot {
  scope: string
  mutable: boolean
  values: Record<string, unknown>
}

export interface ActiveConfigurationSnapshot {
  config_dir: string
  scopes: ConfigScopeSnapshot[]
}

export interface ControlCenterSnapshot {
  summary: GlobalHealthSummary
  runtime: RuntimeStatusSnapshot
  services: ServiceCardSnapshot[]
  ingestion: IngestionHealthSnapshot
  incidents: IncidentSnapshot[]
  audit: AuditEventSnapshot[]
  config: ActiveConfigurationSnapshot
}

export interface IngestionRunResult {
  started_at: string
  finished_at: string
  market_records_written: number
  news_records_written: number
  sentiment_records_written: number
  freshness_updates_written: number
  connector_statuses: Array<Record<string, unknown>>
  incidents: Array<Record<string, unknown>>
}
