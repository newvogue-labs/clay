import { DemoReadinessPanel } from './demo-readiness-panel'
import { DemoStateBanner } from './demo-state-banner'
import { ManualDemoActionsPanel } from './manual-demo-actions-panel'
import { ResultTrackingPanel } from './result-tracking-panel'
import { useDemoTrading } from './use-demo-trading'

export function DemoValidationPage() {
  const demoTrading = useDemoTrading()
  const snapshot = demoTrading.snapshot

  return (
    <section aria-label="demo-validation-page">
      <DemoStateBanner
        readiness={snapshot?.readiness ?? null}
        activeSession={snapshot?.active_session ?? null}
        isLoading={demoTrading.isLoading}
        error={demoTrading.error}
      />
      <DemoReadinessPanel
        readiness={snapshot?.readiness ?? null}
        isLoading={demoTrading.isLoading}
      />
      <ManualDemoActionsPanel
        activeSession={snapshot?.active_session ?? null}
        isLoading={demoTrading.isLoading}
        isActing={demoTrading.isActing}
        onLogTrade={(operatorAction) => {
          void demoTrading.logTrade(operatorAction)
        }}
      />
      <ResultTrackingPanel
        records={snapshot?.records ?? []}
        isLoading={demoTrading.isLoading}
        isActing={demoTrading.isActing}
        onMarkResult={(recordId, resultProfile) => {
          void demoTrading.markResult(recordId, resultProfile)
        }}
      />
    </section>
  )
}
