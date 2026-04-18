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
      <p>{risk.risk_reward_hint}</p>
      <p>{risk.action_guidance}</p>
    </section>
  )
}
