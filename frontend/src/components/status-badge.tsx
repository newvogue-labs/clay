type StatusBadgeProps = {
  label: string
}

export function StatusBadge({ label }: StatusBadgeProps) {
  const normalized = label.toLowerCase()
  const colorClass =
    normalized === 'fresh' || normalized === 'healthy' || normalized === 'pass' || normalized === 'ready_for_demo'
      ? 'border-clay-success/30 bg-clay-success/12 text-clay-success'
      : normalized === 'warn' || normalized === 'warning' || normalized === 'degraded' || normalized === 'partial_failure'
        ? 'border-clay-warning/30 bg-clay-warning/12 text-clay-warning'
        : normalized === 'fail' || normalized === 'stale' || normalized === 'error' || normalized === 'blocked' || normalized === 'unknown'
          ? 'border-clay-danger/30 bg-clay-danger/12 text-clay-danger'
          : 'border-clay-border bg-clay-bg/55 text-clay-text-muted'

  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] ${colorClass}`}
      data-status={label}
    >
      {label.replaceAll('_', ' ')}
    </span>
  )
}
