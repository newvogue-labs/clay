import { StatusBadge } from '../../components/status-badge'
import type { ReviewCardSnapshot } from '../../types/ai-control'

type ReviewCardPanelProps = {
  review: ReviewCardSnapshot | null
  isLoading: boolean
  isActing: boolean
  onApply: () => void
}

export function ReviewCardPanel({
  review,
  isLoading,
  isActing,
  onApply,
}: ReviewCardPanelProps) {
  return (
    <section>
      <h2>Review Card</h2>
      {isLoading ? (
        <p>Loading review flow...</p>
      ) : !review ? (
        <p>No pending review card.</p>
      ) : (
        <>
          <p><StatusBadge label={review.severity} /> {review.summary}</p>
          <p>Current model: {review.current_model_id}</p>
          <p>Proposed model: {review.proposed_model_name}</p>
          <h3>Risks</h3>
          <ul>
            {review.risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
          <h3>Expected Effects</h3>
          <ul>
            {review.expected_effects.map((effect) => (
              <li key={effect}>{effect}</li>
            ))}
          </ul>
          <button
            disabled={isActing || review.blocks_apply}
            onClick={onApply}
            type="button"
          >
            Apply reviewed assignment
          </button>
        </>
      )}
    </section>
  )
}
