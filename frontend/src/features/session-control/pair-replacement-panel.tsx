import { StatusBadge } from '../../components/status-badge'
import type { PairReplacementReviewSnapshot, SessionLifecycleSnapshot } from '../../types/session-control'

type PairReplacementPanelProps = {
  lifecycle: SessionLifecycleSnapshot | null
  replacementReview: PairReplacementReviewSnapshot | null
  isLoading: boolean
  isActing: boolean
  onReview: () => void
  onApply: () => void
}

export function PairReplacementPanel({
  lifecycle,
  replacementReview,
  isLoading,
  isActing,
  onReview,
  onApply,
}: PairReplacementPanelProps) {
  return (
    <section>
      <h2>Pair Replacement</h2>
      {isLoading ? (
        <p>Loading replacement flow...</p>
      ) : (
        <>
          <button
            disabled={isActing || !lifecycle || !['active_session', 'paused'].includes(lifecycle.lifecycle_state)}
            onClick={onReview}
            type="button"
          >
            Review pair replacement
          </button>
          {!replacementReview ? (
            <p>No pending pair replacement review.</p>
          ) : (
            <>
              <p><StatusBadge label={replacementReview.severity} /> {replacementReview.summary}</p>
              <h3>Reasons to switch</h3>
              <ul>
                {replacementReview.reasons_to_switch.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              <h3>Risks</h3>
              <ul>
                {replacementReview.risks.map((risk) => (
                  <li key={risk}>{risk}</li>
                ))}
              </ul>
              <button
                disabled={isActing || replacementReview.blocks_apply}
                onClick={onApply}
                type="button"
              >
                Apply pair replacement
              </button>
            </>
          )}
        </>
      )}
    </section>
  )
}
