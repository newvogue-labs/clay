import type { DemoActiveSessionSnapshot, DemoTradeRecordSnapshot } from '../../types/demo-trading'

type ManualDemoActionsPanelProps = {
  activeSession: DemoActiveSessionSnapshot | null
  isLoading: boolean
  isActing: boolean
  onLogTrade: (operatorAction: DemoTradeRecordSnapshot['operator_action']) => void
}

export function ManualDemoActionsPanel({
  activeSession,
  isLoading,
  isActing,
  onLogTrade,
}: ManualDemoActionsPanelProps) {
  const disabled = isLoading || isActing || !activeSession?.can_log_decision

  return (
    <section aria-label="manual-demo-actions-panel">
      <h3>Manual Demo Actions</h3>
      {isLoading ? <p>Loading action surface...</p> : null}
      {!isLoading && activeSession ? (
        <>
          <p>Session id: {activeSession.session_id ?? 'none'}</p>
          <p>Signal id: {activeSession.current_signal_id ?? 'none'}</p>
          {activeSession.blocking_reason ? <p>{activeSession.blocking_reason}</p> : null}
          <button disabled={disabled} onClick={() => onLogTrade('entered')} type="button">
            Log Entered Trade
          </button>
          <button disabled={disabled} onClick={() => onLogTrade('skipped')} type="button">
            Log Skipped Trade
          </button>
          <button disabled={disabled} onClick={() => onLogTrade('off_signal')} type="button">
            Log Off-Signal Trade
          </button>
          <button disabled={disabled} onClick={() => onLogTrade('entered_late')} type="button">
            Log Late Entry
          </button>
        </>
      ) : null}
    </section>
  )
}
