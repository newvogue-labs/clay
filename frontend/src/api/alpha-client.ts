import type { AlphaReadinessSnapshot } from '../types/alpha'

const API_BASE_URL =
  import.meta.env.VITE_CLAY_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

export function getAlphaOverview(): Promise<AlphaReadinessSnapshot> {
  return getJson<AlphaReadinessSnapshot>('/alpha/overview')
}

