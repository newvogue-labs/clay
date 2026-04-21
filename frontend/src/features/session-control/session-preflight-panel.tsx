import { StatusBadge } from '../../components/status-badge'
import type { SessionPreflightSnapshot } from '../../types/session-control'

type SessionPreflightPanelProps = {
  preflight: SessionPreflightSnapshot | null
  isLoading: boolean
  isActing: boolean
  onStart: () => void
}

export function SessionPreflightPanel({
  preflight,
  isLoading,
  isActing,
  onStart,
}: SessionPreflightPanelProps) {
  return (
    <section>
      <h2>Hard Preflight</h2>
      {isLoading || !preflight ? (
        <p>Loading preflight...</p>
      ) : (
        <>
          <p>Status: <StatusBadge label={preflight.status} /></p>
          {preflight.blocking_reason ? <p>Blocking reason: {preflight.blocking_reason}</p> : null}
          <button
            disabled={isActing || preflight.status !== 'pass'}
            onClick={onStart}
            type="button"
          >
            Start session
          </button>
          <ul>
            {preflight.checks.map((check) => (
              <li key={check.check_id}>
                <strong>{check.label}</strong> <StatusBadge label={check.status} /> - {check.reason}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
