import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  getReliabilityOverview,
  getReliabilityStreamUrl,
  recheckReliability as postRecheckReliability,
} from '../../api/reliability-client'
import type { ReliabilitySnapshot } from '../../types/reliability'

type ReliabilityState = {
  snapshot: ReliabilitySnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type ReliabilityController = ReliabilityState & {
  recheck: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected reliability error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

export function useReliability(): ReliabilityController {
  const [state, setState] = useState<ReliabilityState>({
    snapshot: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getReliabilityOverview()
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
    const stream = new EventSourceCtor(getReliabilityStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }
    stream.addEventListener('reliability.ready', handleRefresh)
    stream.addEventListener('reliability.refresh', handleRefresh)
    return () => {
      stream.close()
    }
  }, [refresh])

  async function recheck(): Promise<void> {
    if (!confirmAction('Запустить повторную reliability-проверку?')) {
      return
    }
    startTransition(() => {
      setState((current) => ({ ...current, isActing: true, error: null }))
    })
    try {
      const snapshot = await postRecheckReliability()
      startTransition(() => {
        setState((current) => ({
          ...current,
          snapshot,
          isActing: false,
          error: null,
        }))
      })
    } catch (error: unknown) {
      startTransition(() => {
        setState((current) => ({
          ...current,
          isActing: false,
          error: getErrorMessage(error),
        }))
      })
    }
  }

  return {
    ...state,
    recheck,
  }
}
