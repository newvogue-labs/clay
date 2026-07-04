import type { KnowledgeSnapshot } from '../types/knowledge'

const API_BASE_URL =
  import.meta.env.VITE_CLAY_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
  })
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

export function getKnowledgeOverview(query: string | null = null): Promise<KnowledgeSnapshot> {
  const params = new URLSearchParams()
  if (query && query.trim()) {
    params.set('query', query.trim())
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return getJson<KnowledgeSnapshot>(`/knowledge/overview${suffix}`)
}

export function createKnowledgeItem(payload: {
  title: string
  category: 'note' | 'strategy_rule' | 'checklist' | 'observation'
  priority: 'low' | 'medium' | 'high'
  tags: string[]
  content: string
  sourceType?: string
}): Promise<KnowledgeSnapshot> {
  return postJson<KnowledgeSnapshot>('/knowledge/items', {
    title: payload.title,
    category: payload.category,
    priority: payload.priority,
    tags: payload.tags,
    content: payload.content,
    source_type: payload.sourceType ?? 'manual',
  })
}

export function deleteKnowledgeItem(itemId: number): Promise<KnowledgeSnapshot> {
  return deleteJson<KnowledgeSnapshot>(`/knowledge/items/${itemId}`)
}

export function getKnowledgeStreamUrl(): string {
  return `${API_BASE_URL}/knowledge/stream`
}
