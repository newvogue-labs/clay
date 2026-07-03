import {
  AlertTriangle,
  BarChart2,
  Calendar,
  CheckCircle2,
  FileClock,
  Filter,
  History,
  MessageSquare,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import { getOutcomeTone, getSeverityTone } from '../../helpers/tone'
import type {
  AIReviewCardSnapshot,
  FeedbackItemSnapshot,
  NormalizedAuditEventSnapshot,
  ReviewedTradeRecord,
  SessionReviewFilterOptions,
  SessionReviewSummary,
} from '../../types/session-review'
import { useSessionReview } from './use-session-review'

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

function getWinCount(records: ReviewedTradeRecord[]): number {
  return records.filter((record) => (record.pnl_pct ?? 0) > 0).length
}

function getBestPair(records: ReviewedTradeRecord[]): string {
  const resolved = records.filter((record) => record.pnl_pct !== null)
  if (resolved.length === 0) {
    return 'pending'
  }

  return resolved.reduce((best, record) => ((record.pnl_pct ?? 0) > (best.pnl_pct ?? 0) ? record : best)).symbol
}

export function SessionReviewPage() {
  const review = useSessionReview()
  const snapshot = review.snapshot
  const summary = snapshot?.summary ?? null
  const records = snapshot?.records ?? []
  const feedback = snapshot?.feedback ?? []
  const audit = snapshot?.audit ?? []
  const aiReviewCards = snapshot?.ai_review_cards ?? []

  return (
    <div aria-label="session-review-page" className="screen-page session-review-page" data-screen="session-review">
      <header className="screen-page-header review-command-header">
        <div>
          <h2>Session Review</h2>
          <p>Historical performance, signal evidence, feedback capture, and audit review</p>
        </div>
        <div className="review-command-row">
          <StatusBadge label={summary?.review_status ?? (review.isLoading ? 'loading' : 'unknown')} />
          <span>
            <Calendar className="h-3.5 w-3.5" />
            {formatDateTime(summary?.last_reviewed_at)}
          </span>
        </div>
      </header>

      {review.error ? (
        <section className="review-error-panel">
          <AlertTriangle className="h-4 w-4 text-clay-danger" />
          <span>{review.error}</span>
        </section>
      ) : null}

      <ReviewOverviewStrip
        isLoading={review.isLoading}
        records={records}
        summary={summary}
      />

      <div className="review-command-grid">
        <main className="review-main-stack">
          <ReviewFilterConsole
            filterOptions={snapshot?.filter_options ?? null}
            isLoading={review.isLoading}
            onSelectPair={review.setPair}
            selectedPair={review.filters.pair}
          />
          <ReviewRecordsConsole
            isActing={review.isActing}
            isLoading={review.isLoading}
            onCaptureFeedback={(recordId, feedbackLabel) => {
              void review.captureFeedback(recordId, feedbackLabel)
            }}
            records={records}
          />
        </main>

        <aside className="review-side-stack">
          <FeedbackLedger
            feedback={feedback}
            isLoading={review.isLoading}
            summary={summary}
          />
          <ReviewAuditConsole
            aiReviewCards={aiReviewCards}
            audit={audit}
            isLoading={review.isLoading}
          />
        </aside>
      </div>
    </div>
  )
}

type ReviewOverviewStripProps = {
  summary: SessionReviewSummary | null
  records: ReviewedTradeRecord[]
  isLoading: boolean
}

function ReviewOverviewStrip({ summary, records, isLoading }: ReviewOverviewStripProps) {
  const winCount = getWinCount(records)
  const resolvedCount = summary?.resolved_demo_records ?? 0
  const winRate = resolvedCount > 0 ? Math.round((winCount / resolvedCount) * 100) : 0

  return (
    <section className="review-overview-strip">
      <ReviewMetricCard
        icon={BarChart2}
        label="Total demo records"
        value={isLoading ? 'loading' : String(summary?.total_demo_records ?? 0)}
        detail={`Total demo records: ${summary?.total_demo_records ?? 0} / resolved: ${summary?.resolved_demo_records ?? 0}`}
      />
      <ReviewMetricCard
        icon={TrendingUp}
        label="Cumulative PnL"
        value={formatPct(summary?.cumulative_pnl_pct)}
        detail={`Win rate: ${winRate}%`}
      />
      <ReviewMetricCard
        icon={CheckCircle2}
        label="Best pair"
        value={getBestPair(records)}
        detail={`${records.length} records in current filter`}
      />
      <ReviewMetricCard
        icon={MessageSquare}
        label="Feedback count"
        value={String(summary?.feedback_count ?? 0)}
        detail={summary?.operator_message ?? 'Waiting for review summary.'}
      />
    </section>
  )
}

type ReviewMetricCardProps = {
  icon: typeof BarChart2
  label: string
  value: string
  detail: string
}

function ReviewMetricCard({ icon: Icon, label, value, detail }: ReviewMetricCardProps) {
  return (
    <div className="review-metric-card">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <Icon className="h-4 w-4 text-clay-accent" />
      <p>{detail}</p>
    </div>
  )
}

type ReviewFilterConsoleProps = {
  filterOptions: SessionReviewFilterOptions | null
  selectedPair: string | null
  isLoading: boolean
  onSelectPair: (pair: string | null) => void
}

function ReviewFilterConsole({
  filterOptions,
  selectedPair,
  isLoading,
  onSelectPair,
}: ReviewFilterConsoleProps) {
  return (
    <section className="review-filter-console" aria-label="review-filter-panel">
      <div className="review-panel-title">
        <div>
          <h3>Review Filters</h3>
          <span>{selectedPair ?? 'All Pairs'}</span>
        </div>
        <Filter className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? <div className="review-empty-line">Loading filters...</div> : null}
      {!isLoading && filterOptions ? (
        <div className="review-filter-row">
          <button
            aria-pressed={selectedPair === null}
            className={selectedPair === null ? 'is-active' : ''}
            onClick={() => onSelectPair(null)}
            type="button"
          >
            All Pairs
          </button>
          {filterOptions.pairs.map((pair) => (
            <button
              key={pair}
              aria-pressed={selectedPair === pair}
              className={selectedPair === pair ? 'is-active' : ''}
              onClick={() => onSelectPair(pair)}
              type="button"
            >
              {pair}
            </button>
          ))}
        </div>
      ) : null}

      {!isLoading && filterOptions ? (
        <div className="review-filter-meta">
          <span>Strategies: {filterOptions.strategies.join(', ') || 'any'}</span>
          <span>Models: {filterOptions.model_versions.join(', ') || 'any'}</span>
          <span>Confidence: {filterOptions.confidence_bands.join(', ') || 'any'}</span>
        </div>
      ) : null}
    </section>
  )
}

