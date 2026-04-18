import { AIControlStateBanner } from './ai-control-state-banner'
import { AssignmentPanel } from './assignment-panel'
import { ConflictPanel } from './conflict-panel'
import { ReviewCardPanel } from './review-card-panel'
import { RolesPanel } from './roles-panel'
import { useAIControl } from './use-ai-control'

export function AIControlPage() {
  const aiControl = useAIControl()
  const snapshot = aiControl.snapshot

  return (
    <section aria-label="ai-control-page">
      <AIControlStateBanner
        summary={snapshot?.summary ?? null}
        isLoading={aiControl.isLoading}
        error={aiControl.error}
      />
      <AssignmentPanel
        assignments={snapshot?.assignments ?? []}
        models={snapshot?.models ?? []}
        isLoading={aiControl.isLoading}
        isActing={aiControl.isActing}
        onReviewAssignment={(roleId, modelId) => {
          void aiControl.reviewAssignment(roleId, modelId)
        }}
      />
      <ConflictPanel
        conflicts={snapshot?.conflicts ?? []}
        fallback={snapshot?.fallback ?? null}
        isLoading={aiControl.isLoading}
      />
      <ReviewCardPanel
        review={aiControl.preview ?? snapshot?.pending_review ?? null}
        isLoading={aiControl.isLoading}
        isActing={aiControl.isActing}
        onApply={() => {
          void aiControl.applyPendingReview()
        }}
      />
      <RolesPanel roles={snapshot?.roles ?? []} isLoading={aiControl.isLoading} />
    </section>
  )
}
