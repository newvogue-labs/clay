import type { ReviewedTradeRecord } from '../../types/session-review'

type ReviewRecordsPanelProps = {
  records: ReviewedTradeRecord[]
  isLoading: boolean
  isActing: boolean
  onCaptureFeedback: (
    recordId: number,
    feedbackLabel: 'useful' | 'noise' | 'needs_follow_up',
  ) => void
}

export function ReviewRecordsPanel({
  records,
  isLoading,
  isActing,
  onCaptureFeedback,
}: ReviewRecordsPanelProps) {
  return (
    <section aria-label="review-records-panel">
      <h3>Reviewed Signals</h3>
      {isLoading ? <p>Loading reviewed records...</p> : null}
      {!isLoading && records.length === 0 ? <p>No records matched the current filters.</p> : null}
      {!isLoading
        ? records.map((record) => (
            <article key={record.record_id}>
              <h4>{record.symbol}</h4>
              <p>Outcome: {record.outcome_status}</p>
              <p>Strategy: {record.strategy_mode}</p>
              <p>Model: {record.model_version}</p>
              <p>Confidence band: {record.confidence_band}</p>
              <p>PnL: {record.pnl_pct ?? 'pending'}</p>
              <button
                disabled={isActing}
                onClick={() => onCaptureFeedback(record.record_id, 'useful')}
                type="button"
              >
                Mark Useful
              </button>
              <button
                disabled={isActing}
                onClick={() => onCaptureFeedback(record.record_id, 'noise')}
                type="button"
              >
                Mark Noise
              </button>
              <button
                disabled={isActing}
                onClick={() => onCaptureFeedback(record.record_id, 'needs_follow_up')}
                type="button"
              >
                Needs Follow-Up
              </button>
            </article>
          ))
        : null}
    </section>
  )
}
