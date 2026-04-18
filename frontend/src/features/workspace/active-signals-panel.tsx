import { StatusBadge } from '../../components/status-badge'
import type { WorkspaceSignalSummary } from '../../types/workspace'

type ActiveSignalsPanelProps = {
  signals: WorkspaceSignalSummary[]
  selectedSignalId: string | null
  isActing: boolean
  onSelect: (signalId: string, symbol: string) => void
}

export function ActiveSignalsPanel({
  signals,
  selectedSignalId,
  isActing,
  onSelect,
}: ActiveSignalsPanelProps) {
  return (
    <section>
      <h2>Active Signals</h2>
      {signals.length === 0 ? (
        <p>No actionable signals yet.</p>
      ) : (
        <ul>
          {signals.map((signal) => (
            <li key={signal.signal_id}>
              <button
                data-selected={selectedSignalId === signal.signal_id}
                disabled={isActing}
                onClick={() => {
                  onSelect(signal.signal_id, signal.pair)
                }}
                type="button"
              >
                {signal.pair} · {signal.direction} · <StatusBadge label={signal.state} />
              </button>
              <div>{signal.setup_summary}</div>
              <div>
                Confidence {signal.confidence} · penalty {signal.confidence_penalty} · action{' '}
                <StatusBadge label={signal.response_action} />
              </div>
              <div>Strategy mode: <StatusBadge label={signal.strategy_mode} /></div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
