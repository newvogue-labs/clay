import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  Percent,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { StatusBadge } from '../../components/status-badge'
import type { AppScreen } from '../../components/app-sidebar'
import { useControlCenter } from '../control-center/use-control-center'
import { useReliability } from '../reliability/use-reliability'
import { useWorkspace } from '../workspace/use-workspace'

type OverviewPageProps = {
  onNavigate: (screen: AppScreen) => void
}

export function OverviewPage({ onNavigate }: OverviewPageProps) {
  const controlCenter = useControlCenter()
  const workspace = useWorkspace()
  const reliability = useReliability()

  const controlSnapshot = controlCenter.snapshot
  const workspaceSnapshot = workspace.snapshot
  const reliabilitySnapshot = reliability.snapshot
  const signals = workspaceSnapshot?.signals ?? []
  const topSignals = signals.slice(0, 4)
  const activeSignals = signals.filter((signal) => signal.state === 'active')
  const activeIncidents = controlSnapshot?.summary.active_incident_count ?? 0
  const criticalIncidents = controlSnapshot?.summary.critical_incident_count ?? 0
  const marketStatus = controlSnapshot?.ingestion.market_status ?? 'loading'
  const contextStatus = controlSnapshot?.ingestion.context_status ?? 'loading'
  const releaseStatus = reliabilitySnapshot?.summary.release_readiness_status ?? 'loading'
  const overallStatus = controlSnapshot?.summary.overall_status ?? 'loading'
  const reviewScore = reliabilitySnapshot ? Math.max(0, 100 - reliabilitySnapshot.summary.warning_gate_count * 6) : 0

  return (
    <div aria-label="overview-page" className="screen-page overview-page" data-screen="overview">
      <header className="screen-page-header">
        <div>
          <h2>Mission Overview</h2>
          <p>System state and market intelligence summary</p>
        </div>
        <div className="mission-mode-chip">
          <span className={`mission-dot ${overallStatus === 'healthy' ? 'bg-clay-success' : 'bg-clay-warning'}`} />
          <span>{overallStatus === 'healthy' ? 'Operational Mode' : 'Attention Mode'}</span>
          <span className="mission-chip-divider" />
          <span>Release: {releaseStatus.replaceAll('_', ' ')}</span>
        </div>
      </header>

      <div className="overview-kpi-grid">
        <MetricCard
          icon={<Zap className="h-3.5 w-3.5" />}
          label="Active Signals"
          meta={`${activeSignals.length} active / ${signals.length} tracked`}
          value={String(activeSignals.length)}
        />
        <MetricCard
          icon={<BarChart3 className="h-3.5 w-3.5" />}
          label="Simulated Result"
          meta="Demo discipline pending"
          tone="success"
          value="+0.0%"
        />
        <MetricCard
          icon={<Percent className="h-3.5 w-3.5" />}
          label="Review Score"
          meta="Derived from release gates"
          value={`${reviewScore}/100`}
        />
        <MetricCard
          icon={<ShieldCheck className="h-3.5 w-3.5" />}
          label="System Health"
          meta={`Market ${marketStatus} / Context ${contextStatus}`}
          tone={overallStatus === 'healthy' ? 'success' : 'warning'}
          value={overallStatus}
        />
        <MetricCard
          icon={<AlertCircle className="h-3.5 w-3.5" />}
          label="Active Alerts"
          meta={`${criticalIncidents} critical`}
          tone={activeIncidents > 0 ? 'warning' : 'success'}
          value={String(activeIncidents).padStart(2, '0')}
        />
      </div>

      <div className="overview-secondary-grid">
        <CompactStatus label="Consensus" status={criticalIncidents > 0 ? 'conflict' : activeIncidents > 0 ? 'partial' : 'agreement'} />
        <CompactStatus label="Market Data" status={marketStatus} />
        <CompactStatus label="Context Feeds" status={contextStatus} />
        <CompactStatus label="Readiness" status={releaseStatus} />
      </div>

      <div className="overview-layout-grid">
        <div className="overview-main-stack">
          <section className="overview-panel overview-signals-panel">
            <div className="panel-title-row">
              <h3>Top Ranked Signals</h3>
              <button
                className="link-command"
                onClick={() => {
                  onNavigate('workspace')
                }}
                type="button"
              >
                Open Workspace <ArrowRight className="h-3 w-3" />
              </button>
            </div>
            <div className="dense-list">
              {topSignals.length > 0 ? (
                topSignals.map((signal) => {
                  const isLong = signal.direction.toLowerCase() === 'long'
                  return (
                    <button
                      className="signal-row"
                      key={signal.signal_id}
                      onClick={() => {
                        onNavigate('workspace')
                      }}
                      type="button"
                    >
                      <span className={`signal-icon ${isLong ? 'text-clay-success' : 'text-clay-danger'}`}>
                        {isLong ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="signal-name">{signal.pair}</span>
                        <span className="signal-meta">Confidence {(signal.confidence * 100).toFixed(0)}% / Rank {(signal.ranking_score * 100).toFixed(0)}</span>
                      </span>
                      <StatusBadge label={signal.state} />
                    </button>
                  )
                })
              ) : (
                <div className="empty-terminal-line">No active ranked signals available.</div>
              )}
            </div>
          </section>

          <section className="overview-panel overview-audit-panel">
            <div className="panel-title-row">
              <h3>Recent Alerts / Audit Trail</h3>
              <button
                className="link-command"
                onClick={() => {
                  onNavigate('control-center')
                }}
                type="button"
              >
                View Full Log <ArrowRight className="h-3 w-3" />
              </button>
            </div>
            <div className="audit-terminal">
              {(controlSnapshot?.audit ?? []).slice(0, 5).map((event) => (
                <div className="audit-line" key={`${event.timestamp}-${event.event_type}`}>
                  <span>{new Date(event.timestamp).toLocaleTimeString('en-GB', { hour12: false })}</span>
                  <strong>[{event.event_type.split('.')[0].toUpperCase()}]</strong>
                  <em>{event.event_type}</em>
                </div>
              ))}
              {(controlSnapshot?.audit ?? []).length === 0 ? (
                <div className="audit-line">
                  <span>--:--:--</span>
                  <strong>[BOOT]</strong>
                  <em>Audit stream waiting for live events.</em>
                </div>
              ) : null}
            </div>
          </section>
        </div>

        <aside className="overview-side-stack">
          <section className="overview-panel">
            <h3>Quick Actions</h3>
            <div className="quick-action-stack">
              <button
                aria-label="Open trading workspace from overview"
                onClick={() => {
                  onNavigate('workspace')
                }}
                type="button"
              >
                <Activity className="h-3.5 w-3.5" /> Trading Workspace
              </button>
              <button
                aria-label="Open operations console from overview"
                onClick={() => {
                  onNavigate('control-center')
                }}
                type="button"
              >
                <ShieldCheck className="h-3.5 w-3.5" /> Control Center
              </button>
              <button
                aria-label="Open session workflow from overview"
                onClick={() => {
                  onNavigate('session-control')
                }}
                type="button"
              >
                <CheckCircle2 className="h-3.5 w-3.5" /> Session Control
              </button>
            </div>
          </section>

          <section className="overview-panel">
            <h3>Active Strategy</h3>
            <div className="strategy-block">
              <span>Current Profile</span>
              <strong>{workspaceSnapshot?.risk.strategy_mode ?? 'momentum'}</strong>
            </div>
            <div className="strategy-block">
              <span>Risk Regime</span>
              <strong className="text-clay-warning">{workspaceSnapshot?.risk.risk_posture ?? 'moderate'}</strong>
            </div>
          </section>

          <section className="overview-panel">
            <h3>System Status</h3>
            <div className="service-mini-list">
              {(controlSnapshot?.services ?? []).slice(0, 5).map((service) => (
                <div className="service-mini-row" key={service.service_id}>
                  <span>{service.service_name}</span>
                  <StatusBadge label={service.status} />
                </div>
              ))}
              {!controlSnapshot ? (
                <div className="service-mini-row">
                  <span>Control API</span>
                  <StatusBadge label="loading" />
                </div>
              ) : null}
            </div>
          </section>

          <section className="overview-panel">
            <h3>Data Spine</h3>
            <div className="data-spine-row">
              <Database className="h-4 w-4 text-clay-accent" />
              <span>Market items: {controlSnapshot?.ingestion.market_items.length ?? 0}</span>
            </div>
          </section>
        </aside>
      </div>

      {controlCenter.error || workspace.error || reliability.error ? (
        <section className="overview-panel">
          <h3>Integration Warnings</h3>
          <p>{controlCenter.error ?? workspace.error ?? reliability.error}</p>
        </section>
      ) : null}
    </div>
  )
}

type MetricCardProps = {
  label: string
  value: string
  meta: string
  icon: ReactNode
  tone?: 'default' | 'success' | 'warning'
}

function MetricCard({ label, value, meta, icon, tone = 'default' }: MetricCardProps) {
  const toneClass =
    tone === 'success'
      ? 'text-clay-success'
      : tone === 'warning'
        ? 'text-clay-warning'
        : 'text-clay-text'

  return (
    <section className="metric-card">
      <div className="metric-card-header">
        <h3>{label}</h3>
        <span className={toneClass}>{icon}</span>
      </div>
      <div>
        <strong className={toneClass}>{value}</strong>
        <span>{meta}</span>
      </div>
    </section>
  )
}

function CompactStatus({ label, status }: { label: string; status: string }) {
  return (
    <section className="compact-status-card">
      <span>{label}</span>
      <StatusBadge label={status} />
    </section>
  )
}