type ReviewRecordsConsoleProps = {
  records: ReviewedTradeRecord[]
  isLoading: boolean
  isActing: boolean
  onCaptureFeedback: (
    recordId: number,
    feedbackLabel: 'useful' | 'noise' | 'needs_follow_up',
  ) => void
}

function ReviewRecordsConsole({
  records,
  isLoading,
  isActing,
  onCaptureFeedback,
}: ReviewRecordsConsoleProps) {
  return (
    <section className="review-records-console" aria-label="review-records-panel">
      <div className="review-panel-title">
        <div>
          <h3>Reviewed Signals</h3>
          <span>{records.length} records in evidence table</span>
        </div>
        <History className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <div className="review-empty-line">Loading reviewed records...</div> : null}
      {!isLoading && records.length === 0 ? <div className="review-empty-line">No records matched the current filters.</div> : null}

      {!isLoading && records.length > 0 ? (
        <div className="review-record-table">
          <div className="review-record-head">
            <span>Signal</span>
            <span>Outcome</span>
            <span>Model</span>
            <span>PnL</span>
            <span>Feedback</span>
          </div>
          {records.map((record) => (
            <article className="review-record-row" key={record.record_id}>
              <div>
                <strong>{record.symbol}</strong>
                <span>{record.signal_id} / {record.strategy_mode}</span>
              </div>
              <div>
                <StatusBadge label={record.outcome_status} tone={getOutcomeTone(record.outcome_status)} />
                <span>{record.operator_action}</span>
              </div>
              <div>
                <strong>{record.model_version}</strong>
                <span>{record.confidence_band}</span>
              </div>
              <div className={(record.pnl_pct ?? 0) >= 0 ? 'is-positive' : 'is-negative'}>
                {(record.pnl_pct ?? 0) >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                <strong>{formatPct(record.pnl_pct)}</strong>
              </div>
              <div className="review-feedback-actions">
                <button
                  disabled={isActing}
                  onClick={() => onCaptureFeedback(record.record_id, 'useful')}
                  type="button"
                >
                  Mark Useful
                </button>
                <button
                  disabled={isActing}
                  onClick={() => onCaptureFeedback(record.record_id, 'noise')}
                  type="button"
                >
                  Mark Noise
                </button>
                <button
                  disabled={isActing}
                  onClick={() => onCaptureFeedback(record.record_id, 'needs_follow_up')}
                  type="button"
                >
                  Needs Follow-Up
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

type FeedbackLedgerProps = {
  summary: SessionReviewSummary | null
  feedback: FeedbackItemSnapshot[]
  isLoading: boolean
}

function FeedbackLedger({ summary, feedback, isLoading }: FeedbackLedgerProps) {
  return (
    <section className="review-feedback-ledger" aria-label="review-feedback-panel">
      <div className="review-panel-title">
        <div>
          <h3>Captured Feedback</h3>
          <span>Feedback count: {summary?.feedback_count ?? 0}</span>
        </div>
        <MessageSquare className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <div className="review-empty-line">Loading feedback history...</div> : null}
      {!isLoading && feedback.length === 0 ? <div className="review-empty-line">No feedback captured yet.</div> : null}
      {!isLoading
        ? feedback.map((item) => (
            <article className="review-feedback-card" key={item.feedback_id}>
              <div>
                <strong>{item.symbol}</strong>
                <StatusBadge label={item.feedback_label} />
              </div>
              <p>Label: {item.feedback_label}</p>
              <p>Outcome: {item.outcome_status ?? 'n/a'}</p>
              <p>Notes: {item.notes ?? 'none'}</p>
              <span>{formatDateTime(item.created_at)}</span>
            </article>
          ))
        : null}
    </section>
  )
}

type ReviewAuditConsoleProps = {
  audit: NormalizedAuditEventSnapshot[]
  aiReviewCards: AIReviewCardSnapshot[]
  isLoading: boolean
}

function ReviewAuditConsole({
  audit,
  aiReviewCards,
  isLoading,
}: ReviewAuditConsoleProps) {
  return (
    <section className="review-audit-console" aria-label="review-audit-panel">
      <div className="review-panel-title">
        <div>
          <h3>Audit and AI Review</h3>
          <span>{aiReviewCards.length} AI cards / {audit.length} events</span>
        </div>
        <FileClock className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? <div className="review-empty-line">Loading audit trail...</div> : null}
      {!isLoading
        ? aiReviewCards.map((card) => (
            <article className="review-ai-card" data-tone={getSeverityTone(card.severity)} key={card.card_id}>
              <div>
                <h4>{card.title}</h4>
                <StatusBadge label={card.severity} tone={getSeverityTone(card.severity)} />
              </div>
              <p>{card.summary}</p>
              {card.recommendations.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </article>
          ))
        : null}
      {!isLoading
        ? audit.map((event) => (
            <article className="review-audit-event" key={`${event.timestamp}-${event.event_type}`}>
              <div>
                <strong>{event.event_type}</strong>
                <StatusBadge label={event.severity} tone={getSeverityTone(event.severity)} />
              </div>
              <p>Module: {event.module}</p>
              <p>{event.explanation}</p>
              <span>{formatDateTime(event.timestamp)}</span>
            </article>
          ))
        : null}
    </section>
  )
}
