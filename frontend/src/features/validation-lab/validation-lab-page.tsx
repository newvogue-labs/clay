import { ActivationReviewPanel } from './activation-review-panel'
import { ValidationActionsPanel } from './validation-actions-panel'
import { ValidationRunsPanel } from './validation-runs-panel'
import { ValidationStateBanner } from './validation-state-banner'
import { useValidationLab } from './use-validation-lab'

export function ValidationLabPage() {
  const validation = useValidationLab()
  const snapshot = validation.snapshot

  return (
    <div aria-label="validation-lab-page" className="screen-page" data-screen="validation-lab">
      <ValidationStateBanner
        summary={snapshot?.summary ?? null}
        isLoading={validation.isLoading}
        error={validation.error}
      />
      <ValidationActionsPanel
        isLoading={validation.isLoading}
        isActing={validation.isActing}
        onRunReplay={(runType) => {
          void validation.runReplay(runType)
        }}
        onReviewStrategyActivation={() => {
          void validation.reviewStrategyActivation()
        }}
        onReviewModelActivation={() => {
          void validation.reviewModelActivation()
        }}
      />
      <ValidationRunsPanel
        runs={snapshot?.runs ?? []}
        isLoading={validation.isLoading}
      />
      <ActivationReviewPanel
        pendingReview={validation.pendingReview}
        reviews={snapshot?.activation_reviews ?? []}
        isLoading={validation.isLoading}
        isActing={validation.isActing}
        onApply={() => {
          void validation.applyActivation()
        }}
      />
    </div>
  )
}
