import type { FeedbackItemSnapshot } from '../../types/session-review'

type ReviewFeedbackPanelProps = {
  feedback: FeedbackItemSnapshot[]
  isLoading: boolean
}

export function ReviewFeedbackPanel({ feedback, isLoading }: ReviewFeedbackPanelProps) {
  return (
    <section aria-label="review-feedback-panel">
      <h3>Captured Feedback</h3>
      {isLoading ? <p>Loading feedback history...</p> : null}
      {!isLoading && feedback.length === 0 ? <p>No feedback captured yet.</p> : null}
      {!isLoading
        ? feedback.map((item) => (
            <article key={item.feedback_id}>
              <h4>{item.symbol}</h4>
              <p>Label: {item.feedback_label}</p>
              <p>Outcome: {item.outcome_status ?? 'n/a'}</p>
              <p>Notes: {item.notes ?? 'none'}</p>
            </article>
          ))
        : null}
    </section>
  )
}
