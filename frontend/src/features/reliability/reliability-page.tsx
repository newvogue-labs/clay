import { DegradedModePanel } from './degraded-mode-panel'
import { ReleaseGatesPanel } from './release-gates-panel'
import { ReliabilityIncidentsPanel } from './reliability-incidents-panel'
import { ReliabilityStateBanner } from './reliability-state-banner'
import { useReliability } from './use-reliability'

export function ReliabilityPage() {
  const reliability = useReliability()
  const snapshot = reliability.snapshot

  return (
    <section aria-label="reliability-page">
      <ReliabilityStateBanner
        summary={snapshot?.summary ?? null}
        isLoading={reliability.isLoading}
        error={reliability.error}
      />
      <DegradedModePanel
        triggers={snapshot?.degraded_triggers ?? []}
        fallback={snapshot?.fallback ?? null}
        isLoading={reliability.isLoading}
      />
      <ReleaseGatesPanel
        readinessChecks={snapshot?.readiness_checks ?? []}
        releaseGates={snapshot?.release_gates ?? []}
        isLoading={reliability.isLoading}
        isActing={reliability.isActing}
        onRecheck={() => {
          void reliability.recheck()
        }}
      />
      <ReliabilityIncidentsPanel
        incidents={snapshot?.incidents ?? []}
        isLoading={reliability.isLoading}
      />
    </section>
  )
}
