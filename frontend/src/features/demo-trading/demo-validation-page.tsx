import {
  AlertTriangle,
  BarChart2,
  CheckCircle2,
  ClipboardList,
  Clock3,
  FileCheck2,
  PlayCircle,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import type {
  DemoActiveSessionSnapshot,
  DemoReadinessGateSnapshot,
  DemoReadinessSnapshot,
  DemoTradeRecordSnapshot,
} from '../../types/demo-trading'
import { outcomeTone } from '../../types/demo-trading'
import { useDemoTrading } from './use-demo-trading'

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

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'pending'
  }

  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function getGateTone(status: DemoReadinessGateSnapshot['status']): 'success' | 'warning' | 'danger' {
  if (status === 'pass') {
    return 'success'
  }
  if (status === 'fail') {
    return 'danger'
  }
  return 'warning'
}

export function DemoValidationPage() {
  const demoTrading = useDemoTrading()
  const snapshot = demoTrading.snapshot
  const readiness = snapshot?.readiness ?? null
  const activeSession = snapshot?.active_session ?? null
  const records = snapshot?.records ?? []

  return (
    <div aria-label="demo-validation-page" className="screen-page demo-validation-page" data-screen="demo-validation">
      <header className="screen-page-header demo-command-header">
        <div>
          <h2>Demo Validation</h2>
          <p>Manual execution capture, readiness gates, broker result tracking, and promotion evidence</p>
        </div>
        <div className="demo-command-row">
          <StatusBadge label={readiness?.status ?? (demoTrading.isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={activeSession?.lifecycle_state ?? 'session_pending'} />
          <span>{activeSession?.current_pair_symbol ?? 'no active pair'}</span>
        </div>
      </header>

      {demoTrading.error ? (
        <section className="demo-error-panel">
          <AlertTriangle className="h-4 w-4 text-clay-danger" />
          <span>{demoTrading.error}</span>
        </section>
      ) : null}

      <DemoOverviewStrip
        activeSession={activeSession}
        isLoading={demoTrading.isLoading}
        readiness={readiness}
        records={records}
      />

      <div className="demo-command-grid">
        <main className="demo-main-stack">
          <ReadinessGateConsole
            isLoading={demoTrading.isLoading}
            readiness={readiness}
          />
          <ResultTrackingConsole
            isActing={demoTrading.isActing}
            isLoading={demoTrading.isLoading}
            onMarkResult={(recordId, resultProfile) => {
              void demoTrading.markResult(recordId, resultProfile)
            }}
            records={records}
          />
        </main>

        <aside className="demo-side-stack">
          <ManualActionConsole
            activeSession={activeSession}
            isActing={demoTrading.isActing}
            isLoading={demoTrading.isLoading}
            onLogTrade={(operatorAction) => {
              void demoTrading.logTrade(operatorAction)
            }}
          />
          <OutcomeMixConsole
            isLoading={demoTrading.isLoading}
            readiness={readiness}
          />
        </aside>
      </div>
    </div>
  )
}

type DemoOverviewStripProps = {
  readiness: DemoReadinessSnapshot | null
  activeSession: DemoActiveSessionSnapshot | null
  records: DemoTradeRecordSnapshot[]
  isLoading: boolean
}

function DemoOverviewStrip({
  readiness,
  activeSession,
  records,
  isLoading,
}: DemoOverviewStripProps) {
  const awaitingResult = records.filter((record) => record.awaiting_result).length

  return (
    <section className="demo-overview-strip">
      <DemoMetricCard
        detail={`Sessions: ${readiness?.distinct_session_count ?? 0}`}
        icon={ShieldCheck}
        label="Readiness"
        value={isLoading ? 'loading' : readiness?.status ?? 'pending'}
      />
      <DemoMetricCard
        detail={`Cumulative PnL: ${formatPct(readiness?.cumulative_pnl_pct)}`}
        icon={BarChart2}
        label="Cumulative PnL"
        value={formatPct(readiness?.cumulative_pnl_pct)}
      />
      <DemoMetricCard
        detail={`${awaitingResult} awaiting result`}
        icon={ClipboardList}
        label="Total records"
        value={String(readiness?.total_records ?? records.length)}
      />
      <DemoMetricCard
        detail={`Signal: ${activeSession?.current_signal_id ?? 'standby'}`}
        icon={Target}
        label="Current pair"
        value={activeSession?.current_pair_symbol ?? 'not selected'}
      />
    </section>
  )
}

type DemoMetricCardProps = {
  icon: typeof ShieldCheck
  label: string
  value: string
  detail: string
}

function DemoMetricCard({ icon: Icon, label, value, detail }: DemoMetricCardProps) {
  return (
    <div className="demo-metric-card">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <Icon className="h-4 w-4 text-clay-accent" />
      <p>{detail}</p>
    </div>
  )
}

type ReadinessGateConsoleProps = {
  readiness: DemoReadinessSnapshot | null
  isLoading: boolean
}

function ReadinessGateConsole({ readiness, isLoading }: ReadinessGateConsoleProps) {
  return (
    <section className="demo-readiness-console" aria-label="demo-readiness-panel">
      <div className="demo-panel-title">
        <div>
          <h3>Readiness Gates</h3>
          <span>{readiness?.operator_message ?? 'Readiness snapshot pending.'}</span>
        </div>
        <ShieldCheck className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <div className="demo-empty-line">Loading readiness gates...</div> : null}
      {!isLoading && readiness ? (
        <>
          <div className="demo-readiness-stats">
            <p>Sessions: {readiness.distinct_session_count}</p>
            <p>Total records: {readiness.total_records}</p>
            <p>Resolved records: {readiness.resolved_record_count}</p>
            <p>Profitable records: {readiness.profitable_record_count}</p>
            <p>Cumulative PnL: {readiness.cumulative_pnl_pct}%</p>
          </div>
          <div className="demo-gate-list">
            {readiness.gates.map((gate) => (
              <article className="demo-gate-row" data-tone={getGateTone(gate.status)} key={gate.gate_id}>
                <span className="demo-gate-dot" />
                <div>
                  <strong>{gate.label}</strong>
                  <em>{gate.gate_id}</em>
                </div>
                <p>{gate.detail}</p>
                <StatusBadge label={gate.status} />
              </article>
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}

type ManualActionConsoleProps = {
  activeSession: DemoActiveSessionSnapshot | null
  isLoading: boolean
  isActing: boolean
  onLogTrade: (operatorAction: DemoTradeRecordSnapshot['operator_action']) => void
}

function ManualActionConsole({
  activeSession,
  isLoading,
  isActing,
  onLogTrade,
}: ManualActionConsoleProps) {
  const disabled = isLoading || isActing || !activeSession?.can_log_decision

  return (
    <section className="demo-action-console" aria-label="manual-demo-actions-panel">
      <div className="demo-panel-title">
        <div>
          <h3>Manual Demo Actions</h3>
          <span>{activeSession?.session_id ?? 'session not active'}</span>
        </div>
        <PlayCircle className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <div className="demo-empty-line">Loading action surface...</div> : null}
      {!isLoading && activeSession ? (
        <>
          <div className="demo-session-card">
            <strong>{activeSession.current_pair_symbol ?? 'No pair selected'}</strong>
            <p>Session id: {activeSession.session_id ?? 'none'}</p>
            <p>Signal id: {activeSession.current_signal_id ?? 'none'}</p>
            {activeSession.blocking_reason ? <p>{activeSession.blocking_reason}</p> : null}
          </div>
          <div className="demo-action-grid">
            <button disabled={disabled} onClick={() => onLogTrade('entered')} type="button">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Log Entered Trade
            </button>
            <button disabled={disabled} onClick={() => onLogTrade('skipped')} type="button">
              <Clock3 className="h-3.5 w-3.5" />
              Log Skipped Trade
            </button>
            <button disabled={disabled} onClick={() => onLogTrade('off_signal')} type="button">
              <AlertTriangle className="h-3.5 w-3.5" />
              Log Off-Signal Trade
            </button>
            <button disabled={disabled} onClick={() => onLogTrade('entered_late')} type="button">
              <Clock3 className="h-3.5 w-3.5" />
              Log Late Entry
            </button>
          </div>
        </>
      ) : null}
    </section>
  )
}

type ResultTrackingConsoleProps = {
  records: DemoTradeRecordSnapshot[]
  isLoading: boolean
  isActing: boolean
  onMarkResult: (recordId: number, resultProfile: 'win' | 'flat' | 'loss') => void
}

function ResultTrackingConsole({
  records,
  isLoading,
  isActing,
  onMarkResult,
}: ResultTrackingConsoleProps) {
  return (
    <section className="demo-result-console" aria-label="result-tracking-panel">
      <div className="demo-panel-title">
        <div>
          <h3>Tracked Demo Results</h3>
          <span>{records.length} broker records</span>
        </div>
        <FileCheck2 className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <div className="demo-empty-line">Loading demo records...</div> : null}
      {!isLoading && records.length === 0 ? <div className="demo-empty-line">No demo records yet.</div> : null}
      {!isLoading && records.length > 0 ? (
        <div className="demo-record-table">
          <div className="demo-record-head">
            <span>Signal</span>
            <span>Execution</span>
            <span>Outcome</span>
            <span>PnL</span>
            <span>Result</span>
          </div>
          {records.map((record) => (
            <article className="demo-record-row" key={record.record_id}>
              <div>
                <strong>{record.symbol}</strong>
                <span>{record.signal_id}</span>
              </div>
              <div>
                <strong>{record.operator_action}</strong>
                <span>{record.executed_symbol ? `Executed symbol: ${record.executed_symbol}` : `Broker status: ${record.broker_status ?? 'pending'}`}</span>
              </div>
              <div>
                <StatusBadge label={record.outcome_status} tone={outcomeTone(record.outcome_status)} />
                <span>{formatDateTime(record.observed_at ?? record.recorded_at)}</span>
              </div>
              <div className={(record.pnl_pct ?? 0) >= 0 ? 'is-positive' : 'is-negative'}>
                {(record.pnl_pct ?? 0) >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                <strong>{formatPct(record.pnl_pct)}</strong>
              </div>
              <div className="demo-result-actions">
                {record.awaiting_result ? (
                  <>
                    <button disabled={isActing} onClick={() => onMarkResult(record.record_id, 'win')} type="button">
                      Mark Win
                    </button>
                    <button disabled={isActing} onClick={() => onMarkResult(record.record_id, 'flat')} type="button">
                      Mark Flat
                    </button>
                    <button disabled={isActing} onClick={() => onMarkResult(record.record_id, 'loss')} type="button">
                      Mark Loss
                    </button>
                  </>
                ) : (
                  <span>Result captured</span>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

type OutcomeMixConsoleProps = {
  readiness: DemoReadinessSnapshot | null
  isLoading: boolean
}

function OutcomeMixConsole({ readiness, isLoading }: OutcomeMixConsoleProps) {
  const outcomes = [
    ['Matched', readiness?.outcome_counts.matched ?? 0, 'matched'],
    ['Missed', readiness?.outcome_counts.missed ?? 0, 'missed'],
    ['Late matched', readiness?.outcome_counts.late_matched ?? 0, 'late_matched'],
    ['Mismatched', readiness?.outcome_counts.mismatched ?? 0, 'mismatched'],
    ['Unresolved', readiness?.outcome_counts.unresolved ?? 0, 'unresolved'],
  ] as const

  return (
    <section className="demo-outcome-console">
      <div className="demo-panel-title">
        <div>
          <h3>Outcome Mix</h3>
          <span>{readiness?.total_records ?? 0} tracked actions</span>
        </div>
        <BarChart2 className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? <div className="demo-empty-line">Loading outcome mix...</div> : null}
      {!isLoading ? (
        <div className="demo-outcome-list">
          {outcomes.map(([label, value, outcome]) => (
            <p data-tone={outcomeTone(outcome)} key={outcome}>
              <span>{label}</span>
              <strong>{value}</strong>
            </p>
          ))}
        </div>
      ) : null}
    </section>
  )
}
