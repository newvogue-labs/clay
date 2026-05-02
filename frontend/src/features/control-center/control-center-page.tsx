import { ActiveConfigurationPanel } from './active-configuration-panel'
import { AlertsAuditPanel } from './alerts-audit-panel'
import { ControlCenterStateBanner } from './state-banner'
import { ManagedServicesPanel } from './managed-services-panel'
import { RuntimeStatusPanel } from './runtime-status-panel'
import { SystemHealthPanel } from './system-health-panel'
import { useControlCenter } from './use-control-center'

export function ControlCenterPage() {
  const controlCenter = useControlCenter()
  const snapshot = controlCenter.snapshot

  return (
    <div aria-label="control-center-page" className="screen-page" data-screen="control-center">
      <ControlCenterStateBanner
        summary={snapshot?.summary ?? null}
        isLoading={controlCenter.isLoading}
        error={controlCenter.error}
      />
      <SystemHealthPanel
        ingestion={snapshot?.ingestion ?? null}
        isLoading={controlCenter.isLoading}
        isActing={controlCenter.isActing}
        onRunIngestion={() => {
          void controlCenter.runIngestionCycle()
        }}
      />
      <RuntimeStatusPanel
        runtime={snapshot?.runtime ?? null}
        isLoading={controlCenter.isLoading}
        isActing={controlCenter.isActing}
        onTransition={(target) => {
          void controlCenter.transitionRuntime(target)
        }}
      />
      <ManagedServicesPanel
        services={snapshot?.services ?? []}
        isLoading={controlCenter.isLoading}
        isActing={controlCenter.isActing}
        onAction={(serviceId, action) => {
          void controlCenter.runServiceAction(serviceId, action)
        }}
      />
      <AlertsAuditPanel
        incidents={snapshot?.incidents ?? []}
        audit={snapshot?.audit ?? []}
        isLoading={controlCenter.isLoading}
      />
      <ActiveConfigurationPanel
        config={snapshot?.config ?? null}
        isLoading={controlCenter.isLoading}
        isActing={controlCenter.isActing}
        onRestore={(scope) => {
          void controlCenter.restoreConfig(scope)
        }}
      />
    </div>
  )
}
