import type { SessionReviewFilterOptions } from '../../types/session-review'

type ReviewFilterPanelProps = {
  filterOptions: SessionReviewFilterOptions | null
  selectedPair: string | null
  isLoading: boolean
  onSelectPair: (pair: string | null) => void
}

export function ReviewFilterPanel({
  filterOptions,
  selectedPair,
  isLoading,
  onSelectPair,
}: ReviewFilterPanelProps) {
  return (
    <section aria-label="review-filter-panel">
      <h3>Review Filters</h3>
      {isLoading ? <p>Loading filters...</p> : null}
      {!isLoading && filterOptions ? (
        <>
          <button
            aria-pressed={selectedPair === null}
            onClick={() => onSelectPair(null)}
            type="button"
          >
            All Pairs
          </button>
          {filterOptions.pairs.map((pair) => (
            <button
              key={pair}
              aria-pressed={selectedPair === pair}
              onClick={() => onSelectPair(pair)}
              type="button"
            >
              {pair}
            </button>
          ))}
        </>
      ) : null}
    </section>
  )
}
