import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  createKnowledgeItem as postCreateKnowledgeItem,
  deleteKnowledgeItem as apiDeleteKnowledgeItem,
  getKnowledgeOverview,
  getKnowledgeStreamUrl,
} from '../../api/knowledge-client'
import type { KnowledgeSnapshot } from '../../types/knowledge'

type KnowledgeState = {
  snapshot: KnowledgeSnapshot | null
  query: string
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type KnowledgeController = KnowledgeState & {
  setQuery: (query: string) => void
  runSearch: () => Promise<void>
  addSample: (sampleType: 'strategy_rule' | 'checklist' | 'observation' | 'note') => Promise<void>
  deleteItem: (itemId: number) => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected knowledge error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

function samplePayload(sampleType: 'strategy_rule' | 'checklist' | 'observation' | 'note') {
  if (sampleType === 'strategy_rule') {
    return {
      title: 'Momentum continuation rule',
      category: 'strategy_rule' as const,
      priority: 'high' as const,
      tags: ['momentum', 'trend'],
      content:
        'Use continuation entries only when higher timeframe structure supports the move. Avoid forcing entries against defensive posture.',
    }
  }
  if (sampleType === 'checklist') {
    return {
      title: 'Pre-entry checklist',
      category: 'checklist' as const,
      priority: 'high' as const,
      tags: ['checklist', 'entry'],
      content:
        'Check liquidity. Confirm invalidation. Confirm market freshness. Reject setups with degraded context.',
    }
  }
  if (sampleType === 'observation') {
    return {
      title: 'Operator observation',
      category: 'observation' as const,
      priority: 'medium' as const,
      tags: ['journal', 'observation'],
      content:
        'Late entries keep reducing edge when the pair is already extended after the first impulse candle.',
    }
  }
  return {
    title: 'Research note',
    category: 'note' as const,
    priority: 'low' as const,
    tags: ['note'],
    content:
      'Research notes are useful for review and planning, but they must not block the live signal pipeline.',
  }
}

export function useKnowledge(): KnowledgeController {
  const [state, setState] = useState<KnowledgeState>({
    snapshot: null,
    query: '',
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async (queryOverride?: string) => {
    startTransition(() => {
      setState((current) => ({ ...current, isLoading: true }))
    })
    try {
      const snapshot = await getKnowledgeOverview(queryOverride ?? state.query)
      startTransition(() => {
        setState((current) => ({
          ...current,
          snapshot,
          isLoading: false,
          error: null,
        }))
      })
    } catch (error: unknown) {
      startTransition(() => {
        setState((current) => ({
          ...current,
          isLoading: false,
          error: getErrorMessage(error),
        }))
      })
    }
  })

  useEffect(() => {
    void refresh()
    const EventSourceCtor = globalThis.EventSource
    if (typeof EventSourceCtor !== 'function') {
      return
    }
    const stream = new EventSourceCtor(getKnowledgeStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }
    stream.addEventListener('knowledge.refresh', handleRefresh)
    return () => {
      stream.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runAction(task: () => Promise<void>): Promise<void> {
    startTransition(() => {
      setState((current) => ({ ...current, isActing: true, error: null }))
    })
    try {
      await task()
      await refresh()
    } catch (error: unknown) {
      startTransition(() => {
        setState((current) => ({ ...current, error: getErrorMessage(error) }))
      })
    } finally {
      startTransition(() => {
        setState((current) => ({ ...current, isActing: false }))
      })
    }
  }

  function setQuery(query: string): void {
    startTransition(() => {
      setState((current) => ({ ...current, query }))
    })
  }

  async function runSearch(): Promise<void> {
    await refresh(state.query)
  }

  async function deleteItem(itemId: number): Promise<void> {
    if (!confirmAction(`Удалить knowledge item #${itemId}?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await apiDeleteKnowledgeItem(itemId)
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  async function addSample(
    sampleType: 'strategy_rule' | 'checklist' | 'observation' | 'note',
  ): Promise<void> {
    if (!confirmAction(`Добавить sample knowledge item: ${sampleType}?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await postCreateKnowledgeItem(samplePayload(sampleType))
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  return {
    ...state,
    setQuery,
    runSearch,
    deleteItem,
    addSample,
  }
}
