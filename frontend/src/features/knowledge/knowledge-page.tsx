import { KnowledgeIngestPanel } from './knowledge-ingest-panel'
import { KnowledgeResultsPanel } from './knowledge-results-panel'
import { KnowledgeSearchPanel } from './knowledge-search-panel'
import { KnowledgeStateBanner } from './knowledge-state-banner'
import { useKnowledge } from './use-knowledge'

export function KnowledgePage() {
  const knowledge = useKnowledge()
  const snapshot = knowledge.snapshot

  return (
    <div aria-label="knowledge-page" className="screen-page" data-screen="knowledge">
      <KnowledgeStateBanner
        summary={snapshot?.summary ?? null}
        isLoading={knowledge.isLoading}
        error={knowledge.error}
      />
      <KnowledgeIngestPanel
        isLoading={knowledge.isLoading}
        isActing={knowledge.isActing}
        onAddSample={(sampleType) => {
          void knowledge.addSample(sampleType)
        }}
      />
      <KnowledgeSearchPanel
        query={knowledge.query}
        isLoading={knowledge.isLoading}
        onQueryChange={knowledge.setQuery}
        onSearch={() => {
          void knowledge.runSearch()
        }}
      />
      <KnowledgeResultsPanel
        recentItems={snapshot?.recent_items ?? []}
        searchResults={snapshot?.search_results ?? []}
        isLoading={knowledge.isLoading}
      />
    </div>
  )
}
