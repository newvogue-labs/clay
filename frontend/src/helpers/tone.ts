export type Tone = 'success' | 'warning' | 'danger' | 'muted'

export function getOutcomeTone(outcome: string): Tone {
  const n = outcome.toLowerCase()
  if (n === 'matched' || n === 'profitable') return 'success'
  if (n === 'mismatched' || n === 'violation') return 'danger'
  if (n === 'late_matched' || n === 'missed' || n === 'unresolved') return 'warning'
  return 'muted'
}

export function getSeverityTone(severity: string): Tone {
  if (severity === 'critical' || severity === 'error' || severity === 'danger') return 'danger'
  if (severity === 'warning' || severity === 'warn') return 'warning'
  return 'muted'
}

export function getPriorityTone(priority: string): Tone {
  if (priority === 'high') return 'success'
  if (priority === 'medium') return 'warning'
  return 'muted'
}
