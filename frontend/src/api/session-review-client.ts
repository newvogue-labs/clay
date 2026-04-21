import type { SessionReviewSnapshot } from '../types/session-review'

const API_BASE_URL =
  import.meta.env.VITE_CLAY_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

async function postJson<T>(path: string, body: object): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

export function getSessionReviewOverview(
  filters: {
    pair?: string | null
    strategy?: string | null
    modelVersion?: string | null
    confidenceBand?: string | null
  } = {},
): Promise<SessionReviewSnapshot> {
  const params = new URLSearchParams()
  if (filters.pair) params.set('pair', filters.pair)
  if (filters.strategy) params.set('strategy', filters.strategy)
  if (filters.modelVersion) params.set('model_version', filters.modelVersion)
  if (filters.confidenceBand) params.set('confidence_band', filters.confidenceBand)
  const query = params.toString()
  return getJson<SessionReviewSnapshot>(`/session-review/overview${query ? `?${query}` : ''}`)
}

export function captureSessionFeedback(
  recordId: number,
  feedbackLabel: 'useful' | 'noise' | 'needs_follow_up',
  notes: string | null = null,
): Promise<SessionReviewSnapshot> {
  return postJson<SessionReviewSnapshot>('/session-review/feedback', {
    record_id: recordId,
    feedback_label: feedbackLabel,
    notes,
  })
}

export function getSessionReviewStreamUrl(): string {
  return `${API_BASE_URL}/session-review/stream`
}
