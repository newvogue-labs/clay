import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Crosshair,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  Square,
  Target,
  Zap,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import type {
  PairReplacementReviewSnapshot,
  SessionBriefingSignal,
  SessionBriefingSnapshot,
  SessionControlSnapshot,
  SessionLifecycleSnapshot,
  SessionPreflightCheck,
  SessionPreflightSnapshot,
} from '../../types/session-control'
import { useSessionControl } from './use-session-control'

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return 'not recorded'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString('en-GB', {
    day: '2-digit',
    hour: '2-digit',
    hour12: false,
    minute: '2-digit',
    month: 'short',
  })
}

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`
}

function getLifecycleTitle(lifecycle: SessionLifecycleSnapshot | null): string {
  if (!lifecycle) {
    return 'Session snapshot loading'
  }

  if (lifecycle.lifecycle_state === 'idle') {
    return 'Ready for preflight'
  }

  return lifecycle.lifecycle_state.replaceAll('_', ' ')
}

function getPrimarySignal(briefing: SessionBriefingSnapshot | null): SessionBriefingSignal | null {
  if (!briefing) {
    return null
  }

  return briefing.shortlist[0] ?? null
}

function getPreflightTone(check: SessionPreflightCheck): 'success' | 'danger' | 'warning' {
  if (check.status === 'ok') {
    return 'success'
  }

  return check.blocks_start ? 'danger' : 'warning'
}

export function SessionControlPage() {
  const sessionControl = useSessionControl()
  const snapshot = sessionControl.snapshot
  const lifecycle = snapshot?.lifecycle ?? null
  const preflight = snapshot?.preflight ?? null
  const briefing = snapshot?.briefing ?? null
  const replacementReview = sessionControl.replacementReview ?? snapshot?.pending_pair_replacement ?? null
  const primarySignal = getPrimarySignal(briefing)

  return (
    <div aria-label="session-control-page" className="screen-page session-control-page" data-screen="session-control">
      <header className="screen-page-header session-command-header">
        <div>
          <h2>Session Control</h2>
          <p>Lifecycle orchestration, preflight gates, focused target, and operator command</p>
        </div>
        <div className="session-command-row">
          <StatusBadge label={lifecycle?.lifecycle_state ?? (sessionControl.isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={preflight?.status ?? 'preflight_pending'} />
          <button
            disabled={sessionControl.isActing || !preflight || preflight.status !== 'pass'}
            onClick={() => {
              void sessionControl.startSession()
            }}
            type="button"
          >
            <Zap className="h-3.5 w-3.5" />
            Start session
          </button>
        </div>
      </header>

      {sessionControl.error ? (
        <section className="session-error-panel">
          <AlertTriangle className="h-4 w-4 text-clay-danger" />
          <span>Session control error: {sessionControl.error}</span>
        </section>
      ) : null}

      <SessionOverviewStrip
        isLoading={sessionControl.isLoading}
        lifecycle={lifecycle}
        preflight={preflight}
        primarySignal={primarySignal}
      />

      <div className="session-command-grid">
        <main className="session-main-stack">
          <PreflightMatrix
            isLoading={sessionControl.isLoading}
            preflight={preflight}
          />
          <BriefingConsole
            briefing={briefing}
            isLoading={sessionControl.isLoading}
          />
        </main>

        <aside className="session-side-stack">
          <LifecycleConsole
            isActing={sessionControl.isActing}
            isLoading={sessionControl.isLoading}
            lifecycle={lifecycle}
            onComplete={() => {
              void sessionControl.completeSession()
            }}
            onPause={() => {
              void sessionControl.pauseSession()
            }}
            onResume={() => {
              void sessionControl.resumeSession()
            }}
          />
          <TargetConsole
            briefing={briefing}
            lifecycle={lifecycle}
            primarySignal={primarySignal}
          />
          <ReplacementConsole
            isActing={sessionControl.isActing}
            isLoading={sessionControl.isLoading}
            lifecycle={lifecycle}
            onApply={() => {
              void sessionControl.applyReplacement()
            }}
            onReview={() => {
              void sessionControl.reviewReplacement()
            }}
            replacementReview={replacementReview}
          />
        </aside>
      </div>
    </div>
  )
}

type SessionOverviewStripProps = {
  lifecycle: SessionLifecycleSnapshot | null
  preflight: SessionPreflightSnapshot | null
  primarySignal: SessionBriefingSignal | null
  isLoading: boolean
}

function SessionOverviewStrip({
  lifecycle,
  preflight,
  primarySignal,
  isLoading,
}: SessionOverviewStripProps) {
  const checks = preflight?.checks ?? []
  const passedChecks = checks.filter((check) => check.status === 'ok').length

  return (
    <section className="session-overview-strip">
      <MetricCard
        icon={ShieldCheck}
        label="Lifecycle"
        value={isLoading ? 'loading' : getLifecycleTitle(lifecycle)}
        detail={`Runtime: ${lifecycle?.runtime_state ?? 'unknown'}`}
      />
      <MetricCard
        icon={CheckCircle2}
        label="Preflight"
        value={preflight?.status ?? 'pending'}
        detail={`${passedChecks} / ${checks.length} checks clear`}
      />
      <MetricCard
        icon={Crosshair}
        label="Current pair"
        value={lifecycle?.current_pair_symbol ?? primarySignal?.symbol ?? 'not selected'}
        detail={`Signal: ${lifecycle?.current_signal_id ?? primarySignal?.signal_id ?? 'standby'}`}
      />
      <MetricCard
        icon={BrainCircuit}
        label="Strategy"
        value={primarySignal ? formatPct(primarySignal.confidence) : 'waiting'}
        detail={primarySignal?.setup_summary ?? 'Briefing has not produced a ranked target yet.'}
      />
    </section>
  )
}

type MetricCardProps = {
  icon: typeof ShieldCheck
  label: string
  value: string
  detail: string
}

function MetricCard({ icon: Icon, label, value, detail }: MetricCardProps) {
  return (
    <div className="session-metric-card">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <Icon className="h-4 w-4 text-clay-accent" />
      <p>{detail}</p>
    </div>
  )
}

type PreflightMatrixProps = {
  preflight: SessionPreflightSnapshot | null
  isLoading: boolean
}

function PreflightMatrix({ preflight, isLoading }: PreflightMatrixProps) {
  return (
    <section className="session-preflight-panel">
      <div className="session-panel-title">
        <div>
          <h2>Hard Preflight</h2>
          <span>{preflight?.blocking_reason ?? 'All hard gates are available for operator review.'}</span>
        </div>
        <ShieldCheck className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading || !preflight ? (
        <div className="session-empty-line">Loading preflight...</div>
      ) : (
        <div className="session-preflight-list">
          {preflight.checks.map((check) => {
            const tone = getPreflightTone(check)
            return (
              <div className="session-preflight-row" data-tone={tone} key={check.check_id}>
                <span className="session-check-dot" />
                <div>
                  <strong>{check.label}</strong>
                  <em>{check.check_id}</em>
                </div>
                <p>{check.reason}</p>
                <StatusBadge label={check.status} />
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

type BriefingConsoleProps = {
  briefing: SessionBriefingSnapshot | null
  isLoading: boolean
}

function BriefingConsole({ briefing, isLoading }: BriefingConsoleProps) {
  return (
    <section className="session-briefing-panel">
      <div className="session-panel-title">
        <div>
          <h2>Pre-Session Briefing</h2>
          <span>{briefing?.active_strategy ?? 'strategy pending'}</span>
        </div>
        <BrainCircuit className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading || !briefing ? (
        <div className="session-empty-line">Loading briefing...</div>
      ) : (
        <>
          <div className="session-briefing-copy">
            <p>{briefing.market_context}</p>
            <p>{briefing.sentiment_summary}</p>
            <p>{briefing.ai_summary}</p>
          </div>

          <div className="session-shortlist-grid">
            {briefing.shortlist.map((signal) => (
              <article className="session-signal-card" key={signal.signal_id}>
                <div>
                  <strong>{signal.symbol}</strong>
                  <StatusBadge label={signal.state} />
                </div>
                <p>{signal.setup_summary}</p>
                <div className="session-signal-meta">
                  <span>{signal.direction}</span>
                  <span>confidence {formatPct(signal.confidence)}</span>
                  <span>rank {formatPct(signal.ranking_score)}</span>
                </div>
              </article>
            ))}
          </div>

          <div className="session-risk-alerts">
            <h3>Risk Alerts</h3>
            {briefing.risk_alerts.length === 0 ? (
              <p>No risk alerts reported.</p>
            ) : (
              briefing.risk_alerts.map((alert) => (
                <p key={alert}>
                  <AlertTriangle className="h-3.5 w-3.5 text-clay-warning" />
                  {alert}
                </p>
              ))
            )}
          </div>
        </>
      )}
    </section>
  )
}

type LifecycleConsoleProps = {
  lifecycle: SessionLifecycleSnapshot | null
  isLoading: boolean
  isActing: boolean
  onPause: () => void
  onResume: () => void
  onComplete: () => void
}

function LifecycleConsole({
  lifecycle,
  isLoading,
  isActing,
  onPause,
  onResume,
  onComplete,
}: LifecycleConsoleProps) {
  return (
    <section className="session-lifecycle-console">
      <div className="session-panel-title">
        <div>
          <h2>Session Lifecycle</h2>
          <span>{lifecycle?.session_id ?? 'session not started'}</span>
        </div>
        <Clock3 className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading || !lifecycle ? (
        <div className="session-empty-line">Loading lifecycle...</div>
      ) : (
        <>
          <dl className="session-lifecycle-list">
            <div>
              <dt>Lifecycle:</dt>
              <dd><StatusBadge label={lifecycle.lifecycle_state} /></dd>
            </div>
            <div>
              <dt>Runtime</dt>
              <dd><StatusBadge label={lifecycle.runtime_state} /></dd>
            </div>
            <div>
              <dt>Session ID</dt>
              <dd>{lifecycle.session_id ?? 'not started'}</dd>
            </div>
            <div>
              <dt>Current pair</dt>
              <dd>{lifecycle.current_pair_symbol ?? 'not selected'}</dd>
            </div>
            <div>
              <dt>Started</dt>
              <dd>{formatDateTime(lifecycle.started_at)}</dd>
            </div>
            <div>
              <dt>Paused</dt>
              <dd>{formatDateTime(lifecycle.paused_at)}</dd>
            </div>
          </dl>

          <div className="session-action-grid">
            <button disabled={isActing || !lifecycle.can_pause} onClick={onPause} type="button">
              <Pause className="h-3.5 w-3.5" />
              Pause session
            </button>
            <button disabled={isActing || !lifecycle.can_resume} onClick={onResume} type="button">
              <Play className="h-3.5 w-3.5" />
              Resume session
            </button>
            <button disabled={isActing || !lifecycle.can_complete} onClick={onComplete} type="button">
              <Square className="h-3.5 w-3.5" />
              Complete session
            </button>
          </div>
        </>
      )}
    </section>
  )
}

type TargetConsoleProps = {
  lifecycle: SessionLifecycleSnapshot | null
  briefing: SessionBriefingSnapshot | null
  primarySignal: SessionBriefingSignal | null
}

function TargetConsole({ lifecycle, briefing, primarySignal }: TargetConsoleProps) {
  const currentPair = lifecycle?.current_pair_symbol ?? primarySignal?.symbol ?? 'not selected'
  const targetLabel = currentPair === 'not selected' ? 'standby' : currentPair

  return (
    <section className="session-target-console">
      <div className="session-panel-title">
        <div>
          <h2>Focused Target</h2>
          <span>Current pair: {currentPair}</span>
        </div>
        <Target className="h-4 w-4 text-clay-accent" />
      </div>

      <div className="session-target-card">
        <strong>{targetLabel}</strong>
        <p>{primarySignal?.setup_summary ?? 'No ranked signal is available yet.'}</p>
        <div>
          <StatusBadge label={primarySignal?.direction ?? 'standby'} />
          <StatusBadge label={primarySignal?.state ?? lifecycle?.lifecycle_state ?? 'idle'} />
        </div>
      </div>

      <div className="session-backup-list">
        <h3>Shortlist</h3>
        {(briefing?.shortlist ?? []).filter((signal) => signal.symbol !== currentPair).length === 0 ? (
          <p>No backup targets in the current shortlist.</p>
        ) : (
          briefing?.shortlist
            .filter((signal) => signal.symbol !== currentPair)
            .map((signal) => (
              <p key={signal.signal_id}>
                <span>{signal.symbol}</span>
                <strong>{formatPct(signal.ranking_score)}</strong>
              </p>
            ))
        )}
      </div>
    </section>
  )
}

type ReplacementConsoleProps = {
  lifecycle: SessionLifecycleSnapshot | null
  replacementReview: PairReplacementReviewSnapshot | null
  isLoading: boolean
  isActing: boolean
  onReview: () => void
  onApply: () => void
}

function ReplacementConsole({
  lifecycle,
  replacementReview,
  isLoading,
  isActing,
  onReview,
  onApply,
}: ReplacementConsoleProps) {
  const canReview = Boolean(lifecycle && ['active_session', 'paused'].includes(lifecycle.lifecycle_state))

  return (
    <section className="session-replacement-console">
      <div className="session-panel-title">
        <div>
          <h2>Pair Replacement</h2>
          <span>{replacementReview ? `${replacementReview.current_symbol} -> ${replacementReview.proposed_symbol}` : 'No pending review'}</span>
        </div>
        <RotateCcw className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? (
        <div className="session-empty-line">Loading replacement flow...</div>
      ) : (
        <>
          <button disabled={isActing || !canReview} onClick={onReview} type="button">
            <RotateCcw className="h-3.5 w-3.5" />
            Review pair replacement
          </button>

          {!replacementReview ? (
            <p className="session-empty-line">No pending pair replacement review.</p>
          ) : (
            <div className="session-replacement-review">
              <p>
                <StatusBadge label={replacementReview.severity} />
                {replacementReview.summary}
              </p>
              <h3>Reasons to switch</h3>
              {replacementReview.reasons_to_switch.map((reason) => (
                <p key={reason}>{reason}</p>
              ))}
              <h3>Risks</h3>
              {replacementReview.risks.map((risk) => (
                <p key={risk}>{risk}</p>
              ))}
              <button
                disabled={isActing || replacementReview.blocks_apply}
                onClick={onApply}
                type="button"
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Apply pair replacement
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
