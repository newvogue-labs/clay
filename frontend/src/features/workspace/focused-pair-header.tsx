import type { FocusPairSnapshot, WorkspaceStateSnapshot } from '../../types/workspace'

type FocusedPairHeaderProps = {
  focusPair: FocusPairSnapshot | null
  workspaceState: WorkspaceStateSnapshot | null
}

function buildBinanceUrl(symbol: string): string {
  if (!symbol.endsWith('USDT')) {
    return 'https://www.binance.com/en/trade'
  }
  const base = symbol.slice(0, -4)
  return `https://www.binance.com/en/trade/${base}_USDT`
}

export function FocusedPairHeader({
  focusPair,
  workspaceState,
}: FocusedPairHeaderProps) {
  if (!focusPair) {
    return <section><h2>Focused Pair</h2><p>No focused pair yet.</p></section>
  }

  return (
    <section>
      <h2>Focused Pair</h2>
      <p><strong>{focusPair.display_name}</strong></p>
      <p>Last price: {focusPair.last_price}</p>
      <p>24h change: {focusPair.pct_change_24h}%</p>
      <p>Volatility: {focusPair.volatility}</p>
      <p>Focus source: {focusPair.focus_source}</p>
<p>Role: {focusPair.role}</p>
{workspaceState?.monitored_data_health === 'degraded' ? (
  <p role="status">
    ⚠️ Часть пар вне фокуса несвежие — гейтинг ведём по фокусной паре.
  </p>
) : null}
{workspaceState?.can_open_binance ? (
        <p>
          <a href={buildBinanceUrl(focusPair.symbol)} rel="noreferrer" target="_blank">
            Open in Binance
          </a>
        </p>
      ) : null}
    </section>
  )
}
