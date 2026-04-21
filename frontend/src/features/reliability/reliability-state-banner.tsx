import type { ReliabilitySummary } from '../../types/reliability'

type ReliabilityStateBannerProps = {
  summary: ReliabilitySummary | null
  isLoading: boolean
  error: string | null
}

export function ReliabilityStateBanner({
  summary,
  isLoading,
  error,
}: ReliabilityStateBannerProps) {
  return (
    <section aria-label="reliability-state-banner">
      <h2>Reliability Center</h2>
      {isLoading ? <p>Loading reliability posture...</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!isLoading && !error && summary ? (
        <>
          <p>Overall status: {summary.overall_status}</p>
          <p>Degraded mode active: {String(summary.degraded_mode_active)}</p>
          <p>Release readiness: {summary.release_readiness_status}</p>
          <p>Blocking gates: {summary.blocking_gate_count}</p>
          <p>Warning gates: {summary.warning_gate_count}</p>
          <p>{summary.operator_message}</p>
        </>
      ) : null}
    </section>
  )
}
