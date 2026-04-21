import type { SessionBriefingSnapshot } from '../../types/session-control'

type SessionBriefingPanelProps = {
  briefing: SessionBriefingSnapshot | null
  isLoading: boolean
}

export function SessionBriefingPanel({
  briefing,
  isLoading,
}: SessionBriefingPanelProps) {
  return (
    <section>
      <h2>Pre-Session Briefing</h2>
      {isLoading || !briefing ? (
        <p>Loading briefing...</p>
      ) : (
        <>
          <p>{briefing.market_context}</p>
          <p>{briefing.sentiment_summary}</p>
          <p>Active strategy: {briefing.active_strategy}</p>
          <p>{briefing.ai_summary}</p>
          <h3>Shortlist</h3>
          <ul>
            {briefing.shortlist.map((signal) => (
              <li key={signal.signal_id}>
                {signal.symbol} · {signal.direction} · {signal.state} · {signal.setup_summary}
              </li>
            ))}
          </ul>
          <h3>Risk Alerts</h3>
          <ul>
            {briefing.risk_alerts.map((alert) => (
              <li key={alert}>{alert}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
