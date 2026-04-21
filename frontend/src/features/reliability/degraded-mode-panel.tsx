import type {
  DegradedTriggerSnapshot,
  LocalFallbackReadinessSnapshot,
} from '../../types/reliability'

type DegradedModePanelProps = {
  triggers: DegradedTriggerSnapshot[]
  fallback: LocalFallbackReadinessSnapshot | null
  isLoading: boolean
}

export function DegradedModePanel({
  triggers,
  fallback,
  isLoading,
}: DegradedModePanelProps) {
  return (
    <section aria-label="degraded-mode-panel">
      <h3>Degraded Mode and Fallback</h3>
      {isLoading ? <p>Loading degraded-mode posture...</p> : null}
      {!isLoading && fallback ? (
        <>
          <p>Fallback active: {String(fallback.fallback_active)}</p>
          <p>Local fallback ready: {String(fallback.local_fallback_ready)}</p>
          <p>Degraded roles: {fallback.degraded_roles.join(', ') || 'none'}</p>
          <p>{fallback.operator_message}</p>
        </>
      ) : null}
      {!isLoading && triggers.length === 0 ? <p>No degraded triggers are active.</p> : null}
      {!isLoading
        ? triggers.map((trigger) => (
            <article key={trigger.trigger_id}>
              <h4>{trigger.title}</h4>
              <p>Severity: {trigger.severity}</p>
              <p>{trigger.description}</p>
              <p>Action: {trigger.recommended_action}</p>
            </article>
          ))
        : null}
    </section>
  )
}
