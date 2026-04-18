import type { ReasoningSnapshot } from '../../types/workspace'

type ReasoningPanelProps = {
  reasoning: ReasoningSnapshot | null
}

export function ReasoningPanel({ reasoning }: ReasoningPanelProps) {
  if (!reasoning) {
    return null
  }

  return (
    <section>
      <h2>AI Reasoning</h2>
      <p>{reasoning.thesis}</p>
      <h3>Technical Context</h3>
      <ul>
        {reasoning.technical_context.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <h3>Execution Notes</h3>
      <ul>
        {reasoning.execution_notes.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  )
}
