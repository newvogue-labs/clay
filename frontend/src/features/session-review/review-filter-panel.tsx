import type { SessionReviewFilterOptions } from '../../types/session-review'

type ReviewFilterPanelProps = {
  filterOptions: SessionReviewFilterOptions | null
  selectedPair: string | null
  selectedStrategy: string | null
  selectedModelVersion: string | null
  selectedConfidenceBand: string | null
  isLoading: boolean
  onSelectPair: (pair: string | null) => void
  onSelectStrategy: (strategy: string | null) => void
  onSelectModelVersion: (modelVersion: string | null) => void
  onSelectConfidenceBand: (confidenceBand: string | null) => void
}

export function ReviewFilterPanel({
  filterOptions,
  selectedPair,
  selectedStrategy,
  selectedModelVersion,
  selectedConfidenceBand,
  isLoading,
  onSelectPair,
  onSelectStrategy,
  onSelectModelVersion,
  onSelectConfidenceBand,
}: ReviewFilterPanelProps) {
  return (
    <section aria-label="review-filter-panel">
      <h3>Review Filters</h3>
      {isLoading ? <p>Loading filters...</p> : null}
      {!isLoading && filterOptions ? (
        <>
          <div>
            <span>Pair</span>
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
          </div>
          <div>
            <span>Strategy</span>
            <button
              aria-pressed={selectedStrategy === null}
              onClick={() => onSelectStrategy(null)}
              type="button"
            >
              All
            </button>
            {filterOptions.strategies.map((s) => (
              <button
                key={s}
                aria-pressed={selectedStrategy === s}
                onClick={() => onSelectStrategy(s)}
                type="button"
              >
                {s}
              </button>
            ))}
          </div>
          <div>
            <span>Model</span>
            <button
              aria-pressed={selectedModelVersion === null}
              onClick={() => onSelectModelVersion(null)}
              type="button"
            >
              All
            </button>
            {filterOptions.model_versions.map((m) => (
              <button
                key={m}
                aria-pressed={selectedModelVersion === m}
                onClick={() => onSelectModelVersion(m)}
                type="button"
              >
                {m}
              </button>
            ))}
          </div>
          <div>
            <span>Confidence</span>
            <button
              aria-pressed={selectedConfidenceBand === null}
              onClick={() => onSelectConfidenceBand(null)}
              type="button"
            >
              All
            </button>
            {filterOptions.confidence_bands.map((c) => (
              <button
                key={c}
                aria-pressed={selectedConfidenceBand === c}
                onClick={() => onSelectConfidenceBand(c)}
                type="button"
              >
                {c}
              </button>
            ))}
          </div>
          <div>
            <span>Time</span>
            <span>Unimplemented</span>
          </div>
        </>
      ) : null}
    </section>
  )
}
