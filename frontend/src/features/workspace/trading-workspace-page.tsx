import { useMemo } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  Brain,
  Clock3,
  Eye,
  Newspaper,
  Radar,
  ShieldAlert,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import type {
  FocusPairSnapshot,
  MonitoringPoolItem,
  NewsContextItem,
  RiskSnapshot,
  SentimentContextItem,
  SituationMapSnapshot,
  WorkspaceSignalSummary,
  WorkspaceSnapshot,
  WorkspaceStateSnapshot,
} from '../../types/workspace'
import { useWorkspace } from './use-workspace'
import { formatMMSS, useOverrideCountdown } from './use-override-countdown'

function buildBinanceUrl(symbol: string): string {
  if (!symbol.endsWith('USDT')) {
    return 'https://www.binance.com/en/trade'
  }
  const base = symbol.slice(0, -4)
  return `https://www.binance.com/en/trade/${base}_USDT`
}

function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '--'
  }
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: value > 1000 ? 0 : 2,
  }).format(value)
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '--'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatTime(value: string | null | undefined): string {
  if (!value) {
    return '--:--:--'
  }
  return new Date(value).toLocaleTimeString('en-GB', { hour12: false })
}

function isBullish(signal: WorkspaceSignalSummary | null): boolean {
  return Boolean(signal?.direction.toLowerCase().match(/long|bull/))
}

function pickSelectedSignal(snapshot: WorkspaceSnapshot | null): WorkspaceSignalSummary | null {
  if (!snapshot) {
    return null
  }
  return (
    snapshot.signals.find((signal) => signal.signal_id === snapshot.focus_pair.active_signal_id) ??
    snapshot.signals[0] ??
    null
  )
}

