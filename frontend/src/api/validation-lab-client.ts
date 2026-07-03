import type { ActivationReviewSnapshot, ValidationLabSnapshot } from '../types/validation-lab'

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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

export function getValidationLabOverview(): Promise<ValidationLabSnapshot> {
  return getJson<ValidationLabSnapshot>('/validation-lab/overview')
}

export function runValidation(
  runType: 'strategy_replay' | 'model_comparison' | 'signal_quality',
  label: string,
): Promise<ValidationLabSnapshot> {
  return postJson<ValidationLabSnapshot>('/validation-lab/runs', {
    run_type: runType,
    label,
  })
}

export function reviewActivation(
  targetType: 'strategy_mode' | 'model_assignment',
  targetId: string,
  proposedValue: string,
): Promise<ActivationReviewSnapshot> {
  return postJson<ActivationReviewSnapshot>('/validation-lab/activation/review', {
    target_type: targetType,
    target_id: targetId,
    proposed_value: proposedValue,
  })
}

export function applyActivation(reviewId: string): Promise<ValidationLabSnapshot> {
  return postJson<ValidationLabSnapshot>('/validation-lab/activation/apply', {
    review_id: reviewId,
  })
}

export function discardActivation(reviewId: string): Promise<ValidationLabSnapshot> {
  return postJson<ValidationLabSnapshot>(`/validation-lab/activation/review/${reviewId}/discard`, {})
}

export function getValidationLabStreamUrl(): string {
  return `${API_BASE_URL}/validation-lab/stream`
}
