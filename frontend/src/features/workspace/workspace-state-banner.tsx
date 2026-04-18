import { StatusBadge } from '../../components/status-badge'
import type { WorkspaceStateSnapshot } from '../../types/workspace'

type WorkspaceStateBannerProps = {
  workspaceState: WorkspaceStateSnapshot | null
  isLoading: boolean
  error: string | null
}

export function WorkspaceStateBanner({
  workspaceState,
  isLoading,
  error,
}: WorkspaceStateBannerProps) {
  if (isLoading) {
    return <section aria-label="workspace-state">Loading workspace...</section>
  }

  if (error) {
    return <section aria-label="workspace-state">Workspace error: {error}</section>
  }

  if (!workspaceState) {
    return <section aria-label="workspace-state">No workspace snapshot available.</section>
  }

  return (
    <section aria-label="workspace-state">
      <h2>Trading Workspace</h2>
      <p>Runtime: <StatusBadge label={workspaceState.runtime_state} /></p>
      <p>Workspace posture: <StatusBadge label={workspaceState.workspace_posture} /></p>
      <p>Focused signal state: <StatusBadge label={workspaceState.focused_signal_state} /></p>
      {workspaceState.blocking_reason ? <p>Blocking reason: {workspaceState.blocking_reason}</p> : null}
    </section>
  )
}
