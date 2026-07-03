import type { ConfigsSnapshot } from '../types/settings'

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

export function getConfigs(): Promise<ConfigsSnapshot> {
  return getJson<ConfigsSnapshot>('/configs')
}

export function applyConfig(
  scope: string,
  config: Record<string, unknown>,
): Promise<{ scope: string; config: Record<string, unknown> }> {
  return postJson<{ scope: string; config: Record<string, unknown> }>(`/configs/${scope}`, { config })
}

export function restoreConfig(
  scope: string,
): Promise<{ scope: string; config: Record<string, unknown>; restored_from?: string }> {
  return postJson<{ scope: string; config: Record<string, unknown>; restored_from?: string }>(
    `/configs/${scope}/restore`,
    {},
  )
}

export function getConfigsStreamUrl(): string {
  return `${API_BASE_URL}/events/stream`
}
