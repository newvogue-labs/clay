import type { AIControlSnapshot, ReviewCardSnapshot } from '../types/ai-control'

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

export function getAIControlOverview(): Promise<AIControlSnapshot> {
  return getJson<AIControlSnapshot>('/ai-control/overview')
}

export function reviewAIAssignment(roleId: string, modelId: string): Promise<ReviewCardSnapshot> {
  return postJson<ReviewCardSnapshot>('/ai-control/assignments/review', {
    role_id: roleId,
    model_id: modelId,
  })
}

export function applyAIAssignment(reviewId: string): Promise<AIControlSnapshot> {
  return postJson<AIControlSnapshot>('/ai-control/assignments/apply', {
    review_id: reviewId,
  })
}

export function getAIControlStreamUrl(): string {
  return `${API_BASE_URL}/ai-control/stream`
}
