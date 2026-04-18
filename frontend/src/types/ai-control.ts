export type AIOverallStatus = 'healthy' | 'degraded'
export type AssignmentHealth = 'healthy' | 'review_required' | 'degraded'
export type AssignmentMode = 'active' | 'fallback'
export type ReviewSeverity = 'info' | 'warning' | 'critical'

export type AIControlSummary = {
  overall_status: AIOverallStatus
  chief_agent_model: string
  active_conflict_count: number
  degraded_role_count: number
  fallback_active: boolean
  last_reviewed_at: string | null
}

export type RoleDefinitionSnapshot = {
  role_id: string
  role_name: string
  responsibility: string
  inputs: string[]
  outputs: string[]
  allowed_actions: string[]
  constraints: string[]
  explanation_owner: boolean
  synthesis_owner: boolean
}

export type ModelVersionSnapshot = {
  model_id: string
  display_name: string
  provider: string
  source: string
  training_date: string
  metrics_summary: string
  notes: string
  activation_status: string
  compatible_roles: string[]
  fallback_ready: boolean
}

export type AssignmentSnapshot = {
  role_id: string
  role_name: string
  model_id: string
  model_display_name: string
  provider: string
  assignment_mode: AssignmentMode
  assignment_health: AssignmentHealth
  confidence_penalty: number
  review_required: boolean
  reason: string
}

export type ConflictSnapshot = {
  conflict_id: string
  severity: ReviewSeverity
  title: string
  description: string
  affected_roles: string[]
  recommended_action: string
}

export type ReviewCardSnapshot = {
  review_id: string
  role_id: string
  role_name: string
  current_model_id: string
  proposed_model_id: string
  proposed_model_name: string
  severity: ReviewSeverity
  approval_required: boolean
  blocks_apply: boolean
  summary: string
  risks: string[]
  expected_effects: string[]
  resulting_confidence_penalty: number
  resulting_conflicts: ConflictSnapshot[]
}

export type FallbackSnapshot = {
  fallback_active: boolean
  local_fallback_ready: boolean
  degraded_roles: string[]
  operator_message: string
}

export type AIControlSnapshot = {
  summary: AIControlSummary
  roles: RoleDefinitionSnapshot[]
  models: ModelVersionSnapshot[]
  assignments: AssignmentSnapshot[]
  conflicts: ConflictSnapshot[]
  fallback: FallbackSnapshot
  pending_review: ReviewCardSnapshot | null
}
