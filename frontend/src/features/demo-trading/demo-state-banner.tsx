import type { DemoActiveSessionSnapshot, DemoReadinessSnapshot } from '../../types/demo-trading'

type DemoStateBannerProps = {
  readiness: DemoReadinessSnapshot | null
  activeSession: DemoActiveSessionSnapshot | null
  isLoading: boolean
  error: string | null
}

export function DemoStateBanner({
  readiness,
  activeSession,
  isLoading,
  error,
}: DemoStateBannerProps) {
  return (
    <section aria-label="demo-state-banner">
      <h2>Demo Validation</h2>
      {isLoading ? <p>Loading demo-validation state...</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!isLoading && !error && readiness && activeSession ? (
        <>
          <p>Readiness: {readiness.status}</p>
          <p>{readiness.operator_message}</p>
          <p>Lifecycle: {activeSession.lifecycle_state}</p>
          <p>Current pair: {activeSession.current_pair_symbol ?? 'none'}</p>
        </>
      ) : null}
    </section>
  )
}
