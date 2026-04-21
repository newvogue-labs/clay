import type { DemoReadinessSnapshot } from '../../types/demo-trading'

type DemoReadinessPanelProps = {
  readiness: DemoReadinessSnapshot | null
  isLoading: boolean
}

export function DemoReadinessPanel({ readiness, isLoading }: DemoReadinessPanelProps) {
  return (
    <section aria-label="demo-readiness-panel">
      <h3>Readiness Gates</h3>
      {isLoading ? <p>Loading readiness gates...</p> : null}
      {!isLoading && readiness ? (
        <>
          <p>Sessions: {readiness.distinct_session_count}</p>
          <p>Total records: {readiness.total_records}</p>
          <p>Resolved records: {readiness.resolved_record_count}</p>
          <p>Profitable records: {readiness.profitable_record_count}</p>
          <p>Cumulative PnL: {readiness.cumulative_pnl_pct}%</p>
          <p>Matched: {readiness.outcome_counts.matched ?? 0}</p>
          <p>Missed: {readiness.outcome_counts.missed ?? 0}</p>
          <p>Late matched: {readiness.outcome_counts.late_matched ?? 0}</p>
          <p>Mismatched: {readiness.outcome_counts.mismatched ?? 0}</p>
          <p>Unresolved: {readiness.outcome_counts.unresolved ?? 0}</p>
          <ul>
            {readiness.gates.map((gate) => (
              <li key={gate.gate_id}>
                <strong>{gate.label}</strong>: {gate.status} — {gate.detail}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  )
}
