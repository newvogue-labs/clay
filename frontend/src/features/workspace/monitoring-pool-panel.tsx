import { StatusBadge } from '../../components/status-badge'
import type { MonitoringPoolItem } from '../../types/workspace'

type MonitoringPoolPanelProps = {
  items: MonitoringPoolItem[]
  isActing: boolean
  onSelect: (symbol: string) => void
}

export function MonitoringPoolPanel({
  items,
  isActing,
  onSelect,
}: MonitoringPoolPanelProps) {
  return (
    <section>
      <h2>Monitoring Pool</h2>
      <ul>
        {items.map((item) => (
          <li key={item.symbol}>
            <button
              data-focused={item.is_focused}
              disabled={isActing}
              onClick={() => {
                onSelect(item.symbol)
              }}
              type="button"
            >
              {item.symbol} · {item.role} · <StatusBadge label={item.availability_status} />
            </button>
            <div>
              Price {item.last_price} · 24h {item.pct_change_24h}% · active signal {item.has_active_signal ? 'yes' : 'no'}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
