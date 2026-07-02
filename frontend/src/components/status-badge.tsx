type StatusBadgeProps = {
  label: string
  tone?: 'success' | 'warning' | 'danger' | 'muted'
}

const successStatuses = new Set(['fresh', 'healthy', 'pass', 'ready_for_demo', 'operator_path_ready'])
const warningStatuses = new Set([
  'warn',
  'warning',
  'degraded',
  'partial_failure',
  'needs_attention',
  'operator_attention',
])
const dangerStatuses = new Set(['fail', 'stale', 'error', 'blocked', 'unknown'])

const toneClass: Record<NonNullable<StatusBadgeProps['tone']>, string> = {
  success: 'border-clay-success/30 bg-clay-success/12 text-clay-success',
  warning: 'border-clay-warning/30 bg-clay-warning/12 text-clay-warning',
  danger: 'border-clay-danger/30 bg-clay-danger/12 text-clay-danger',
  muted: 'border-clay-border bg-clay-bg/55 text-clay-text-muted',
}

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  const normalized = label.toLowerCase()
  const colorClass = tone
    ? toneClass[tone]
    : successStatuses.has(normalized)
      ? toneClass.success
      : warningStatuses.has(normalized)
        ? toneClass.warning
        : dangerStatuses.has(normalized)
          ? toneClass.danger
          : toneClass.muted

  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] ${colorClass}`}
      data-status={label}
    >
      {label.replaceAll('_', ' ')}
    </span>
  )
}
