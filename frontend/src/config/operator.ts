export function getOperatorActor(): string {
  const raw = import.meta.env.VITE_CLAY_OPERATOR_NAME
  const v = typeof raw === 'string' ? raw.trim() : ''
  return v || 'operator'
}
