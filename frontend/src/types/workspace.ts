export type WorkspaceRuntimeState =
  | 'background_monitoring'
  | 'pre_session'
  | 'active_session'
  | 'paused'
  | 'review'
  | 'degraded'

export interface FocusPairSnapshot {
  symbol: string
  display_name: string
  is_focused: boolean
  role: string
  last_price: number
  pct_change_24h: number
  volatility: number
  last_scan_at: string
  active_signal_id: string | null
  focus_source: string
}

export type ExecutionOverrideState = 'pending' | 'confirmed'

export interface WorkspaceStateSnapshot {
  runtime_state: WorkspaceRuntimeState
  workspace_posture: string
  focused_signal_state: 'active' | 'weakening' | 'invalidated' | 'absent'
  can_open_binance: boolean
  can_log_decision: boolean
  blocking_reason: string | null
  execution_mode: string | null
  execution_override_state: ExecutionOverrideState | null
  execution_override_expires_at: string | null
  server_time: string
}

export interface WorkspaceSignalSummary {
  signal_id: string
  pair: string
  direction: string
  state: string
  confidence: number
  ranking_score: number
  confidence_penalty: number
  response_action: string
  strategy_mode: string
  setup_summary: string
  last_updated_at: string
}

export interface MonitoringPoolItem {
  symbol: string
  display_name: string
  role: string
  availability_status: string
  last_price: number
  pct_change_24h: number
  volatility: number
  has_active_signal: boolean
  is_focused: boolean
}

export interface SituationMapSnapshot {
  directional_bias: string
  entry_hint: string
  target_hint: string
  invalidation_hint: string
  analyst_note: string
}

export interface ReasoningSnapshot {
  thesis: string
  technical_context: string[]
  execution_notes: string[]
}

export interface RiskSnapshot {
  risk_posture: string
  confidence_label: string
  confidence_penalty: number
  response_action: string
  strategy_mode: string
  risk_reward_hint: string
  action_guidance: string
  active_triggers: string[]
}

export interface NewsContextItem {
  headline: string
  summary: string | null
  source_name: string
  published_at: string
  source_url: string | null
}

export interface SentimentContextItem {
  source_name: string
  sentiment_label: string
  sentiment_score: number
  captured_at: string
}

export interface UpdateMetaSnapshot {
  focus_last_updated_at: string
  market_status: string
  context_status: string
  last_ingestion_at: string | null
}

export interface WorkspaceSnapshot {
  focus_pair: FocusPairSnapshot
  workspace_state: WorkspaceStateSnapshot
  signals: WorkspaceSignalSummary[]
  monitoring_pool: MonitoringPoolItem[]
  situation_map: SituationMapSnapshot
  reasoning: ReasoningSnapshot
  risk: RiskSnapshot
  news: NewsContextItem[]
  sentiment: SentimentContextItem[]
  update_meta: UpdateMetaSnapshot
}
