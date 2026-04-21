import type { SessionReviewSummary } from '../../types/session-review'

type ReviewStateBannerProps = {
  summary: SessionReviewSummary | null
  isLoading: boolean
  error: string | null
}

export function ReviewStateBanner({ summary, isLoading, error }: ReviewStateBannerProps) {
  return (
    <section aria-label="review-state-banner">
      <h2>Session Review</h2>
      {isLoading ? <p>Loading session review...</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!isLoading && !error && summary ? (
        <>
          <p>Status: {summary.review_status}</p>
          <p>{summary.operator_message}</p>
          <p>Total demo records: {summary.total_demo_records}</p>
          <p>Cumulative PnL: {summary.cumulative_pnl_pct}%</p>
          <p>Feedback count: {summary.feedback_count}</p>
        </>
      ) : null}
    </section>
  )
}
