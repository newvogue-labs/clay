import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Play,
  RefreshCw,
  Route,
  Target,
} from 'lucide-react'

import type { AppScreen } from '../../components/app-sidebar'
import { StatusBadge } from '../../components/status-badge'
import type {
  AlphaGateStatus,
  AlphaOperatorStepSnapshot,
  AlphaReadinessGateSnapshot,
  AlphaReadinessSnapshot,
} from '../../types/alpha'
import { useAlphaOperatorConsole } from './use-alpha-operator-console'

type AlphaOperatorPageProps = {
  onNavigate: (screen: AppScreen) => void
}

function getTone(status: AlphaGateStatus | string): 'pass' | 'warn' | 'fail' {
  if (status === 'pass' || status === 'operator_path_ready') {
    return 'pass'
  }
  if (status === 'fail' || status === 'blocked') {
    return 'fail'
  }
  return 'warn'
}

function resolveAlphaTargetScreen(targetScreen: string): AppScreen {
  const allowedTargets: AppScreen[] = [
    'workspace',
    'session-control',
    'demo-validation',
    'session-review',
    'validation-lab',
    'reliability',
  ]
  return allowedTargets.includes(targetScreen as AppScreen) ? (targetScreen as AppScreen) : 'overview'
}

function formatValue(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return 'pending'
  }
  if (typeof value === 'boolean') {
    return value ? 'yes' : 'no'
  }
  return String(value).replaceAll('_', ' ')
}

