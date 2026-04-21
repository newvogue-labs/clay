import { ReviewAuditPanel } from './review-audit-panel'
import { ReviewFeedbackPanel } from './review-feedback-panel'
import { ReviewFilterPanel } from './review-filter-panel'
import { ReviewRecordsPanel } from './review-records-panel'
import { ReviewStateBanner } from './review-state-banner'
import { useSessionReview } from './use-session-review'

export function SessionReviewPage() {
  const review = useSessionReview()
  const snapshot = review.snapshot

  return (
    <section aria-label="session-review-page">
      <ReviewStateBanner
        summary={snapshot?.summary ?? null}
        isLoading={review.isLoading}
        error={review.error}
      />
      <ReviewFilterPanel
        filterOptions={snapshot?.filter_options ?? null}
        selectedPair={review.filters.pair}
        isLoading={review.isLoading}
        onSelectPair={review.setPair}
      />
      <ReviewRecordsPanel
        records={snapshot?.records ?? []}
        isLoading={review.isLoading}
        isActing={review.isActing}
        onCaptureFeedback={(recordId, feedbackLabel) => {
          void review.captureFeedback(recordId, feedbackLabel)
        }}
      />
      <ReviewFeedbackPanel
        feedback={snapshot?.feedback ?? []}
        isLoading={review.isLoading}
      />
      <ReviewAuditPanel
        audit={snapshot?.audit ?? []}
        aiReviewCards={snapshot?.ai_review_cards ?? []}
        isLoading={review.isLoading}
      />
    </section>
  )
}
