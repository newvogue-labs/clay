import { StatusBadge } from '../../components/status-badge'
import type { ConflictSnapshot, FallbackSnapshot } from '../../types/ai-control'

type ConflictPanelProps = {
  conflicts: ConflictSnapshot[]
  fallback: FallbackSnapshot | null
  isLoading: boolean
}

export function ConflictPanel({
  conflicts,
  fallback,
  isLoading,
}: ConflictPanelProps) {
  return (
    <section>
      <h2>Conflicts and Fallback</h2>
      {isLoading || !fallback ? (
        <p>Loading conflict state...</p>
      ) : (
        <>
          <p>Fallback active: <StatusBadge label={fallback.fallback_active ? 'active' : 'inactive'} /></p>
          <p>Local fallback ready: {fallback.local_fallback_ready ? 'yes' : 'no'}</p>
          <p>{fallback.operator_message}</p>
          <ul>
            {conflicts.length === 0 ? (
              <li>No active AI conflicts.</li>
            ) : (
              conflicts.map((conflict) => (
                <li key={conflict.conflict_id}>
                  <strong>{conflict.title}</strong> <StatusBadge label={conflict.severity} />
                  <div>{conflict.description}</div>
                  <div>Recommended action: {conflict.recommended_action}</div>
                </li>
              ))
            )}
          </ul>
        </>
      )}
    </section>
  )
}
