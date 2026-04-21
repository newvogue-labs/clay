import type { SessionLifecycleSnapshot } from '../../types/session-control'

type SessionLifecyclePanelProps = {
  lifecycle: SessionLifecycleSnapshot | null
  isLoading: boolean
  isActing: boolean
  onPause: () => void
  onResume: () => void
  onComplete: () => void
}

export function SessionLifecyclePanel({
  lifecycle,
  isLoading,
  isActing,
  onPause,
  onResume,
  onComplete,
}: SessionLifecyclePanelProps) {
  return (
    <section>
      <h2>Session Lifecycle</h2>
      {isLoading || !lifecycle ? (
        <p>Loading lifecycle...</p>
      ) : (
        <>
          <p>Session ID: {lifecycle.session_id ?? 'not started'}</p>
          <p>Started at: {lifecycle.started_at ?? 'n/a'}</p>
          <p>Paused at: {lifecycle.paused_at ?? 'n/a'}</p>
          <div>
            <button disabled={isActing || !lifecycle.can_pause} onClick={onPause} type="button">
              Pause session
            </button>
            <button disabled={isActing || !lifecycle.can_resume} onClick={onResume} type="button">
              Resume session
            </button>
            <button disabled={isActing || !lifecycle.can_complete} onClick={onComplete} type="button">
              Complete session
            </button>
          </div>
        </>
      )}
    </section>
  )
}
