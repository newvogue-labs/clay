export type DemoReadinessGateSnapshot = {
  gate_id: string
  label: string
  status: 'pass' | 'warn' | 'fail'
  detail: string
}

export type DemoReadinessSnapshot = {
  status: 'collecting' | 'at_risk' | 'ready_for_review'
  operator_message: string
  distinct_session_count: number
  total_records: number
  resolved_record_count: number
  profitable_record_count: number
  cumulative_pnl_pct: number
  outcome_counts: Record<string, number>
  gates: DemoReadinessGateSnapshot[]
}

export type DemoActiveSessionSnapshot = {
  lifecycle_state: string
  session_id: string | null
  current_pair_symbol: string | null
  current_signal_id: string | null
  can_log_decision: boolean
  blocking_reason: string | null
}

export type DemoTradeRecordSnapshot = {
  record_id: number
  session_id: string
  signal_id: string
  symbol: string
  executed_symbol: string | null
  operator_action: 'entered' | 'skipped' | 'off_signal' | 'entered_late'
  operator_notes: string | null
  recorded_at: string
  external_trade_id: string | null
  broker_status: string | null
  entry_price: number | null
  exit_price: number | null
  pnl_pct: number | null
  observed_at: string | null
  outcome_status: 'matched' | 'missed' | 'late_matched' | 'mismatched' | 'unresolved'
  awaiting_result: boolean
}

export type DemoTradingSnapshot = {
  readiness: DemoReadinessSnapshot
  active_session: DemoActiveSessionSnapshot
  records: DemoTradeRecordSnapshot[]
}
