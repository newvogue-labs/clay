import type {
  PairReplacementReviewSnapshot,
  SessionControlSnapshot,
} from '../types/session-control'

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

export function getSessionOverview(): Promise<SessionControlSnapshot> {
  return getJson<SessionControlSnapshot>('/session/overview')
}

export function startSession(): Promise<SessionControlSnapshot> {
  return postJson<SessionControlSnapshot>('/session/start', {})
}

export function pauseSession(): Promise<SessionControlSnapshot> {
  return postJson<SessionControlSnapshot>('/session/pause', {})
}

export function resumeSession(): Promise<SessionControlSnapshot> {
  return postJson<SessionControlSnapshot>('/session/resume', {})
}

export function completeSession(): Promise<SessionControlSnapshot> {
  return postJson<SessionControlSnapshot>('/session/complete', {})
}

export function closeReview(): Promise<SessionControlSnapshot> {
  return postJson<SessionControlSnapshot>('/session/review/close', {})
}

export function reviewPairReplacement(
  proposedSymbol?: string,
): Promise<PairReplacementReviewSnapshot> {
  return postJson<PairReplacementReviewSnapshot>('/session/replacement/review', {
    proposed_symbol: proposedSymbol ?? null,
  })
}

export function applyPairReplacement(reviewId: string): Promise<SessionControlSnapshot> {
  return postJson<SessionControlSnapshot>('/session/replacement/apply', {
    review_id: reviewId,
  })
}

export function getSessionStreamUrl(): string {
  return `${API_BASE_URL}/session/stream`
}
