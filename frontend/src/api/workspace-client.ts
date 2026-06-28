import { getOperatorActor } from '../config/operator'
import type { WorkspaceSnapshot } from '../types/workspace'

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

export function getTradingWorkspace(): Promise<WorkspaceSnapshot> {
  return getJson<WorkspaceSnapshot>('/workspace/trading')
}

export function setTradingWorkspaceFocus(
  symbol: string,
  focusSource: string,
  signalId: string | null = null,
): Promise<{ focus_pair: WorkspaceSnapshot['focus_pair']; workspace_state: WorkspaceSnapshot['workspace_state'] }> {
  return postJson('/workspace/trading/focus', {
    symbol,
    focus_source: focusSource,
    signal_id: signalId,
  })
}

export function getTradingWorkspaceStreamUrl(): string {
  return `${API_BASE_URL}/workspace/trading/stream`
}

export async function requestOverride(reason: string): Promise<void> {
  await postJson('/workspace/trading/override/request', {
    actor: getOperatorActor(),
    reason,
  })
}

export async function confirmOverride(): Promise<void> {
  await postJson('/workspace/trading/override/confirm', {
    actor: getOperatorActor(),
  })
}

export async function revokeOverride(): Promise<void> {
  await postJson('/workspace/trading/override/revoke', {
    actor: getOperatorActor(),
  })
}
