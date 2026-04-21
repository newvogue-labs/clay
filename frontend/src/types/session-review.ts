export type SessionReviewSummary = {
  review_status: string
  total_demo_records: number
  resolved_demo_records: number
  cumulative_pnl_pct: number
  feedback_count: number
  last_reviewed_at: string | null
  operator_message: string
}

export type SessionReviewFilterOptions = {
  pairs: string[]
  strategies: string[]
  model_versions: string[]
  confidence_bands: string[]
}

export type SessionReviewFilterState = {
  pair: string | null
  strategy: string | null
  model_version: string | null
  confidence_band: string | null
}

export type ReviewedTradeRecord = {
  record_id: number
  session_id: string
  signal_id: string
  symbol: string
  strategy_mode: string
  model_version: string
  confidence_band: string
  operator_action: string
  outcome_status: string
  pnl_pct: number | null
  recorded_at: string
  observed_at: string | null
}

export type FeedbackItemSnapshot = {
  feedback_id: number
  session_id: string
  signal_id: string
  symbol: string
  strategy_mode: string | null
  model_version: string | null
  confidence_band: string | null
  outcome_status: string | null
  feedback_label: string
  notes: string | null
  created_at: string
  score: number | null
}

export type NormalizedAuditEventSnapshot = {
  timestamp: string
  actor: string
  module: string
  event_type: string
  object_id: string | null
  explanation: string
  severity: string
}

export type AIReviewCardSnapshot = {
  card_id: string
  severity: string
  title: string
  summary: string
  recommendations: string[]
  confirmation_required_for_changes: boolean
}

export type SessionReviewSnapshot = {
  summary: SessionReviewSummary
  filters: SessionReviewFilterState
  filter_options: SessionReviewFilterOptions
  records: ReviewedTradeRecord[]
  feedback: FeedbackItemSnapshot[]
  audit: NormalizedAuditEventSnapshot[]
  ai_review_cards: AIReviewCardSnapshot[]
}
