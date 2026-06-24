export type SessionPreflightCheck = {
  check_id: string
  label: string
  status: 'ok' | 'warn' | 'hard_fail'
  reason: string
  blocks_start: boolean
}

export type SessionPreflightSnapshot = {
  status: string
  blocking_reason: string | null
  checks: SessionPreflightCheck[]
}

export type SessionBriefingSignal = {
  signal_id: string
  symbol: string
  direction: string
  state: string
  confidence: number
  ranking_score: number
  setup_summary: string
}

export type SessionBriefingSnapshot = {
  shortlist: SessionBriefingSignal[]
  market_context: string
  sentiment_summary: string
  active_strategy: string
  risk_alerts: string[]
  ai_summary: string
}

export type SessionLifecycleSnapshot = {
  lifecycle_state: 'idle' | 'pre_session' | 'active_session' | 'paused' | 'review'
  runtime_state: string
  session_id: string | null
  current_pair_symbol: string | null
  current_signal_id: string | null
  started_at: string | null
  paused_at: string | null
  resume_ready: boolean
  can_start: boolean
  can_pause: boolean
  can_resume: boolean
  can_complete: boolean
}

export type PairReplacementReviewSnapshot = {
  review_id: string
  current_symbol: string
  proposed_symbol: string
  severity: 'info' | 'warning' | 'critical'
  summary: string
  reasons_to_switch: string[]
  risks: string[]
  approval_required: boolean
  blocks_apply: boolean
}

export type SessionControlSnapshot = {
  preflight: SessionPreflightSnapshot
  briefing: SessionBriefingSnapshot
  lifecycle: SessionLifecycleSnapshot
  pending_pair_replacement: PairReplacementReviewSnapshot | null
}
