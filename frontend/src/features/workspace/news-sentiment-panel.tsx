import type {
  NewsContextItem,
  SentimentContextItem,
} from '../../types/workspace'

type NewsSentimentPanelProps = {
  news: NewsContextItem[]
  sentiment: SentimentContextItem[]
}

export function NewsSentimentPanel({
  news,
  sentiment,
}: NewsSentimentPanelProps) {
  return (
    <section>
      <h2>News and Sentiment</h2>
      <h3>News</h3>
      <ul>
        {news.length === 0 ? (
          <li>No focus-relevant news yet.</li>
        ) : (
          news.map((item) => (
            <li key={`${item.source_name}-${item.published_at}`}>
              <strong>{item.headline}</strong>
              {item.summary ? <div>{item.summary}</div> : null}
            </li>
          ))
        )}
      </ul>
      <h3>Sentiment</h3>
      <ul>
        {sentiment.length === 0 ? (
          <li>No focus-relevant sentiment snapshots yet.</li>
        ) : (
          sentiment.map((item) => (
            <li key={`${item.source_name}-${item.captured_at}`}>
              {item.sentiment_label} · score {item.sentiment_score}
            </li>
          ))
        )}
      </ul>
    </section>
  )
}
