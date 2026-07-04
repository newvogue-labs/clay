import type { LucideIcon } from 'lucide-react'
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  Database,
  FileText,
  PlusCircle,
  Search,
  Tags,
} from 'lucide-react'

import { StatusBadge } from '../../components/status-badge'
import { getPriorityTone } from '../../helpers/tone'
import type {
  KnowledgeItemSnapshot,
  KnowledgeSearchResultSnapshot,
  KnowledgeSummarySnapshot,
} from '../../types/knowledge'
import { useKnowledge } from './use-knowledge'

type KnowledgeSampleType = 'strategy_rule' | 'checklist' | 'observation' | 'note'

function formatScore(value: number): string {
  return value.toFixed(2)
}

function formatDate(value: string | null | undefined): string {
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

function formatBoolean(value: boolean): string {
  return value ? 'yes' : 'no'
}

export function KnowledgePage() {
  const knowledge = useKnowledge()
  const snapshot = knowledge.snapshot
  const summary = snapshot?.summary ?? null
  const recentItems = snapshot?.recent_items ?? []
  const searchResults = snapshot?.search_results ?? []

  return (
    <div aria-label="knowledge-page" className="screen-page knowledge-page" data-screen="knowledge">
      <header className="screen-page-header knowledge-command-header">
        <div>
          <h2>Knowledge Base</h2>
          <p>Strategy rules, checklists, observations, and advisory research retrieval</p>
        </div>
        <div className="knowledge-command-row">
          <StatusBadge label={summary?.retrieval_mode ?? (knowledge.isLoading ? 'loading' : 'unknown')} />
          <StatusBadge label={summary?.hot_path_dependency ? 'hot_path_linked' : 'advisory_only'} />
          <span>{summary ? `Items: ${summary.total_items}` : 'Items: pending'}</span>
        </div>
      </header>

      {knowledge.error ? (
        <section className="knowledge-error-panel">
          <AlertCircle className="h-4 w-4 text-clay-danger" />
          <span>{knowledge.error}</span>
        </section>
      ) : null}

      <KnowledgeOverviewStrip
        isLoading={knowledge.isLoading}
        recentItems={recentItems}
        searchResults={searchResults}
        summary={summary}
      />

      <div className="knowledge-command-grid">
        <main className="knowledge-main-stack">
          <KnowledgeSearchConsole
            isLoading={knowledge.isLoading}
            onQueryChange={knowledge.setQuery}
            onSearch={() => {
              void knowledge.runSearch()
            }}
            query={knowledge.query}
            searchResults={searchResults}
          />
          <KnowledgeResultsConsole
            isActing={knowledge.isActing}
            isLoading={knowledge.isLoading}
            onDeleteItem={(itemId) => { void knowledge.deleteItem(itemId) }}
            recentItems={recentItems}
            searchResults={searchResults}
          />
        </main>

        <aside className="knowledge-side-stack">
          <KnowledgeIngestConsole
            isActing={knowledge.isActing}
            isLoading={knowledge.isLoading}
            onAddSample={(sampleType) => {
              void knowledge.addSample(sampleType)
            }}
          />
          <KnowledgePolicyConsole
            isLoading={knowledge.isLoading}
            summary={summary}
          />
        </aside>
      </div>
    </div>
  )
}

type KnowledgeOverviewStripProps = {
  summary: KnowledgeSummarySnapshot | null
  recentItems: KnowledgeItemSnapshot[]
  searchResults: KnowledgeSearchResultSnapshot[]
  isLoading: boolean
}

function KnowledgeOverviewStrip({
  summary,
  recentItems,
  searchResults,
  isLoading,
}: KnowledgeOverviewStripProps) {
  return (
    <section className="knowledge-overview-strip">
      <KnowledgeMetricCard
        detail={`Total items: ${summary?.total_items ?? recentItems.length}`}
        icon={Database}
        label="Corpus size"
        value={isLoading ? 'loading' : String(summary?.total_items ?? recentItems.length)}
      />
      <KnowledgeMetricCard
        detail={`Total chunks: ${summary?.total_chunks ?? 0}`}
        icon={FileText}
        label="Chunks"
        value={String(summary?.total_chunks ?? 0)}
      />
      <KnowledgeMetricCard
        detail={`Retrieval mode: ${summary?.retrieval_mode ?? 'unknown'}`}
        icon={Search}
        label="Retrieval"
        value={summary?.retrieval_mode ?? 'pending'}
      />
      <KnowledgeMetricCard
        detail={`${searchResults.length} active result(s)`}
        icon={BookOpen}
        label="Search evidence"
        value={searchResults.length > 0 ? 'available' : 'idle'}
      />
    </section>
  )
}

type KnowledgeMetricCardProps = {
  icon: LucideIcon
  label: string
  value: string
  detail: string
}

function KnowledgeMetricCard({ icon: Icon, label, value, detail }: KnowledgeMetricCardProps) {
  return (
    <div className="knowledge-metric-card">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <Icon className="h-4 w-4" />
      <p>{detail}</p>
    </div>
  )
}

type KnowledgeSearchConsoleProps = {
  query: string
  searchResults: KnowledgeSearchResultSnapshot[]
  isLoading: boolean
  onQueryChange: (query: string) => void
  onSearch: () => void
}

function KnowledgeSearchConsole({
  query,
  searchResults,
  isLoading,
  onQueryChange,
  onSearch,
}: KnowledgeSearchConsoleProps) {
  return (
    <section>
      <div className="knowledge-panel-title">
        <div>
          <h3>Research Search</h3>
          <span>{searchResults.length} current result(s)</span>
        </div>
        <Search className="h-4 w-4 text-clay-accent" />
      </div>

      <div className="knowledge-search-form">
        <label>
          Search knowledge
          <input
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="momentum"
            type="text"
            value={query}
          />
        </label>
        <button disabled={isLoading} onClick={onSearch} type="button">
          <Search className="h-3.5 w-3.5" />
          Search Knowledge
        </button>
      </div>
    </section>
  )
}

type KnowledgeResultsConsoleProps = {
  recentItems: KnowledgeItemSnapshot[]
  searchResults: KnowledgeSearchResultSnapshot[]
  isLoading: boolean
  isActing: boolean
  onDeleteItem: (itemId: number) => void
}

function KnowledgeResultsConsole({
  recentItems,
  searchResults,
  isLoading,
  isActing,
  onDeleteItem,
}: KnowledgeResultsConsoleProps) {
  return (
    <section>
      <div className="knowledge-panel-title">
        <div>
          <h3>Knowledge Results</h3>
          <span>Recent corpus and active retrieval evidence</span>
        </div>
        <BookOpen className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? <p className="knowledge-empty-line">Loading knowledge results...</p> : null}

      {!isLoading ? (
        <div className="knowledge-results-grid">
          <div>
            <h4>Recent Items</h4>
            <div className="knowledge-item-list">
              {recentItems.length === 0 ? <p className="knowledge-empty-line">No knowledge items yet.</p> : null}
              {recentItems.map((item) => (
                <article className="knowledge-item-card" data-tone={getPriorityTone(item.priority)} key={item.item_id}>
                  <div>
                    <strong>{item.title}</strong>
                    <StatusBadge label={item.priority} tone={getPriorityTone(item.priority)} />
                  </div>
                  <p>{item.content_preview}</p>
                  <dl>
                    <div>
                      <dt>Category</dt>
                      <dd>{item.category}</dd>
                    </div>
                    <div>
                      <dt>Chunks</dt>
                      <dd>{item.chunk_count}</dd>
                    </div>
                    <div>
                      <dt>Updated</dt>
                      <dd>{formatDate(item.updated_at)}</dd>
                    </div>
                  </dl>
                  <button
                    className="knowledge-delete-btn"
                    disabled={isActing}
                    onClick={() => onDeleteItem(item.item_id)}
                    title={`Удалить «${item.title}»`}
                    type="button"
                  >
                    Delete
                  </button>
                  <div className="knowledge-tag-strip">
                    {item.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div>
            <h4>Search Results</h4>
            <div className="knowledge-search-result-list">
              {searchResults.length === 0 ? <p className="knowledge-empty-line">No search results for the current query.</p> : null}
              {searchResults.map((item) => (
                <article className="knowledge-search-result-card" key={`search-${item.item_id}`}>
                  <div>
                    <strong>{item.title}</strong>
                    <span>{formatScore(item.score)}</span>
                  </div>
                  <p>{item.matched_chunk}</p>
                  <p>{item.rationale}</p>
                  <div className="knowledge-tag-strip">
                    <span>{item.category}</span>
                    <span>{item.priority}</span>
                    {item.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

type KnowledgeIngestConsoleProps = {
  isLoading: boolean
  isActing: boolean
  onAddSample: (sampleType: KnowledgeSampleType) => void
}

function KnowledgeIngestConsole({
  isLoading,
  isActing,
  onAddSample,
}: KnowledgeIngestConsoleProps) {
  const disabled = isLoading || isActing
  const samples: Array<{ type: KnowledgeSampleType; label: string; icon: LucideIcon }> = [
    { type: 'strategy_rule', label: 'Add Strategy Rule', icon: FileText },
    { type: 'checklist', label: 'Add Checklist', icon: ClipboardList },
    { type: 'observation', label: 'Add Observation', icon: CheckCircle2 },
    { type: 'note', label: 'Add Note', icon: PlusCircle },
  ]

  return (
    <section>
      <div className="knowledge-panel-title">
        <div>
          <h3>Quick Ingest</h3>
          <span>Operator-reviewed sample capture</span>
        </div>
        <PlusCircle className="h-4 w-4 text-clay-accent" />
      </div>

      {isLoading ? (
        <p className="knowledge-empty-line">Loading quick ingest...</p>
      ) : (
        <div className="knowledge-ingest-grid">
          {samples.map(({ type, label, icon: Icon }) => (
            <button disabled={disabled} key={type} onClick={() => onAddSample(type)} type="button">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

type KnowledgePolicyConsoleProps = {
  summary: KnowledgeSummarySnapshot | null
  isLoading: boolean
}

function KnowledgePolicyConsole({ summary, isLoading }: KnowledgePolicyConsoleProps) {
  return (
    <section>
      <div className="knowledge-panel-title">
        <div>
          <h3>Retrieval Policy</h3>
          <span>Research stays outside realtime execution</span>
        </div>
        <Tags className="h-4 w-4 text-clay-muted" />
      </div>

      {isLoading ? (
        <p className="knowledge-empty-line">Loading retrieval policy...</p>
      ) : (
        <div className="knowledge-policy-list">
          <p>
            <span>Policy</span>
            <strong>{summary?.retrieval_policy ?? 'unknown'}</strong>
          </p>
          <p>
            <span>Hot path dependency</span>
            <strong>{summary ? formatBoolean(summary.hot_path_dependency) : 'unknown'}</strong>
          </p>
          <p>
            <span>Mode</span>
            <strong>{summary?.retrieval_mode ?? 'unknown'}</strong>
          </p>
          <div className="knowledge-operator-note">
            <p>{summary?.operator_message ?? 'Knowledge summary has not loaded yet.'}</p>
          </div>
        </div>
      )}
    </section>
  )
}
