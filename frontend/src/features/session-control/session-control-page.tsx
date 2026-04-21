import { PairReplacementPanel } from './pair-replacement-panel'
import { SessionBriefingPanel } from './session-briefing-panel'
import { SessionLifecyclePanel } from './session-lifecycle-panel'
import { SessionPreflightPanel } from './session-preflight-panel'
import { SessionStateBanner } from './session-state-banner'
import { useSessionControl } from './use-session-control'

export function SessionControlPage() {
  const sessionControl = useSessionControl()
  const snapshot = sessionControl.snapshot

  return (
    <section aria-label="session-control-page">
      <SessionStateBanner
        lifecycle={snapshot?.lifecycle ?? null}
        isLoading={sessionControl.isLoading}
        error={sessionControl.error}
      />
      <SessionPreflightPanel
        preflight={snapshot?.preflight ?? null}
        isLoading={sessionControl.isLoading}
        isActing={sessionControl.isActing}
        onStart={() => {
          void sessionControl.startSession()
        }}
      />
      <SessionBriefingPanel
        briefing={snapshot?.briefing ?? null}
        isLoading={sessionControl.isLoading}
      />
      <SessionLifecyclePanel
        lifecycle={snapshot?.lifecycle ?? null}
        isLoading={sessionControl.isLoading}
        isActing={sessionControl.isActing}
        onPause={() => {
          void sessionControl.pauseSession()
        }}
        onResume={() => {
          void sessionControl.resumeSession()
        }}
        onComplete={() => {
          void sessionControl.completeSession()
        }}
      />
      <PairReplacementPanel
        lifecycle={snapshot?.lifecycle ?? null}
        replacementReview={sessionControl.replacementReview ?? snapshot?.pending_pair_replacement ?? null}
        isLoading={sessionControl.isLoading}
        isActing={sessionControl.isActing}
        onReview={() => {
          void sessionControl.reviewReplacement()
        }}
        onApply={() => {
          void sessionControl.applyReplacement()
        }}
      />
    </section>
  )
}
