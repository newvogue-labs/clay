import { StatusBadge } from '../../components/status-badge'
import type { SessionLifecycleSnapshot } from '../../types/session-control'

type SessionStateBannerProps = {
  lifecycle: SessionLifecycleSnapshot | null
  isLoading: boolean
  error: string | null
}

export function SessionStateBanner({
  lifecycle,
  isLoading,
  error,
}: SessionStateBannerProps) {
  if (isLoading) {
    return <section aria-label="session state">Loading session control...</section>
  }

  if (error) {
    return <section aria-label="session state">Session control error: {error}</section>
  }

  if (!lifecycle) {
    return <section aria-label="session state">No session snapshot available.</section>
  }

  return (
    <section aria-label="session state">
      <h2>Session Control</h2>
      <p>Lifecycle: <StatusBadge label={lifecycle.lifecycle_state} /></p>
      <p>Runtime: <StatusBadge label={lifecycle.runtime_state} /></p>
      {lifecycle.current_pair_symbol ? <p>Current pair: {lifecycle.current_pair_symbol}</p> : null}
    </section>
  )
}