export function AlphaOperatorPage({ onNavigate }: AlphaOperatorPageProps) {
  const alpha = useAlphaOperatorConsole()
  const snapshot = alpha.snapshot
  const summary = snapshot?.summary ?? null
  const nextStep = alpha.nextStep
  const canRunNextStep = alpha.canRunNextStep

  return (
    <div aria-label="alpha-operator-page" className="screen-page alpha-operator-page" data-screen="alpha-operator">
      <header className="screen-page-header alpha-operator-command-header">
        <div>
          <h2>Alpha Operator Console</h2>
          <p>Single-path alpha runbook, evidence, and next operator action</p>
        </div>
        <div className="alpha-operator-command-row">
          <StatusBadge label={summary?.readiness_status ?? (alpha.isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={summary?.operator_path_ready ? 'operator_path_ready' : 'operator_attention'} />
          <button
            aria-label="Refresh alpha operator console"
            disabled={alpha.isLoading || alpha.isActing}
            onClick={() => {
              void alpha.refresh()
            }}
            type="button"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
      </header>

      {alpha.error ? <div className="alpha-operator-error">{alpha.error}</div> : null}
      {alpha.lastActionMessage ? <div className="alpha-operator-success">{alpha.lastActionMessage}</div> : null}

      <section className="alpha-operator-next-panel">
        <div className="alpha-operator-next-copy">
          <span>Next alpha step</span>
          <strong>{nextStep?.action_label ?? (alpha.isLoading && !alpha.snapshot ? 'Loading…' : 'Path complete')}</strong>
          <p>{nextStep?.detail ?? summary?.next_action ?? 'No pending operator step.'}</p>
        </div>
        <div className="alpha-operator-next-actions">
          <button
            aria-label={nextStep ? `Run alpha step ${nextStep.action_label}` : 'Run alpha step'}
            disabled={!nextStep || !canRunNextStep || alpha.isLoading || alpha.isActing}
            onClick={() => {
              void alpha.runNextStep()
            }}
            type="button"
          >
            <Play className="h-3.5 w-3.5" />
            {alpha.isActing ? 'Running' : nextStep?.action_label ?? 'Complete'}
          </button>
          <button
            aria-label={nextStep ? `Open alpha target ${nextStep.target_screen}` : 'Open alpha target'}
            disabled={!nextStep || alpha.isActing}
            onClick={() => {
              if (nextStep) {
                onNavigate(resolveAlphaTargetScreen(nextStep.target_screen))
              }
            }}
            type="button"
          >
            <ArrowRight className="h-3.5 w-3.5" />
            Open target
          </button>
        </div>
      </section>

      <AlphaSummaryStrip snapshot={snapshot} />

      <div className="alpha-operator-grid">
        <AlphaRunbookPanel
          isLoading={alpha.isLoading}
          steps={snapshot?.operator_steps ?? []}
        />
        <AlphaEvidencePanel snapshot={snapshot} />
      </div>

      <AlphaGatePanel gates={snapshot?.gates ?? []} isLoading={alpha.isLoading} />
    </div>
  )
}

function AlphaSummaryStrip({ snapshot }: { snapshot: AlphaReadinessSnapshot | null }) {
  const summary = snapshot?.summary ?? null
  const evidence = snapshot?.evidence ?? null

  return (
    <section className="alpha-operator-summary-strip">
      <AlphaConsoleMetric
        label="Readiness"
        tone={getTone(summary?.readiness_status ?? 'warn')}
        value={summary?.readiness_status ?? 'loading'}
      />
      <AlphaConsoleMetric
        label="Blocking gates"
        tone={summary?.blocking_gate_count ? 'fail' : 'pass'}
        value={summary?.blocking_gate_count ?? 0}
      />
      <AlphaConsoleMetric
        label="Warnings"
        tone={summary?.warning_gate_count ? 'warn' : 'pass'}
        value={summary?.warning_gate_count ?? 0}
      />
      <AlphaConsoleMetric
        label="Focused symbol"
        tone={evidence?.focus_symbol ? 'pass' : 'warn'}
        value={evidence?.focus_symbol ?? 'pending'}
      />
      <AlphaConsoleMetric
        label="Validation runs"
        tone={evidence?.validation_replay_ready ? 'pass' : 'warn'}
        value={evidence?.validation_run_count ?? 0}
      />
    </section>
  )
}

type AlphaConsoleMetricProps = {
  label: string
  value: string | number
  tone: 'pass' | 'warn' | 'fail'
}

function AlphaConsoleMetric({ label, value, tone }: AlphaConsoleMetricProps) {
  return (
    <article className="alpha-console-metric" data-tone={tone}>
      <span>{label}</span>
      <strong>{formatValue(value)}</strong>
    </article>
  )
}

function AlphaRunbookPanel({
  steps,
  isLoading,
}: {
  steps: AlphaOperatorStepSnapshot[]
  isLoading: boolean
}) {
  return (
    <section className="alpha-operator-panel">
      <div className="alpha-operator-panel-title">
        <div>
          <h3>Operator Runbook</h3>
          <span>{steps.length ? `${steps.length} linked steps` : 'waiting for alpha snapshot'}</span>
        </div>
        <Route className="h-4 w-4 text-clay-muted" />
      </div>
      {isLoading && !steps.length ? <p className="alpha-operator-empty">Loading alpha runbook...</p> : null}
      <div className="alpha-runbook-list">
        {steps.map((step, index) => (
          <AlphaRunbookStep index={index + 1} key={step.step_id} step={step} />
        ))}
      </div>
    </section>
  )
}

function AlphaRunbookStep({ step, index }: { step: AlphaOperatorStepSnapshot; index: number }) {
  return (
    <article className="alpha-runbook-step" data-next={step.is_next ? 'true' : 'false'} data-tone={getTone(step.status)}>
      <div className="alpha-runbook-index">{String(index).padStart(2, '0')}</div>
      <div className="alpha-runbook-copy">
        <strong>{step.label}</strong>
        <p>{step.detail}</p>
        <span>{step.action_label}</span>
      </div>
      {step.is_next ? <Target className="h-4 w-4 text-clay-accent" /> : <StatusBadge label={step.status} />}
    </article>
  )
}

function AlphaEvidencePanel({ snapshot }: { snapshot: AlphaReadinessSnapshot | null }) {
  const evidence = snapshot?.evidence ?? null
  const evidenceItems = [
    ['Runtime', evidence?.runtime_state],
    ['Preflight', evidence?.preflight_status],
    ['Workspace', evidence?.workspace_posture],
    ['Signal state', evidence?.focused_signal_state],
    ['Lifecycle', evidence?.session_lifecycle_state],
    ['Demo records', evidence?.demo_record_count],
    ['Demo status', evidence?.demo_readiness_status],
    ['Review', evidence?.review_status],
    ['Release', evidence?.release_readiness_status],
  ] as const

  return (
    <section className="alpha-operator-panel">
      <div className="alpha-operator-panel-title">
        <div>
          <h3>Evidence Spine</h3>
          <span>Runtime, demo, review, validation, reliability</span>
        </div>
        <ClipboardCheck className="h-4 w-4 text-clay-muted" />
      </div>
      <div className="alpha-evidence-grid">
        {evidenceItems.map(([label, value]) => (
          <article className="alpha-evidence-cell" key={label}>
            <span>{label}</span>
            <strong>{formatValue(value)}</strong>
          </article>
        ))}
      </div>
    </section>
  )
}

function AlphaGatePanel({
  gates,
  isLoading,
}: {
  gates: AlphaReadinessGateSnapshot[]
  isLoading: boolean
}) {
  return (
    <section className="alpha-operator-panel alpha-gate-console">
      <div className="alpha-operator-panel-title">
        <div>
          <h3>Alpha Gates</h3>
          <span>{gates.length ? `${gates.length} readiness gates` : 'waiting for readiness gates'}</span>
        </div>
        <AlertTriangle className="h-4 w-4 text-clay-muted" />
      </div>
      {isLoading && !gates.length ? <p className="alpha-operator-empty">Loading readiness gates...</p> : null}
      <div className="alpha-gate-grid">
        {gates.map((gate) => (
          <article className="alpha-gate-card" data-tone={getTone(gate.status)} key={gate.gate_id}>
            <div>
              <strong>{gate.label}</strong>
              <p>{gate.detail}</p>
            </div>
            <div className="alpha-gate-meta">
              {gate.blocks_alpha ? <span>blocks alpha</span> : null}
              {gate.status === 'pass' ? <CheckCircle2 className="h-4 w-4 text-clay-success" /> : <StatusBadge label={gate.status} />}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
