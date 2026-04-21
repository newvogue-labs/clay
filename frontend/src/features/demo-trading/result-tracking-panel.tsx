import type { DemoTradeRecordSnapshot } from '../../types/demo-trading'

type ResultTrackingPanelProps = {
  records: DemoTradeRecordSnapshot[]
  isLoading: boolean
  isActing: boolean
  onMarkResult: (recordId: number, resultProfile: 'win' | 'flat' | 'loss') => void
}

export function ResultTrackingPanel({
  records,
  isLoading,
  isActing,
  onMarkResult,
}: ResultTrackingPanelProps) {
  return (
    <section aria-label="result-tracking-panel">
      <h3>Tracked Demo Results</h3>
      {isLoading ? <p>Loading demo records...</p> : null}
      {!isLoading && records.length === 0 ? <p>No demo records yet.</p> : null}
      {!isLoading
        ? records.map((record) => (
            <article key={record.record_id}>
              <h4>{record.symbol}</h4>
              <p>Operator action: {record.operator_action}</p>
              <p>Outcome: {record.outcome_status}</p>
              <p>Broker status: {record.broker_status ?? 'pending'}</p>
              <p>PnL: {record.pnl_pct ?? 'pending'}</p>
              {record.executed_symbol ? <p>Executed symbol: {record.executed_symbol}</p> : null}
              {record.awaiting_result ? (
                <>
                  <button
                    disabled={isActing}
                    onClick={() => onMarkResult(record.record_id, 'win')}
                    type="button"
                  >
                    Mark Win
                  </button>
                  <button
                    disabled={isActing}
                    onClick={() => onMarkResult(record.record_id, 'flat')}
                    type="button"
                  >
                    Mark Flat
                  </button>
                  <button
                    disabled={isActing}
                    onClick={() => onMarkResult(record.record_id, 'loss')}
                    type="button"
                  >
                    Mark Loss
                  </button>
                </>
              ) : null}
            </article>
          ))
        : null}
    </section>
  )
}
