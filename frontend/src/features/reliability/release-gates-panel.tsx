import type {
  ReliabilityCheckSnapshot,
  ReleaseGateSnapshot,
} from '../../types/reliability'

type ReleaseGatesPanelProps = {
  readinessChecks: ReliabilityCheckSnapshot[]
  releaseGates: ReleaseGateSnapshot[]
  isLoading: boolean
  isActing: boolean
  onRecheck: () => void
}

export function ReleaseGatesPanel({
  readinessChecks,
  releaseGates,
  isLoading,
  isActing,
  onRecheck,
}: ReleaseGatesPanelProps) {
  return (
    <section aria-label="release-gates-panel">
      <h3>Readiness and Release Gates</h3>
      <button disabled={isLoading || isActing} onClick={onRecheck} type="button">
        Recheck Reliability
      </button>
      {isLoading ? <p>Loading readiness checks...</p> : null}
      {!isLoading
        ? readinessChecks.map((check) => (
            <article key={check.check_id}>
              <h4>{check.label}</h4>
              <p>Status: {check.status}</p>
              <p>{check.detail}</p>
            </article>
          ))
        : null}
      {!isLoading
        ? releaseGates.map((gate) => (
            <article key={gate.gate_id}>
              <h4>{gate.label}</h4>
              <p>Status: {gate.status}</p>
              <p>Blocks release: {String(gate.blocks_release)}</p>
              <p>{gate.detail}</p>
            </article>
          ))
        : null}
    </section>
  )
}
