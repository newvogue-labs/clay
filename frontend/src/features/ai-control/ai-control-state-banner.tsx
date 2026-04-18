import { StatusBadge } from '../../components/status-badge'
import type { AIControlSummary } from '../../types/ai-control'

type AIControlStateBannerProps = {
  summary: AIControlSummary | null
  isLoading: boolean
  error: string | null
}

export function AIControlStateBanner({
  summary,
  isLoading,
  error,
}: AIControlStateBannerProps) {
  if (isLoading) {
    return <section aria-label="ai control state">Loading AI control...</section>
  }

  if (error) {
    return <section aria-label="ai control state">AI control error: {error}</section>
  }

  if (!summary) {
    return <section aria-label="ai control state">No AI control snapshot available.</section>
  }

  return (
    <section aria-label="ai control state">
      <h2>AI Control</h2>
      <p>Overall status: <StatusBadge label={summary.overall_status} /></p>
      <p>Chief Agent model: {summary.chief_agent_model}</p>
      <p>Active conflicts: {summary.active_conflict_count}</p>
      <p>Degraded roles: {summary.degraded_role_count}</p>
      <p>Fallback active: {summary.fallback_active ? 'yes' : 'no'}</p>
    </section>
  )
}
