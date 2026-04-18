import { ActiveSignalsPanel } from './active-signals-panel'
import { FocusedPairHeader } from './focused-pair-header'
import { MonitoringPoolPanel } from './monitoring-pool-panel'
import { NewsSentimentPanel } from './news-sentiment-panel'
import { NoActiveSignalState } from './no-active-signal-state'
import { ReasoningPanel } from './reasoning-panel'
import { RiskPanel } from './risk-panel'
import { SituationMap } from './situation-map'
import { UpdateMetaStrip } from './update-meta-strip'
import { useWorkspace } from './use-workspace'
import { WorkspaceStateBanner } from './workspace-state-banner'

export function TradingWorkspacePage() {
  const workspace = useWorkspace()
  const snapshot = workspace.snapshot

  return (
    <section aria-label="trading-workspace-page">
      <WorkspaceStateBanner
        workspaceState={snapshot?.workspace_state ?? null}
        isLoading={workspace.isLoading}
        error={workspace.error}
      />
      <FocusedPairHeader
        focusPair={snapshot?.focus_pair ?? null}
        workspaceState={snapshot?.workspace_state ?? null}
      />
      <UpdateMetaStrip meta={snapshot?.update_meta ?? null} />
      <div>
        <ActiveSignalsPanel
          signals={snapshot?.signals ?? []}
          selectedSignalId={snapshot?.focus_pair.active_signal_id ?? null}
          isActing={workspace.isActing}
          onSelect={(signalId, symbol) => {
            void workspace.focusSignal(signalId, symbol)
          }}
        />
        <MonitoringPoolPanel
          items={snapshot?.monitoring_pool ?? []}
          isActing={workspace.isActing}
          onSelect={(symbol) => {
            void workspace.focusMonitoringPair(symbol)
          }}
        />
      </div>
      {snapshot?.workspace_state.focused_signal_state === 'absent' ? (
        <NoActiveSignalState />
      ) : (
        <SituationMap situationMap={snapshot?.situation_map ?? null} />
      )}
      <ReasoningPanel reasoning={snapshot?.reasoning ?? null} />
      <RiskPanel risk={snapshot?.risk ?? null} />
      <NewsSentimentPanel
        news={snapshot?.news ?? []}
        sentiment={snapshot?.sentiment ?? []}
      />
    </section>
  )
}
