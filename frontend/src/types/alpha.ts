export type AlphaGateStatus = 'pass' | 'warn' | 'fail'

export type AlphaReadinessStatus = 'blocked' | 'needs_attention' | 'operator_path_ready'

export type AlphaReadinessSummary = {
  readiness_status: AlphaReadinessStatus
  operator_path_ready: boolean
  blocking_gate_count: number
  warning_gate_count: number
  next_action: string
}

export type AlphaReadinessGateSnapshot = {
  gate_id: string
  label: string
  status: AlphaGateStatus
  blocks_alpha: boolean
  detail: string
}

export type AlphaOperatorStepSnapshot = {
  step_id: string
  label: string
  status: AlphaGateStatus
  detail: string
}

export type AlphaReadinessEvidence = {
  runtime_state: string
  preflight_status: string
  workspace_posture: string
  focus_symbol: string | null
  focused_signal_state: string
  session_lifecycle_state: string
  demo_readiness_status: string
  demo_record_count: number
  review_status: string
  validation_replay_ready: boolean
  validation_run_count: number
  release_readiness_status: string
}

export type AlphaReadinessSnapshot = {
  summary: AlphaReadinessSummary
  gates: AlphaReadinessGateSnapshot[]
  operator_steps: AlphaOperatorStepSnapshot[]
  evidence: AlphaReadinessEvidence
}

