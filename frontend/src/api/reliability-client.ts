import type { ReliabilitySnapshot } from '../types/reliability'

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

export function getReliabilityOverview(): Promise<ReliabilitySnapshot> {
  return getJson<ReliabilitySnapshot>('/reliability/overview')
}

export function recheckReliability(): Promise<ReliabilitySnapshot> {
  return postJson<ReliabilitySnapshot>('/reliability/recheck', {})
}

export function getReliabilityStreamUrl(): string {
  return `${API_BASE_URL}/reliability/stream`
}