export function TradingWorkspacePage() {
  const { snapshot, isLoading, error, refetch, isActing, focusSignal, focusMonitoringPair } = useWorkspace()
  const selectedSignal = pickSelectedSignal(snapshot)
  const focusPair = snapshot?.focus_pair ?? null
  const workspaceState = snapshot?.workspace_state ?? null
  const directionIsBullish = isBullish(selectedSignal)
  const hasActiveSignal = workspaceState?.focused_signal_state !== 'absent' && selectedSignal !== null

  const serverOffsetMs = useMemo(
    () =>
      workspaceState?.server_time
        ? Date.parse(workspaceState.server_time) - Date.now()
        : 0,
    [workspaceState?.server_time],
  )
  const isOverrideActive = workspaceState?.execution_override_state === 'confirmed'
  const overrideRemaining = useOverrideCountdown(
    isOverrideActive ? workspaceState?.execution_override_expires_at ?? null : null,
    serverOffsetMs,
    refetch,
  )

  return (
    <div aria-label="trading-workspace-page" className="screen-page workspace-terminal-page" data-screen="workspace">
      <header className="screen-page-header workspace-command-header">
        <div>
          <h2>Trading Workspace</h2>
          <p>Focused pair, active signals, risk posture, and live context</p>
        </div>
        <div className="workspace-command-strip">
          <StatusBadge label={workspaceState?.runtime_state ?? (isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={workspaceState?.workspace_posture ?? 'monitoring'} />
          {isOverrideActive && (
            <StatusBadge
              label={
                overrideRemaining !== null && overrideRemaining > 0
                  ? `OVERRIDE · ${formatMMSS(overrideRemaining)}`
                  : 'OVERRIDE'
              }
            />
          )}
          <span>Update {formatTime(snapshot?.update_meta.focus_last_updated_at)}</span>
        </div>
      </header>

      {error ? (
        <section className="workspace-alert-panel">
          <AlertTriangle className="h-4 w-4 text-clay-danger" />
          <span>Workspace error: {error}</span>
        </section>
      ) : null}

      <div className="workspace-terminal-grid">
        <aside className="workspace-left-rail">
          <ActiveSignalsRail
            isActing={isActing}
            onSelect={(signalId, symbol) => {
              void focusSignal(signalId, symbol)
            }}
            selectedSignalId={snapshot?.focus_pair.active_signal_id ?? null}
            signals={snapshot?.signals ?? []}
          />
          <MonitoringRail
            isActing={isActing}
            items={snapshot?.monitoring_pool ?? []}
            onSelect={(symbol) => {
              void focusMonitoringPair(symbol)
            }}
          />
        </aside>

        <main className="workspace-map-stack">
          <FocusedPairConsole
            focusPair={focusPair}
            selectedSignal={selectedSignal}
            workspaceState={workspaceState}
          />
          {hasActiveSignal ? (
            <SituationConsole
              focusPair={focusPair}
              isBullish={directionIsBullish}
              signal={selectedSignal}
              situationMap={snapshot?.situation_map ?? null}
            />
          ) : (
            <NoSignalConsole focusPair={focusPair} />
          )}
          <ReasoningConsole snapshot={snapshot} />
        </main>

        <aside className="workspace-intel-stack">
          <RiskConsole risk={snapshot?.risk ?? null} />
          <NewsSentimentConsole
            news={snapshot?.news ?? []}
            sentiment={snapshot?.sentiment ?? []}
          />
          <UpdateConsole snapshot={snapshot} />
        </aside>
      </div>
    </div>
  )
}

type ActiveSignalsRailProps = {
  signals: WorkspaceSignalSummary[]
  selectedSignalId: string | null
  isActing: boolean
  onSelect: (signalId: string, symbol: string) => void
}

function ActiveSignalsRail({
  signals,
  selectedSignalId,
  isActing,
  onSelect,
}: ActiveSignalsRailProps) {
  return (
    <section className="workspace-rail-panel workspace-signals-rail">
      <div className="workspace-panel-title">
        <div>
          <h2>Active Signals</h2>
          <span>{signals.filter((signal) => signal.state === 'active').length} active / {signals.length} tracked</span>
        </div>
        <Target className="h-4 w-4 text-clay-accent" />
      </div>

      <div className="workspace-rail-list">
        {signals.length === 0 ? (
          <div className="workspace-empty-line">No actionable signals yet.</div>
        ) : (
          signals.map((signal) => {
            const bullish = isBullish(signal)
            const selected = selectedSignalId === signal.signal_id
            return (
              <button
                className={`workspace-signal-card ${selected ? 'is-selected' : ''}`}
                data-selected={selected}
                disabled={isActing}
                key={signal.signal_id}
                onClick={() => {
                  onSelect(signal.signal_id, signal.pair)
                }}
                type="button"
              >
                <span className="workspace-signal-card-top">
                  <span>
                    <strong>{signal.pair}</strong>
                    <em>{signal.strategy_mode} / penalty {signal.confidence_penalty.toFixed(2)}</em>
                  </span>
                  <span className={bullish ? 'text-clay-success' : 'text-clay-danger'}>
                    {bullish ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                  </span>
                </span>
                <span className="workspace-signal-summary">{signal.setup_summary}</span>
                <span className="workspace-signal-card-bottom">
                  <span className="workspace-confidence-track">
                    <span style={{ width: `${Math.round(signal.confidence * 100)}%` }} />
                  </span>
                  <span>{Math.round(signal.confidence * 100)}%</span>
                  <StatusBadge label={signal.state} />
                </span>
              </button>
            )
          })
        )}
      </div>
    </section>
  )
}

type MonitoringRailProps = {
  items: MonitoringPoolItem[]
  isActing: boolean
  onSelect: (symbol: string) => void
}

function MonitoringRail({ items, isActing, onSelect }: MonitoringRailProps) {
  return (
    <section className="workspace-rail-panel workspace-monitoring-rail">
      <div className="workspace-panel-title">
        <div>
          <h2>Monitoring Pool</h2>
          <span>{items.length} pairs scanned</span>
        </div>
        <Eye className="h-4 w-4 text-clay-muted" />
      </div>

      <div className="workspace-rail-list">
        {items.length === 0 ? (
          <div className="workspace-empty-line">Monitoring pool waiting for market data.</div>
        ) : (
          items.map((item) => (
            <button
              className={`workspace-monitor-row ${item.is_focused ? 'is-focused' : ''}`}
              data-focused={item.is_focused}
              disabled={isActing}
              key={item.symbol}
              onClick={() => {
                onSelect(item.symbol)
              }}
              type="button"
            >
              <span>
                <strong>{item.symbol}</strong>
                <em>{item.role}</em>
              </span>
              <span>
                <strong>{formatPrice(item.last_price)}</strong>
                <em className={item.pct_change_24h >= 0 ? 'text-clay-success' : 'text-clay-danger'}>
                  {formatPct(item.pct_change_24h)}
                </em>
              </span>
              <StatusBadge label={item.availability_status} />
            </button>
          ))
        )}
      </div>
    </section>
  )
}

type FocusedPairConsoleProps = {
  focusPair: FocusPairSnapshot | null
  selectedSignal: WorkspaceSignalSummary | null
  workspaceState: WorkspaceStateSnapshot | null
}

function FocusedPairConsole({
  focusPair,
  selectedSignal,
  workspaceState,
}: FocusedPairConsoleProps) {
  return (
    <section className="workspace-focus-console">
      <div>
        <h2>Focused Pair</h2>
        <p>{focusPair?.display_name ?? 'No focused pair yet.'}</p>
      </div>
      <div className="workspace-focus-stats">
        <span>
          <em>Last Price</em>
          <strong>{formatPrice(focusPair?.last_price)}</strong>
        </span>
        <span>
          <em>24h Change</em>
          <strong className={(focusPair?.pct_change_24h ?? 0) >= 0 ? 'text-clay-success' : 'text-clay-danger'}>
            {formatPct(focusPair?.pct_change_24h)}
          </strong>
        </span>
        <span>
          <em>Volatility</em>
          <strong>{focusPair?.volatility ?? '--'}</strong>
        </span>
        <span>
          <em>Signal State</em>
          <StatusBadge label={workspaceState?.focused_signal_state ?? selectedSignal?.state ?? 'absent'} />
        </span>
      </div>
      {workspaceState?.can_open_binance && focusPair ? (
        <a className="workspace-exchange-link" href={buildBinanceUrl(focusPair.symbol)} rel="noreferrer" target="_blank">
          Open in Binance <ArrowUpRight className="h-3.5 w-3.5" />
        </a>
      ) : null}
    </section>
  )
}

type SituationConsoleProps = {
  focusPair: FocusPairSnapshot | null
  signal: WorkspaceSignalSummary | null
  situationMap: SituationMapSnapshot | null
  isBullish: boolean
}

function SituationConsole({
  focusPair,
  signal,
  situationMap,
  isBullish,
}: SituationConsoleProps) {
  return (
    <section className="workspace-situation-console">
      <div className="workspace-map-grid" />
      <div className="workspace-map-header">
        <h2>Situation Map</h2>
        <p>{focusPair?.symbol ?? signal?.pair ?? 'No pair'} / {situationMap?.directional_bias ?? signal?.direction ?? 'monitoring'}</p>
      </div>

      <svg aria-hidden="true" className="workspace-trajectory" viewBox="0 0 1000 420" preserveAspectRatio="none">
        <path
          className="workspace-current-path"
          d={isBullish ? 'M0 305 L80 295 L150 310 L230 280 L310 290' : 'M0 120 L80 135 L150 128 L230 155 L310 145'}
        />
        <path
          className={isBullish ? 'workspace-forecast-path is-bullish' : 'workspace-forecast-path is-bearish'}
          d={isBullish ? 'M310 290 C430 260 480 220 590 210 S780 155 1000 95' : 'M310 145 C430 165 480 210 590 225 S780 275 1000 335'}
        />
      </svg>

      <div className="workspace-level is-target" style={{ top: isBullish ? '18%' : '78%' }}>
        <span>Target</span>
        <strong>{situationMap?.target_hint ?? 'Waiting for target evidence'}</strong>
      </div>
      <div className="workspace-level is-entry" style={{ top: isBullish ? '56%' : '38%' }}>
        <span>Entry Zone</span>
        <strong>{situationMap?.entry_hint ?? 'No entry zone available'}</strong>
      </div>
      <div className="workspace-level is-stop" style={{ top: isBullish ? '84%' : '16%' }}>
        <span>Invalidation</span>
        <strong>{situationMap?.invalidation_hint ?? 'No invalidation level available'}</strong>
      </div>

      <div className="workspace-map-note">
        <Radar className="h-4 w-4 text-clay-accent" />
        <span>{situationMap?.analyst_note ?? signal?.setup_summary ?? 'Situation map waiting for signal context.'}</span>
      </div>
    </section>
  )
}

function NoSignalConsole({ focusPair }: { focusPair: FocusPairSnapshot | null }) {
  return (
    <section className="workspace-situation-console workspace-no-signal-console">
      <div className="workspace-map-grid" />
      <div className="workspace-map-header">
        <h2>No Active Signal</h2>
        <p>{focusPair?.symbol ?? 'Focused pair'} / monitoring mode</p>
      </div>
      <div className="workspace-scanner-line" />
      <div className="workspace-no-signal-core">
        <Activity className="h-10 w-10 text-clay-accent/60" />
        <strong>Awaiting Signal Trigger</strong>
        <span>The focused pair is in monitoring mode. Keep watching context and wait for a cleaner setup.</span>
      </div>
    </section>
  )
}

function ReasoningConsole({ snapshot }: { snapshot: WorkspaceSnapshot | null }) {
  const reasoning = snapshot?.reasoning ?? null
  return (
    <section className="workspace-reasoning-console">
      <div className="workspace-panel-title">
        <div>
          <h2>AI Reasoning</h2>
          <span>Thesis and execution context</span>
        </div>
        <Brain className="h-4 w-4 text-clay-accent" />
      </div>
      <p>{reasoning?.thesis ?? 'Workspace reasoning is loading from the backend.'}</p>
      <div className="workspace-reasoning-grid">
        <ReasoningList title="Technical Context" items={reasoning?.technical_context ?? []} />
        <ReasoningList title="Execution Notes" items={reasoning?.execution_notes ?? []} />
      </div>
    </section>
  )
}

function ReasoningList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <span className="workspace-muted-line">Waiting for context.</span>
      ) : (
        <ul>
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </div>
  )
}

function RiskConsole({ risk }: { risk: RiskSnapshot | null }) {
  return (
    <section className="workspace-intel-panel">
      <div className="workspace-panel-title">
        <div>
          <h2>Risk Assessment</h2>
          <span>Posture, penalties, and response action</span>
        </div>
        <ShieldAlert className="h-4 w-4 text-clay-warning" />
      </div>
      <div className="workspace-risk-stack">
        <div className="workspace-risk-row">
          <span>Risk posture</span>
          <StatusBadge label={risk?.risk_posture ?? 'loading'} />
        </div>
        <div className="workspace-risk-row">
          <span>Confidence</span>
          <StatusBadge label={risk?.confidence_label ?? 'loading'} />
        </div>
        <div className="workspace-risk-row">
          <span>Response</span>
          <StatusBadge label={risk?.response_action ?? 'loading'} />
        </div>
        <div className="workspace-risk-row">
          <span>Strategy</span>
          <StatusBadge label={risk?.strategy_mode ?? 'loading'} />
        </div>
      </div>
      <p>{risk?.risk_reward_hint ?? 'Risk model is waiting for a complete workspace snapshot.'}</p>
      <p>{risk?.action_guidance ?? 'Operator review remains required before execution.'}</p>
      <div className="workspace-trigger-list">
        {(risk?.active_triggers ?? []).length === 0 ? (
          <span>No active risk triggers.</span>
        ) : (
          risk?.active_triggers.map((trigger) => <span key={trigger}>{trigger}</span>)
        )}
      </div>
    </section>
  )
}

function NewsSentimentConsole({
  news,
  sentiment,
}: {
  news: NewsContextItem[]
  sentiment: SentimentContextItem[]
}) {
  return (
    <section className="workspace-intel-panel">
      <div className="workspace-panel-title">
        <div>
          <h2>News and Sentiment</h2>
          <span>Focus-relevant external context</span>
        </div>
        <Newspaper className="h-4 w-4 text-clay-accent" />
      </div>
      <ContextList
        empty="No focus-relevant news yet."
        items={news.map((item) => ({
          id: `${item.source_name}-${item.published_at}`,
          title: item.headline,
          detail: item.summary ?? item.source_name,
        }))}
      />
      <ContextList
        empty="No focus-relevant sentiment snapshots yet."
        items={sentiment.map((item) => ({
          id: `${item.source_name}-${item.captured_at}`,
          title: item.sentiment_label,
          detail: `Score ${item.sentiment_score}`,
        }))}
      />
    </section>
  )
}

function ContextList({
  items,
  empty,
}: {
  items: Array<{ id: string; title: string; detail: string }>
  empty: string
}) {
  return (
    <div className="workspace-context-list">
      {items.length === 0 ? (
        <span>{empty}</span>
      ) : (
        items.map((item) => (
          <div key={item.id}>
            <strong>{item.title}</strong>
            <span>{item.detail}</span>
          </div>
        ))
      )}
    </div>
  )
}

function UpdateConsole({ snapshot }: { snapshot: WorkspaceSnapshot | null }) {
  return (
    <section className="workspace-intel-panel">
      <div className="workspace-panel-title">
        <div>
          <h2>Update Meta</h2>
          <span>Freshness and ingestion state</span>
        </div>
        <Clock3 className="h-4 w-4 text-clay-muted" />
      </div>
      <div className="workspace-risk-stack">
        <div className="workspace-risk-row">
          <span>Market</span>
          <StatusBadge label={snapshot?.update_meta.market_status ?? 'loading'} />
        </div>
        <div className="workspace-risk-row">
          <span>Context</span>
          <StatusBadge label={snapshot?.update_meta.context_status ?? 'loading'} />
        </div>
        <div className="workspace-risk-row">
          <span>Last ingest</span>
          <strong>{formatTime(snapshot?.update_meta.last_ingestion_at)}</strong>
        </div>
      </div>
      <div className="workspace-data-note">
        <BarChart3 className="h-4 w-4 text-clay-accent" />
        <span>Live focus updates stay backend-owned; browser actions only request reviewed focus changes.</span>
      </div>
    </section>
  )
}
