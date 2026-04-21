export type ReliabilitySummary = {
  overall_status: 'healthy' | 'degraded'
  degraded_mode_active: boolean
  release_readiness_status: 'blocked' | 'needs_attention' | 'ready_for_demo'
  blocking_gate_count: number
  warning_gate_count: number
  operator_message: string
  last_evaluated_at: string
}

export type DegradedTriggerSnapshot = {
  trigger_id: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  description: string
  recommended_action: string
}

export type LocalFallbackReadinessSnapshot = {
  fallback_active: boolean
  local_fallback_ready: boolean
  degraded_roles: string[]
  operator_message: string
}

export type ReliabilityCheckSnapshot = {
  check_id: string
  label: string
  status: 'pass' | 'warn' | 'fail'
  detail: string
}

export type ReleaseGateSnapshot = {
  gate_id: string
  label: string
  status: 'pass' | 'warn' | 'fail'
  detail: string
  blocks_release: boolean
}

export type ReliabilityIncidentSnapshot = {
  source_name: string
  severity: string
  message: string
  recorded_at: string
}

export type ReliabilitySnapshot = {
  summary: ReliabilitySummary
  degraded_triggers: DegradedTriggerSnapshot[]
  fallback: LocalFallbackReadinessSnapshot
  readiness_checks: ReliabilityCheckSnapshot[]
  release_gates: ReleaseGateSnapshot[]
  incidents: ReliabilityIncidentSnapshot[]
}
