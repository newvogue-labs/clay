import { useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  Bot,
  BrainCircuit,
  CheckCircle2,
  FileSearch,
  LayoutGrid,
  MessageSquare,
  RefreshCcw,
  ShieldCheck,
  Terminal,
  TrendingUp,
  Zap,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import type {
  AIControlSnapshot,
  AIControlSummary,
  AssignmentSnapshot,
  ConflictSnapshot,
  FallbackSnapshot,
  ModelVersionSnapshot,
  ReviewCardSnapshot,
  RoleDefinitionSnapshot,
} from '../../types/ai-control'
import { useAIControl } from './use-ai-control'

type AIControlView = 'orchestration' | 'consensus' | 'terminal'

function formatTime(value: string | null | undefined): string {
  if (!value) {
    return '--:--:--'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleTimeString('en-GB', { hour12: false })
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return 'not reviewed'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function getRoleIcon(role: string): LucideIcon {
  const token = role.toLowerCase()
  if (token.includes('chief')) {
    return BrainCircuit
  }
  if (token.includes('forecast') || token.includes('market')) {
    return TrendingUp
  }
  if (token.includes('risk')) {
    return ShieldCheck
  }
  if (token.includes('news') || token.includes('sentiment')) {
    return MessageSquare
  }
  if (token.includes('review') || token.includes('audit')) {
    return FileSearch
  }
  return Bot
}

function getAssignmentTone(assignment: AssignmentSnapshot): 'success' | 'warning' | 'danger' | 'muted' {
  if (assignment.assignment_health === 'healthy') {
    return 'success'
  }
  if (assignment.assignment_health === 'degraded') {
    return 'danger'
  }
  if (assignment.assignment_health === 'review_required' || assignment.review_required) {
    return 'warning'
  }
  return 'muted'
}

function getConfidenceFromPenalty(penalty: number): number {
  return Math.max(0, Math.min(100, Math.round((1 - penalty) * 100)))
}

export function AIControlPage() {
  const [activeView, setActiveView] = useState<AIControlView>('orchestration')
  const aiControl = useAIControl()
  const snapshot = aiControl.snapshot
  const review = aiControl.preview ?? snapshot?.pending_review ?? null

  const assignmentStats = useMemo(() => {
    const assignments = snapshot?.assignments ?? []
    return {
      active: assignments.filter((assignment) => assignment.assignment_mode === 'active').length,
      healthy: assignments.filter((assignment) => assignment.assignment_health === 'healthy').length,
      reviewRequired: assignments.filter((assignment) => assignment.review_required).length,
      total: assignments.length,
    }
  }, [snapshot?.assignments])

  return (
    <div aria-label="ai-control-page" className="screen-page ai-control-page" data-screen="ai-control">
      <header className="screen-page-header ai-control-header">
        <div>
          <h2>AI Control</h2>
          <p>AI Console, role orchestration, model assignments, consensus, and review gates</p>
        </div>
        <div className="ai-control-command-row">
          <StatusBadge label={snapshot?.summary.overall_status ?? (aiControl.isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={review ? 'review_required' : 'review_clear'} />
          <span>Chief {snapshot?.summary.chief_agent_model ?? '...'}</span>
        </div>
      </header>

      <nav aria-label="AI control views" className="ai-control-tabs">
        <AIControlTab activeView={activeView} id="orchestration" label="Orchestration" onSelect={setActiveView} />
        <AIControlTab activeView={activeView} id="consensus" label="Consensus" onSelect={setActiveView} />
        <AIControlTab activeView={activeView} id="terminal" label="Terminal" onSelect={setActiveView} />
      </nav>

      {aiControl.error ? (
        <section className="ai-control-error-panel">
          <AlertTriangle className="h-4 w-4 text-clay-danger" />
          <span>AI control error: {aiControl.error}</span>
        </section>
      ) : null}

      {activeView === 'orchestration' ? (
        <OrchestrationView
          assignmentStats={assignmentStats}
          isActing={aiControl.isActing}
          isLoading={aiControl.isLoading}
          onApplyReview={() => {
            void aiControl.applyPendingReview()
          }}
          onReviewAssignment={(roleId, modelId) => {
            void aiControl.reviewAssignment(roleId, modelId)
          }}
          review={review}
          snapshot={snapshot}
        />
      ) : activeView === 'consensus' ? (
        <ConsensusView
          fallback={snapshot?.fallback ?? null}
          conflicts={snapshot?.conflicts ?? []}
          assignments={snapshot?.assignments ?? []}
          isLoading={aiControl.isLoading}
          review={review}
        />
      ) : (
        <TerminalView
          assignments={snapshot?.assignments ?? []}
          conflicts={snapshot?.conflicts ?? []}
          isLoading={aiControl.isLoading}
          review={review}
          summary={snapshot?.summary ?? null}
        />
      )}
    </div>
  )
}

type AIControlTabProps = {
  activeView: AIControlView
  id: AIControlView
  label: string
  onSelect: (view: AIControlView) => void
}

function AIControlTab({ activeView, id, label, onSelect }: AIControlTabProps) {
  return (
    <button
      aria-pressed={activeView === id}
      className={activeView === id ? 'is-active' : ''}
      onClick={() => {
        onSelect(id)
      }}
      type="button"
    >
      {label}
    </button>
  )
}

type OrchestrationViewProps = {
  snapshot: AIControlSnapshot | null
  review: ReviewCardSnapshot | null
  assignmentStats: {
    active: number
    healthy: number
    reviewRequired: number
    total: number
  }
  isLoading: boolean
  isActing: boolean
  onReviewAssignment: (roleId: string, modelId: string) => void
  onApplyReview: () => void
}

function OrchestrationView({
  snapshot,
  review,
  assignmentStats,
  isLoading,
  isActing,
  onReviewAssignment,
  onApplyReview,
}: OrchestrationViewProps) {
  return (
    <>
      <AIOverviewStrip
        assignmentStats={assignmentStats}
        isLoading={isLoading}
        summary={snapshot?.summary ?? null}
      />

      <div className="ai-orchestration-grid">
        <section className="ai-assignments-panel">
          <PanelTitle
            icon={BrainCircuit}
            kicker={`${assignmentStats.active} active roles`}
            subtitle="Operator-controlled role assignments with review before model changes."
            title="Model Assignments"
          />

          {isLoading ? (
            <div className="ai-empty-line">Loading assignments...</div>
          ) : (
            <div className="ai-assignment-grid">
              {(snapshot?.assignments ?? []).map((assignment) => (
                <AssignmentCard
                  assignment={assignment}
                  isActing={isActing}
                  key={assignment.role_id}
                  models={snapshot?.models ?? []}
                  onReviewAssignment={onReviewAssignment}
                />
              ))}
            </div>
          )}
        </section>

        <aside className="ai-side-stack">
          <ConflictFallbackPanel
            conflicts={snapshot?.conflicts ?? []}
            fallback={snapshot?.fallback ?? null}
            isLoading={isLoading}
          />
          <ReviewPanel
            isActing={isActing}
            isLoading={isLoading}
            onApply={onApplyReview}
            review={review}
          />
        </aside>
      </div>

      <RolesMatrix isLoading={isLoading} roles={snapshot?.roles ?? []} />
    </>
  )
}

type AIOverviewStripProps = {
  summary: AIControlSummary | null
  assignmentStats: {
    active: number
    healthy: number
    reviewRequired: number
    total: number
  }
  isLoading: boolean
}

function AIOverviewStrip({ summary, assignmentStats, isLoading }: AIOverviewStripProps) {
  const healthProgress = assignmentStats.total === 0 ? 0 : Math.round((assignmentStats.healthy / assignmentStats.total) * 100)
  const conflictProgress = Math.min((summary?.active_conflict_count ?? 0) * 25, 100)

  return (
    <div aria-label="ai control overview strip" className="ai-overview-grid">
      <AIMetric
        icon={BrainCircuit}
        label="Chief Agent"
        progress={summary?.overall_status === 'healthy' ? 100 : 62}
        tone={summary?.overall_status === 'healthy' ? 'success' : 'warning'}
        value={isLoading ? '...' : summary?.chief_agent_model ?? 'unassigned'}
      />
      <AIMetric
        icon={LayoutGrid}
        label="Assignments"
        progress={healthProgress}
        tone={assignmentStats.reviewRequired > 0 ? 'warning' : 'success'}
        value={isLoading ? '...' : `${assignmentStats.healthy}/${assignmentStats.total}`}
      />
      <AIMetric
        icon={AlertTriangle}
        label="Conflicts"
        progress={conflictProgress}
        tone={(summary?.active_conflict_count ?? 0) > 0 ? 'warning' : 'success'}
        value={isLoading ? '...' : `${summary?.active_conflict_count ?? 0}`}
      />
      <AIMetric
        icon={RefreshCcw}
        label="Fallback"
        progress={summary?.fallback_active ? 100 : 35}
        tone={summary?.fallback_active ? 'warning' : 'muted'}
        value={isLoading ? '...' : summary?.fallback_active ? 'active' : `${summary?.degraded_role_count ?? 0} degraded`}
      />
    </div>
  )
}

type AIMetricProps = {
  icon: LucideIcon
  label: string
  value: string
  progress: number
  tone: 'success' | 'warning' | 'danger' | 'muted'
}

function AIMetric({ icon: Icon, label, value, progress, tone }: AIMetricProps) {
  return (
    <div className="ai-metric-card">
      <div className={`ai-metric-icon is-${tone}`}>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="ai-metric-body">
        <div>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
        <div className="ai-metric-track">
          <span className={`is-${tone}`} style={{ width: `${progress}%` }} />
        </div>
      </div>
    </div>
  )
}

type AssignmentCardProps = {
  assignment: AssignmentSnapshot
  models: ModelVersionSnapshot[]
  isActing: boolean
  onReviewAssignment: (roleId: string, modelId: string) => void
}

function AssignmentCard({ assignment, models, isActing, onReviewAssignment }: AssignmentCardProps) {
  const Icon = getRoleIcon(assignment.role_name)
  const tone = getAssignmentTone(assignment)
  const alternatives = models.filter(
    (model) =>
      model.compatible_roles.includes(assignment.role_id) &&
      model.model_id !== assignment.model_id,
  )
  const confidence = getConfidenceFromPenalty(assignment.confidence_penalty)

  return (
    <article className={`ai-assignment-card is-${tone}`}>
      <div className="ai-assignment-card-header">
        <div className={`ai-role-icon is-${tone}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <h3>{assignment.role_name}</h3>
          <span>{assignment.provider} / {assignment.assignment_mode}</span>
        </div>
        <StatusBadge label={assignment.assignment_health} />
      </div>

      <div className="ai-current-model">
        <span>Current model</span>
        <strong>{assignment.model_display_name}</strong>
      </div>

      <p>{assignment.reason}</p>

      <div className="ai-confidence-row">
        <div>
          <span>Confidence after penalty</span>
          <strong>{confidence}%</strong>
        </div>
        <div className="ai-confidence-track">
          <span style={{ width: `${confidence}%` }} />
        </div>
      </div>

      <div className="ai-assignment-actions">
        {alternatives.length === 0 ? (
          <span>No compatible alternative staged</span>
        ) : (
          alternatives.map((model) => (
            <button
              disabled={isActing}
              key={`${assignment.role_id}-${model.model_id}`}
              onClick={() => {
                onReviewAssignment(assignment.role_id, model.model_id)
              }}
              title="Готовит review-карточку справа — текущая модель сменится только после Apply"
              type="button"
            >
              Stage {model.display_name}…
            </button>
          ))
        )}
      </div>
    </article>
  )
}

type ConflictFallbackPanelProps = {
  conflicts: ConflictSnapshot[]
  fallback: FallbackSnapshot | null
  isLoading: boolean
}

function ConflictFallbackPanel({ conflicts, fallback, isLoading }: ConflictFallbackPanelProps) {
  return (
    <section className="ai-conflict-panel">
      <PanelTitle
        icon={AlertTriangle}
        kicker={`${conflicts.length} active`}
        subtitle="Conflicts stay visible until the operator reviews the model posture."
        title="Conflicts and Fallback"
      />

      {isLoading || !fallback ? (
        <div className="ai-empty-line">Loading conflict state...</div>
      ) : (
        <>
          <div className="ai-fallback-card">
            <div>
              <StatusBadge label={fallback.fallback_active ? 'active' : 'inactive'} />
              <StatusBadge label={fallback.local_fallback_ready ? 'ready' : 'not_ready'} />
            </div>
            <p>{fallback.operator_message}</p>
            {fallback.degraded_roles.length > 0 ? (
              <span>Degraded roles: {fallback.degraded_roles.join(', ')}</span>
            ) : (
              <span>No degraded roles reported.</span>
            )}
          </div>

          <div className="ai-conflict-list">
            {conflicts.length === 0 ? (
              <div className="ai-empty-line">No active AI conflicts.</div>
            ) : (
              conflicts.map((conflict) => (
                <article className={`ai-conflict-card is-${conflict.severity}`} key={conflict.conflict_id}>
                  <div>
                    <strong>{conflict.title}</strong>
                    <StatusBadge label={conflict.severity} />
                  </div>
                  <p>{conflict.description}</p>
                  <span>Recommended action: {conflict.recommended_action}</span>
                </article>
              ))
            )}
          </div>
        </>
      )}
    </section>
  )
}

type ReviewPanelProps = {
  review: ReviewCardSnapshot | null
  isLoading: boolean
  isActing: boolean
  onApply: () => void
}

function ReviewPanel({ review, isLoading, isActing, onApply }: ReviewPanelProps) {
  return (
    <section className="ai-review-panel">
      <PanelTitle
        icon={CheckCircle2}
        kicker={review ? review.review_id : 'no pending review'}
        subtitle="Model changes are staged as visible review cards before apply."
        title="Review Card"
      />

      {isLoading ? (
        <div className="ai-empty-line">Loading review flow...</div>
      ) : !review ? (
        <div className="ai-empty-line">No pending review card.</div>
      ) : (
        <article className="ai-review-card">
          <div className="ai-review-card-header">
            <StatusBadge label={review.severity} />
            <span>{review.approval_required ? 'approval required' : 'approval optional'}</span>
          </div>
          <p>{review.summary}</p>
          <div className="ai-review-models">
            <div>
              <span>Current model</span>
              <strong>{review.current_model_id}</strong>
            </div>
            <div>
              <span>Proposed model</span>
              <strong>{review.proposed_model_name}</strong>
            </div>
          </div>
          <ReviewList title="Risks" items={review.risks} />
          <ReviewList title="Expected Effects" items={review.expected_effects} />
          <button
            disabled={isActing || review.blocks_apply}
            onClick={onApply}
            type="button"
          >
            Apply reviewed assignment
          </button>
        </article>
      )}
    </section>
  )
}

type ReviewListProps = {
  title: string
  items: string[]
}

function ReviewList({ title, items }: ReviewListProps) {
  return (
    <div className="ai-review-list">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

type RolesMatrixProps = {
  roles: RoleDefinitionSnapshot[]
  isLoading: boolean
}

function RolesMatrix({ roles, isLoading }: RolesMatrixProps) {
  return (
    <section className="ai-roles-panel">
      <PanelTitle
        icon={LayoutGrid}
        kicker={`${roles.length} role definitions`}
        subtitle="Role boundaries define what each model can read, produce, and explain."
        title="AI Roles"
      />

      {isLoading ? (
        <div className="ai-empty-line">Loading role model...</div>
      ) : (
        <div className="ai-role-grid">
          {roles.map((role) => {
            const Icon = getRoleIcon(role.role_name)
            return (
              <article className="ai-role-card" key={role.role_id}>
                <div>
                  <Icon className="h-4 w-4 text-clay-accent" />
                  <strong>{role.role_name}</strong>
                </div>
                <p>{role.responsibility}</p>
                <RoleTokenList label="Inputs" values={role.inputs} />
                <RoleTokenList label="Outputs" values={role.outputs} />
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

type RoleTokenListProps = {
  label: string
  values: string[]
}

function RoleTokenList({ label, values }: RoleTokenListProps) {
  return (
    <div className="ai-role-token-list">
      <span>{label}</span>
      <div>
        {values.map((value) => (
          <em key={value}>{value}</em>
        ))}
      </div>
    </div>
  )
}

type ConsensusViewProps = {
  conflicts: ConflictSnapshot[]
  assignments: AssignmentSnapshot[]
  fallback: FallbackSnapshot | null
  review: ReviewCardSnapshot | null
  isLoading: boolean
}

function ConsensusView({ conflicts, assignments, fallback, review, isLoading }: ConsensusViewProps) {
  const reviewedAssignments = assignments.filter((assignment) => assignment.review_required)

  return (
    <div className="ai-consensus-grid">
      <section className="ai-consensus-main">
        <PanelTitle
          icon={Zap}
          kicker={conflicts.length > 0 ? 'consensus review' : 'agreement'}
          subtitle="Consensus is represented through visible conflicts, assignment health, and fallback posture."
          title="Consensus State"
        />

        {isLoading ? (
          <div className="ai-empty-line">Loading consensus state...</div>
        ) : conflicts.length === 0 ? (
          <div className="ai-consensus-clear">
            <CheckCircle2 className="h-5 w-5 text-clay-success" />
            <strong>No active AI conflicts.</strong>
            <span>Assignments are aligned with the current role model.</span>
          </div>
        ) : (
          <div className="ai-consensus-conflicts">
            {conflicts.map((conflict) => (
              <article className="ai-consensus-conflict" key={conflict.conflict_id}>
                <div>
                  <AlertTriangle className="h-4 w-4 text-clay-warning" />
                  <strong>{conflict.title}</strong>
                  <StatusBadge label={conflict.severity} />
                </div>
                <p>{conflict.description}</p>
                <span>{conflict.recommended_action}</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <aside className="ai-consensus-side">
        <section>
          <PanelTitle
            icon={ShieldCheck}
            kicker="Fallback Posture"
            subtitle={fallback?.operator_message ?? 'Fallback state is loading.'}
            title="Fallback"
          />
          {fallback ? (
            <div className="ai-fallback-mode-card">
              <StatusBadge label={fallback.fallback_active ? 'active' : 'inactive'} />
              <StatusBadge label={fallback.local_fallback_ready ? 'ready' : 'not_ready'} />
              <span>{fallback.degraded_roles.length} degraded role(s)</span>
            </div>
          ) : (
            <div className="ai-empty-line">Loading fallback...</div>
          )}
        </section>

        <section>
          <PanelTitle
            icon={RefreshCcw}
            kicker={`${reviewedAssignments.length} role(s)`}
            subtitle="Assignments requiring review remain visible until the review card is applied."
            title="Review Queue"
          />
          <div className="ai-review-queue">
            {review ? (
              <article>
                <strong>{review.role_name}</strong>
                <span>{review.current_model_id} {'->'} {review.proposed_model_name}</span>
              </article>
            ) : reviewedAssignments.length === 0 ? (
              <div className="ai-empty-line">No staged assignment reviews.</div>
            ) : (
              reviewedAssignments.map((assignment) => (
                <article key={assignment.role_id}>
                  <strong>{assignment.role_name}</strong>
                  <span>{assignment.reason}</span>
                </article>
              ))
            )}
          </div>
        </section>
      </aside>
    </div>
  )
}

type TerminalViewProps = {
  summary: AIControlSummary | null
  assignments: AssignmentSnapshot[]
  conflicts: ConflictSnapshot[]
  review: ReviewCardSnapshot | null
  isLoading: boolean
}

function TerminalView({ summary, assignments, conflicts, review, isLoading }: TerminalViewProps) {
  const lines = [
    summary
      ? {
          source: 'CHIEF',
          tone: 'accent',
          message: `Chief Agent model ${summary.chief_agent_model}; status ${summary.overall_status}.`,
        }
      : null,
    ...assignments.slice(0, 5).map((assignment) => ({
      source: assignment.role_name.toUpperCase().slice(0, 10),
      tone: assignment.assignment_health === 'healthy' ? 'success' : 'warning',
      message: `${assignment.model_display_name}: ${assignment.reason}`,
    })),
    ...conflicts.map((conflict) => ({
      source: 'CONFLICT',
      tone: 'warning',
      message: `${conflict.title}: ${conflict.recommended_action}`,
    })),
    review
      ? {
          source: 'REVIEW',
          tone: 'accent',
          message: `${review.role_name}: staged ${review.current_model_id} -> ${review.proposed_model_name}.`,
        }
      : null,
  ].filter((line): line is { source: string; tone: string; message: string } => line !== null)

  return (
    <section className="ai-terminal-panel">
      <div className="ai-terminal-title">
        <div>
          <Terminal className="h-3.5 w-3.5 text-clay-accent" />
          <span>AI_ORCHESTRATOR_RUNNING</span>
        </div>
        <strong>Last review {formatDate(summary?.last_reviewed_at)}</strong>
      </div>

      <div className="ai-terminal-body">
        {isLoading ? (
          <p>Loading orchestrator stream...</p>
        ) : lines.length === 0 ? (
          <p>No AI control events yet.</p>
        ) : (
          lines.map((line, index) => (
            <p key={`${line.source}-${index}`}>
              <span>[{formatTime(new Date().toISOString())}]</span>
              <strong className={`is-${line.tone}`}>[{line.source}]</strong>
              {line.message}
            </p>
          ))
        )}
      </div>

      <div className="ai-terminal-input">
        <input aria-label="AI console command" placeholder="ENTER COMMAND..." readOnly type="text" />
        <span>READ ONLY</span>
      </div>
    </section>
  )
}

type PanelTitleProps = {
  icon: LucideIcon
  title: string
  kicker: string
  subtitle: string
}

function PanelTitle({ icon: Icon, title, kicker, subtitle }: PanelTitleProps) {
  return (
    <div className="ai-panel-title">
      <div>
        <span>{kicker}</span>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <Icon className="h-4 w-4 text-clay-accent" />
    </div>
  )
}
