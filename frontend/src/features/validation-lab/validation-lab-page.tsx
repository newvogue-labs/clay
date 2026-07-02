import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  BarChart2,
  CheckCircle2,
  FileCheck2,
  FlaskConical,
  GitCompareArrows,
  PlayCircle,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import type {
  ActivationReviewSnapshot,
  ValidationLabSummary,
  ValidationRunSnapshot,
} from '../../types/validation-lab'
import { useValidationLab } from './use-validation-lab'

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

function formatSignedPct(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'pending'
  }

  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatRatioPct(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'pending'
  }

  return `${Math.round(value * 100)}%`
}

function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'pending'
  }

  return `${Math.round(value * 100)}/100`
}

function getReviewTone(severity: ActivationReviewSnapshot['severity']): 'success' | 'warning' | 'danger' | 'muted' {
  if (severity === 'critical') {
    return 'danger'
  }
  if (severity === 'warning') {
    return 'warning'
  }
  if (severity === 'info') {
    return 'success'
  }
  return 'muted'
}

function formatEvidenceValue(value: unknown): string {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'boolean') {
    return String(value)
  }
  if (value === null || value === undefined) {
    return 'n/a'
  }
  return JSON.stringify(value)
}

export function ValidationLabPage() {
  const validation = useValidationLab()
  const snapshot = validation.snapshot
  const summary = snapshot?.summary ?? null
  const runs = snapshot?.runs ?? []
  const reviews = snapshot?.activation_reviews ?? []
  const activeReview = validation.pendingReview ?? null

  return (
    <div aria-label="validation-lab-page" className="screen-page validation-lab-page" data-screen="validation-lab">
      <header className="screen-page-header validation-command-header">
        <div>
          <h2>Validation Lab</h2>
          <p>Replay evidence, strategy validation, model comparisons, and staged activation review</p>
        </div>
        <div className="validation-command-row">
          <StatusBadge label={summary?.activation_review_status ?? (validation.isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={summary?.replay_ready ? 'replay_ready' : 'replay_pending'} />
          <span>Runs {summary?.total_runs ?? 0}</span>
        </div>
      </header>

      {validation.error ? (
        <section className="validation-error-panel">
          <AlertTriangle className="h-4 w-4 text-clay-danger" />
          <span>{validation.error}</span>
        </section>
      ) : null}

      <ValidationOverviewStrip
        isLoading={validation.isLoading}
        runs={runs}
        summary={summary}
      />

      <div className="validation-command-grid">
        <main className="validation-main-stack">
          <ReplayActionConsole
            isActing={validation.isActing}
            isLoading={validation.isLoading}
            onReviewModelActivation={() => {
              void validation.reviewModelActivation()
            }}
            onReviewStrategyActivation={() => {
              void validation.reviewStrategyActivation()
            }}
            onRunReplay={(runType) => {
              void validation.runReplay(runType)
            }}
          />
          <ReplayRunsConsole
            isLoading={validation.isLoading}
            runs={runs}
          />
        </main>

        <aside className="validation-side-stack">
          <ActivationReviewConsole
            isActing={validation.isActing}
            isLoading={validation.isLoading}
            onApply={() => {
              void validation.applyActivation()
            }}
            onDiscard={(reviewId) => {
              void validation.discardActivation(reviewId)
            }}
            pendingReview={activeReview}
            reviews={reviews}
          />
          <ValidationReadinessConsole
            isLoading={validation.isLoading}
            summary={summary}
          />
        </aside>
      </div>
    </div>
  )
}

type ValidationOverviewStripProps = {
  summary: ValidationLabSummary | null
  runs: ValidationRunSnapshot[]
  isLoading: boolean
}

function ValidationOverviewStrip({ summary, runs, isLoading }: ValidationOverviewStripProps) {
  const latestRun = runs[0] ?? null

  return (
    <section className="validation-overview-strip">
      <ValidationMetricCard
        detail={summary?.operator_message ?? 'Validation summary is not available yet.'}
        icon={FlaskConical}
        label="Replay state"
        value={isLoading ? 'loading' : summary?.replay_ready ? 'ready' : 'waiting'}
      />
      <ValidationMetricCard
        detail={`Total runs: ${summary?.total_runs ?? runs.length}`}
        icon={BarChart2}
        label="Total runs"
        value={String(summary?.total_runs ?? runs.length)}
      />
      <ValidationMetricCard
        detail={latestRun ? `Net PnL: ${formatSignedPct(latestRun.net_pnl_pct)}` : 'Run replay to collect evidence.'}
        icon={TrendingUp}
        label="Latest win rate"
        value={latestRun ? formatRatioPct(latestRun.win_rate) : 'pending'}
      />
      <ValidationMetricCard
        detail={`Staged reviews: ${summary?.staged_review_count ?? 0}`}
        icon={ShieldCheck}
        label="Activation review"
        value={summary?.activation_review_status ?? 'collecting'}
      />
    </section>
  )
}

type ValidationMetricCardProps = {
  icon: LucideIcon
  label: string
  value: string
  detail: string
}

function ValidationMetricCard({ icon: Icon, label, value, detail }: ValidationMetricCardProps) {
  return (
    <div className="validation-metric-card">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <Icon className="h-4 w-4 text-clay-accent" />
      <p>{detail}</p>
    </div>
  )
}

type ReplayActionConsoleProps = {
  isLoading: boolean
  isActing: boolean
  onRunReplay: (runType: 'strategy_replay' | 'model_comparison' | 'signal_quality') => void
  onReviewStrategyActivation: () => void
  onReviewModelActivation: () => void
}

function ReplayActionConsole({
  isLoading,
  isActing,
  onRunReplay,
  onReviewStrategyActivation,
  onReviewModelActivation,
}: ReplayActionConsoleProps) {
  const disabled = isLoading || isActing

  return (
    <section className="validation-action-console" aria-label="validation-actions-panel">
      <div className="validation-panel-title">
        <div>
          <h3>Replay and Activation Actions</h3>
          <span>Run evidence before staged changes become applyable.</span>
        </div>
        <PlayCircle className="h-4 w-4 text-clay-accent" />
      </div>

      <div className="validation-action-grid">
        <button disabled={disabled} onClick={() => onRunReplay('strategy_replay')} type="button">
          <PlayCircle className="h-3.5 w-3.5" />
          Run Strategy Replay
        </button>
        <button disabled={disabled} onClick={() => onRunReplay('model_comparison')} type="button">
          <GitCompareArrows className="h-3.5 w-3.5" />
          Run Model Comparison
        </button>
        <button disabled={disabled} onClick={() => onRunReplay('signal_quality')} type="button">
          <FileCheck2 className="h-3.5 w-3.5" />
          Run Signal Quality Replay
        </button>
        <button disabled={disabled} onClick={onReviewStrategyActivation} type="button">
          <ShieldCheck className="h-3.5 w-3.5" />
          Review Strategy Activation
        </button>
        <button disabled={disabled} onClick={onReviewModelActivation} type="button">
          <Sparkles className="h-3.5 w-3.5" />
          Review Model Activation
        </button>
      </div>
    </section>
  )
}

type ReplayRunsConsoleProps = {
  runs: ValidationRunSnapshot[]
  isLoading: boolean
}

function ReplayRunsConsole({ runs, isLoading }: ReplayRunsConsoleProps) {
  return (
    <section className="validation-runs-console" aria-label="validation-runs-panel">
      <div className="validation-panel-title">
        <div>
          <h3>Replay Runs</h3>
          <span>{runs.length} evidence runs</span>
        </div>
        <BarChart2 className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <div className="validation-empty-line">Loading validation runs...</div> : null}
      {!isLoading && runs.length === 0 ? <div className="validation-empty-line">No validation runs yet.</div> : null}
      {!isLoading && runs.length > 0 ? (
        <div className="validation-run-table">
          <div className="validation-run-head">
            <span>Run</span>
            <span>Strategy / Model</span>
            <span>Quality</span>
            <span>Risk</span>
          </div>
          {runs.map((run) => (
            <article className="validation-run-row" key={run.run_id}>
              <div>
                <strong>{run.label}</strong>
                <span>Type: {run.run_type}</span>
                <span>{formatDateTime(run.created_at)}</span>
              </div>
              <div>
                <strong>{run.strategy_mode}</strong>
                <span>{run.model_version}</span>
                <span>{formatDateTime(run.period_start)} to {formatDateTime(run.period_end)}</span>
              </div>
              <div>
                <strong>{formatRatioPct(run.win_rate)} win rate</strong>
                <span>Trades: {run.trades_simulated}</span>
                <span>Decision quality: {formatScore(run.decision_quality_score)}</span>
              </div>
              <div className={run.net_pnl_pct >= 0 ? 'is-positive' : 'is-negative'}>
                {run.net_pnl_pct >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                <strong>{formatSignedPct(run.net_pnl_pct)}</strong>
                <span>Max drawdown: {formatSignedPct(-Math.abs(run.max_drawdown_pct))}</span>
              </div>
              <p>{run.summary}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

type ActivationReviewConsoleProps = {
  pendingReview: ActivationReviewSnapshot | null
  reviews: ActivationReviewSnapshot[]
  isLoading: boolean
  isActing: boolean
  onApply: () => void
  onDiscard: (reviewId: string) => void
}

function ActivationReviewConsole({
  pendingReview,
  reviews,
  isLoading,
  isActing,
  onApply,
  onDiscard,
}: ActivationReviewConsoleProps) {
  return (
    <section className="validation-review-console" aria-label="activation-review-panel">
      <div className="validation-panel-title">
        <div>
          <h3>Activation Reviews</h3>
          <span>{pendingReview ? 'Pending review requires operator apply.' : `${reviews.length} stored reviews`}</span>
        </div>
        <ShieldCheck className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? <div className="validation-empty-line">Loading activation reviews...</div> : null}
      {!isLoading && pendingReview ? (
        <ReviewCard
          isPending
          isActing={isActing}
          onApply={onApply}
          onDiscard={onDiscard}
          review={pendingReview}
        />
      ) : null}
      {!isLoading && !pendingReview && reviews.length === 0 ? (
        <div className="validation-empty-line">No activation reviews staged yet.</div>
      ) : null}
      {!isLoading
        ? reviews.map((review) => (
            <ReviewCard
              isActing={isActing}
              key={review.review_id}
              onDiscard={onDiscard}
              review={review}
            />
          ))
        : null}
    </section>
  )
}

type ReviewCardProps = {
  review: ActivationReviewSnapshot
  isActing: boolean
  isPending?: boolean
  onApply?: () => void
  onDiscard?: (reviewId: string) => void
}

function ReviewCard({ review, isActing, isPending = false, onApply, onDiscard }: ReviewCardProps) {
  const canDiscard = review.status !== 'applied'
  return (
    <article className="validation-review-card" data-tone={getReviewTone(review.severity)}>
      <div>
        <h4>{isPending ? 'Pending Review' : review.target_type}</h4>
        <StatusBadge label={review.severity} />
      </div>
      <p>{review.summary}</p>
      <p>Status: {review.status}</p>
      <p>Severity: {review.severity}</p>
      <dl>
        <div>
          <dt>Current</dt>
          <dd>{review.current_value}</dd>
        </div>
        <div>
          <dt>Proposed</dt>
          <dd>{review.proposed_value}</dd>
        </div>
      </dl>
      {Object.entries(review.evidence).length > 0 ? (
        <div className="validation-evidence-list">
          {Object.entries(review.evidence).map(([key, value]) => (
            <span key={key}>{key}: {formatEvidenceValue(value)}</span>
          ))}
        </div>
      ) : null}
      <div className="validation-review-actions">
        {isPending && onApply ? (
          <button disabled={isActing} onClick={onApply} type="button">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Apply Activation Review
          </button>
        ) : null}
        {canDiscard && onDiscard ? (
          <button disabled={isActing} onClick={() => onDiscard(review.review_id)} type="button">
            <ThumbsDown className="h-3.5 w-3.5" />
            Discard
          </button>
        ) : null}
      </div>
    </article>
  )
}

type ValidationReadinessConsoleProps = {
  summary: ValidationLabSummary | null
  isLoading: boolean
}

function ValidationReadinessConsole({ summary, isLoading }: ValidationReadinessConsoleProps) {
  return (
    <section className="validation-readiness-console">
      <div className="validation-panel-title">
        <div>
          <h3>Readiness Gate</h3>
          <span>{summary?.activation_review_status ?? 'collecting'}</span>
        </div>
        <FlaskConical className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? <div className="validation-empty-line">Loading readiness gate...</div> : null}
      {!isLoading && summary ? (
        <div className="validation-readiness-list">
          <p>
            <span>Replay ready</span>
            <strong>{String(summary.replay_ready)}</strong>
          </p>
          <p>
            <span>Activation review status</span>
            <strong>{summary.activation_review_status}</strong>
          </p>
          <p>
            <span>Total runs</span>
            <strong>{summary.total_runs}</strong>
          </p>
          <p>
            <span>Staged reviews</span>
            <strong>{summary.staged_review_count}</strong>
          </p>
        </div>
      ) : null}
    </section>
  )
}
