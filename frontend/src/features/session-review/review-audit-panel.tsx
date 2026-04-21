import type { AIReviewCardSnapshot, NormalizedAuditEventSnapshot } from '../../types/session-review'

type ReviewAuditPanelProps = {
  audit: NormalizedAuditEventSnapshot[]
  aiReviewCards: AIReviewCardSnapshot[]
  isLoading: boolean
}

export function ReviewAuditPanel({
  audit,
  aiReviewCards,
  isLoading,
}: ReviewAuditPanelProps) {
  return (
    <section aria-label="review-audit-panel">
      <h3>Audit and AI Review</h3>
      {isLoading ? <p>Loading audit trail...</p> : null}
      {!isLoading ? (
        <>
          {aiReviewCards.map((card) => (
            <article key={card.card_id}>
              <h4>{card.title}</h4>
              <p>{card.summary}</p>
              <ul>
                {card.recommendations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
          ))}
          {audit.map((event) => (
            <article key={`${event.timestamp}-${event.event_type}`}>
              <h4>{event.event_type}</h4>
              <p>Module: {event.module}</p>
              <p>Severity: {event.severity}</p>
              <p>{event.explanation}</p>
            </article>
          ))}
        </>
      ) : null}
    </section>
  )
}
