import { StatusBadge } from '../../components/status-badge'
import type { RiskSnapshot } from '../../types/workspace'

type RiskPanelProps = {
  risk: RiskSnapshot | null
}

export function RiskPanel({ risk }: RiskPanelProps) {
  if (!risk) {
    return null
  }

  return (
    <section>
      <h2>Risk Assessment</h2>
      <p>Risk posture: <StatusBadge label={risk.risk_posture} /></p>
      <p>Confidence: <StatusBadge label={risk.confidence_label} /></p>
      <p>Confidence penalty: {risk.confidence_penalty}</p>
      <p>Response action: <StatusBadge label={risk.response_action} /></p>
      <p>Strategy mode: <StatusBadge label={risk.strategy_mode} /></p>
      <p>{risk.risk_reward_hint}</p>
      <p>{risk.action_guidance}</p>
      <ul>
        {risk.active_triggers.length === 0 ? (
          <li>No active risk triggers.</li>
        ) : (
          risk.active_triggers.map((trigger) => <li key={trigger}>{trigger}</li>)
        )}
      </ul>
    </section>
  )
}
