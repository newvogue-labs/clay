import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock3,
  Database,
  RefreshCcw,
  Shield,
  ShieldCheck,
  XCircle,
  Zap,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import { getSeverityTone } from '../../helpers/tone'
import type {
  DegradedTriggerSnapshot,
  LocalFallbackReadinessSnapshot,
  ReliabilityCheckSnapshot,
  ReliabilityIncidentSnapshot,
  ReliabilitySummary,
  ReleaseGateSnapshot,
} from '../../types/reliability'
import { useReliability } from './use-reliability'

type Tone = 'success' | 'warning' | 'danger' | 'muted'

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

function formatBoolean(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return 'unknown'
  }

  return value ? 'yes' : 'no'
}

function getCheckTone(status: ReliabilityCheckSnapshot['status']): Tone {
  if (status === 'pass') {
    return 'success'
  }
  if (status === 'warn') {
    return 'warning'
  }
  return 'danger'
}

function getReadinessTone(status: ReliabilitySummary['release_readiness_status'] | undefined): Tone {
  if (status === 'ready_for_demo') {
    return 'success'
  }
  if (status === 'needs_attention') {
    return 'warning'
  }
  if (status === 'blocked') {
    return 'danger'
  }
  return 'muted'
}

export function ReliabilityPage() {
  const reliability = useReliability()
  const snapshot = reliability.snapshot
  const summary = snapshot?.summary ?? null
  const fallback = snapshot?.fallback ?? null
  const degradedTriggers = snapshot?.degraded_triggers ?? []
  const readinessChecks = snapshot?.readiness_checks ?? []
  const releaseGates = snapshot?.release_gates ?? []
  const incidents = snapshot?.incidents ?? []

  return (
    <div aria-label="reliability-page" className="screen-page reliability-center-page" data-screen="reliability">
      <header className="screen-page-header reliability-command-header">
        <div>
          <h2>Reliability Center</h2>
          <p>Release gates, degraded-mode posture, local fallback, and incident readiness</p>
        </div>
        <div className="reliability-command-row">
          <StatusBadge label={summary?.overall_status ?? (reliability.isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={summary?.release_readiness_status ?? 'release_unknown'} />
          <span className="reliability-meta-chip">
            {summary ? `Last evaluated: ${formatDateTime(summary.last_evaluated_at)}` : 'Last evaluated: pending'}
          </span>
          <span className="reliability-meta-chip">
            {summary?.last_rechecked_at
              ? `Last recheck: ${formatDateTime(summary.last_rechecked_at)}`
              : 'Last recheck: pending'}
          </span>
          <button
            disabled={reliability.isLoading || reliability.isActing}
            onClick={() => {
              void reliability.recheck()
            }}
            type="button"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            Recheck Reliability
          </button>
        </div>
      </header>

      {reliability.error ? (
        <section className="reliability-error-panel">
          <AlertCircle className="h-4 w-4 text-clay-danger" />
          <span>{reliability.error}</span>
        </section>
      ) : null}

      <ReliabilityOverviewStrip
        fallback={fallback}
        incidents={incidents}
        isLoading={reliability.isLoading}
        releaseGates={releaseGates}
        summary={summary}
      />

      <div className="reliability-command-grid">
        <main className="reliability-main-stack">
          <ReleaseReadinessConsole
            isLoading={reliability.isLoading}
            readinessChecks={readinessChecks}
            releaseGates={releaseGates}
          />
          <DegradedModeConsole
            fallback={fallback}
            isLoading={reliability.isLoading}
            triggers={degradedTriggers}
          />
        </main>

        <aside className="reliability-side-stack">
          <FallbackConsole
            fallback={fallback}
            isLoading={reliability.isLoading}
          />
          <IncidentConsole
            incidents={incidents}
            isLoading={reliability.isLoading}
          />
          <OperatorMessageConsole
            isLoading={reliability.isLoading}
            summary={summary}
          />
        </aside>
      </div>
    </div>
  )
}

type ReliabilityOverviewStripProps = {
  summary: ReliabilitySummary | null
  fallback: LocalFallbackReadinessSnapshot | null
  releaseGates: ReleaseGateSnapshot[]
  incidents: ReliabilityIncidentSnapshot[]
  isLoading: boolean
}

function ReliabilityOverviewStrip({
  summary,
  fallback,
  releaseGates,
  incidents,
  isLoading,
}: ReliabilityOverviewStripProps) {
  const blockedGates = releaseGates.filter((gate) => gate.blocks_release).length
  const warningGates = releaseGates.filter((gate) => gate.status === 'warn').length
  const blockingGateCount = summary?.blocking_gate_count ?? blockedGates
  const warningGateCount = summary?.warning_gate_count ?? warningGates

  return (
    <section className="reliability-overview-strip">
      <ReliabilityMetricCard
        detail={`Degraded mode active: ${formatBoolean(summary?.degraded_mode_active)}`}
        icon={Activity}
        label="Overall status"
        tone={summary?.overall_status === 'healthy' ? 'success' : 'warning'}
        value={isLoading ? 'loading' : summary?.overall_status ?? 'unknown'}
      />
      <ReliabilityMetricCard
        detail={`Release readiness: ${summary?.release_readiness_status ?? 'unknown'}`}
        icon={ShieldCheck}
        label="Release readiness"
        tone={getReadinessTone(summary?.release_readiness_status)}
        value={summary?.release_readiness_status ?? 'pending'}
      />
      <ReliabilityMetricCard
        detail={`Local fallback ready: ${formatBoolean(fallback?.local_fallback_ready)}`}
        icon={Shield}
        label="Fallback"
        tone={fallback?.local_fallback_ready ? 'success' : 'warning'}
        value={fallback?.fallback_active ? 'active' : 'standby'}
      />
      <ReliabilityMetricCard
        detail={`${blockingGateCount} blocking / ${warningGateCount} warning`}
        icon={Database}
        label="Gates and incidents"
        tone={incidents.length > 0 || warningGates > 0 ? 'warning' : 'success'}
        value={`${releaseGates.length} gates`}
      />
    </section>
  )
}

type ReliabilityMetricCardProps = {
  icon: LucideIcon
  label: string
  value: string
  detail: string
  tone: Tone
}

function ReliabilityMetricCard({ icon: Icon, label, value, detail, tone }: ReliabilityMetricCardProps) {
  return (
    <div className="reliability-metric-card" data-tone={tone}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <Icon className="h-4 w-4" />
      <p>{detail}</p>
    </div>
  )
}

type ReleaseReadinessConsoleProps = {
  readinessChecks: ReliabilityCheckSnapshot[]
  releaseGates: ReleaseGateSnapshot[]
  isLoading: boolean
}

function ReleaseReadinessConsole({
  readinessChecks,
  releaseGates,
  isLoading,
}: ReleaseReadinessConsoleProps) {
  return (
    <section>
      <div className="reliability-panel-title">
        <div>
          <h3>Readiness Gates</h3>
          <span>{releaseGates.length} release gates / {readinessChecks.length} readiness checks</span>
        </div>
        <Database className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <p className="reliability-empty-line">Loading readiness checks...</p> : null}

      {!isLoading ? (
        <div className="reliability-gate-board">
          <div>
            <h4>Readiness checks</h4>
            <div className="reliability-check-list">
              {readinessChecks.length === 0 ? (
                <p className="reliability-empty-line">No readiness checks are registered.</p>
              ) : (
                readinessChecks.map((check) => (
                  <article className="reliability-check-row" data-tone={getCheckTone(check.status)} key={check.check_id}>
                    {check.status === 'pass' ? <CheckCircle2 className="h-4 w-4" /> : check.status === 'warn' ? <AlertCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                    <div>
                      <strong>{check.label}</strong>
                      <p>{check.detail}</p>
                    </div>
                    <StatusBadge label={check.status} />
                  </article>
                ))
              )}
            </div>
          </div>

          <div>
            <h4>Release gates</h4>
            <div className="reliability-check-list">
              {releaseGates.length === 0 ? (
                <p className="reliability-empty-line">No release gates are registered.</p>
              ) : (
                releaseGates.map((gate) => (
                  <article className="reliability-gate-row" data-tone={getCheckTone(gate.status)} key={gate.gate_id}>
                    <div>
                      <strong>{gate.label}</strong>
                      <p>{gate.detail}</p>
                    </div>
                    <StatusBadge label={gate.status} />
                    <span>{gate.blocks_release ? 'blocks release' : 'non-blocking'}</span>
                  </article>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

type DegradedModeConsoleProps = {
  triggers: DegradedTriggerSnapshot[]
  fallback: LocalFallbackReadinessSnapshot | null
  isLoading: boolean
}

function DegradedModeConsole({ triggers, fallback, isLoading }: DegradedModeConsoleProps) {
  return (
    <section>
      <div className="reliability-panel-title">
        <div>
          <h3>Degraded Mode</h3>
          <span>{triggers.length} active trigger(s)</span>
        </div>
        <Zap className="h-4 w-4 text-clay-warning" />
      </div>

      {isLoading ? <p className="reliability-empty-line">Loading degraded-mode posture...</p> : null}

      {!isLoading && fallback ? (
        <div className="reliability-fallback-summary">
          <p>
            <span>Fallback active</span>
            <strong>{formatBoolean(fallback.fallback_active)}</strong>
          </p>
          <p>
            <span>Degraded roles</span>
            <strong>{fallback.degraded_roles.length || 'none'}</strong>
          </p>
        </div>
      ) : null}

      {!isLoading ? (
        <div className="reliability-trigger-list">
          {triggers.length === 0 ? (
            <p className="reliability-empty-line">No degraded triggers are active.</p>
          ) : (
            triggers.map((trigger) => (
              <article className="reliability-trigger-card" data-tone={getSeverityTone(trigger.severity)} key={trigger.trigger_id}>
                <div>
                  <AlertCircle className="h-4 w-4" />
                  <StatusBadge label={trigger.severity} tone={getSeverityTone(trigger.severity)} />
                </div>
                <h4>{trigger.title}</h4>
                <p>{trigger.description}</p>
                <span>{trigger.recommended_action}</span>
              </article>
            ))
          )}
        </div>
      ) : null}
    </section>
  )
}

type FallbackConsoleProps = {
  fallback: LocalFallbackReadinessSnapshot | null
  isLoading: boolean
}

function FallbackConsole({ fallback, isLoading }: FallbackConsoleProps) {
  return (
    <section>
      <div className="reliability-panel-title">
        <div>
          <h3>Local Fallback</h3>
          <span>{fallback?.local_fallback_ready ? 'ready' : 'needs operator review'}</span>
        </div>
        <Shield className="h-4 w-4 text-clay-success" />
      </div>

      {isLoading ? <p className="reliability-empty-line">Loading local fallback...</p> : null}
      {!isLoading && !fallback ? <p className="reliability-empty-line">Fallback readiness is not available.</p> : null}

      {!isLoading && fallback ? (
        <>
          <div className="reliability-fallback-grid">
            <p>
              <span>Fallback active</span>
              <strong>{formatBoolean(fallback.fallback_active)}</strong>
            </p>
            <p>
              <span>Local fallback ready</span>
              <strong>{formatBoolean(fallback.local_fallback_ready)}</strong>
            </p>
          </div>
          <div className="reliability-role-strip">
            {fallback.degraded_roles.length === 0 ? (
              <span>no degraded roles</span>
            ) : (
              fallback.degraded_roles.map((role) => <span key={role}>{role}</span>)
            )}
          </div>
          <p className="reliability-fallback-note">{fallback.operator_message}</p>
        </>
      ) : null}
    </section>
  )
}

type IncidentConsoleProps = {
  incidents: ReliabilityIncidentSnapshot[]
  isLoading: boolean
}

function IncidentConsole({ incidents, isLoading }: IncidentConsoleProps) {
  return (
    <section>
      <div className="reliability-panel-title">
        <div>
          <h3>Incident Review</h3>
          <span>{incidents.length} active item(s)</span>
        </div>
        <AlertCircle className="h-4 w-4 text-clay-warning" />
      </div>

      {isLoading ? <p className="reliability-empty-line">Loading incidents...</p> : null}
      {!isLoading && incidents.length === 0 ? <p className="reliability-empty-line">No active incidents.</p> : null}

      {!isLoading
        ? incidents.map((incident) => (
            <article
              className="reliability-incident-card"
              data-tone={getSeverityTone(incident.severity)}
              key={`${incident.source_name}-${incident.recorded_at}`}
            >
              <div>
                <strong>{incident.source_name}</strong>
                <StatusBadge label={incident.severity} tone={getSeverityTone(incident.severity)} />
              </div>
              <p>{incident.message}</p>
              <span>{formatDateTime(incident.recorded_at)}</span>
            </article>
          ))
        : null}
    </section>
  )
}

type OperatorMessageConsoleProps = {
  summary: ReliabilitySummary | null
  isLoading: boolean
}

function OperatorMessageConsole({ summary, isLoading }: OperatorMessageConsoleProps) {
  return (
    <section>
      <div className="reliability-panel-title">
        <div>
          <h3>Operator Message</h3>
          <span>
            {summary?.last_rechecked_at
              ? `rechecked ${formatDateTime(summary.last_rechecked_at)}`
              : summary
                ? `evaluated ${formatDateTime(summary.last_evaluated_at)}`
                : 'pending evaluation'}
          </span>
        </div>
        <Clock3 className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? (
        <p className="reliability-empty-line">Loading operator message...</p>
      ) : (
        <div className="reliability-operator-note">
          <p>{summary?.operator_message ?? 'Reliability posture has not been evaluated yet.'}</p>
        </div>
      )}
    </section>
  )
}
