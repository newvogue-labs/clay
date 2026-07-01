import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  captureSessionFeedback as postCaptureSessionFeedback,
  getSessionReviewOverview,
  getSessionReviewStreamUrl,
} from '../../api/session-review-client'
import type { SessionReviewSnapshot } from '../../types/session-review'

type Filters = {
  pair: string | null
  strategy: string | null
  modelVersion: string | null
  confidenceBand: string | null
}

type SessionReviewState = {
  snapshot: SessionReviewSnapshot | null
  filters: Filters
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type SessionReviewController = SessionReviewState & {
  setPair: (pair: string | null) => void
  captureFeedback: (
    recordId: number,
    feedbackLabel: 'useful' | 'noise' | 'needs_follow_up',
  ) => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected session-review error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

export function useSessionReview(): SessionReviewController {
  const [state, setState] = useState<SessionReviewState>({
    snapshot: null,
    filters: {
      pair: null,
      strategy: null,
      modelVersion: null,
      confidenceBand: null,
    },
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getSessionReviewOverview(state.filters)
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
    const stream = new EventSourceCtor(getSessionReviewStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }
    stream.addEventListener('session-review.ready', handleRefresh)
    stream.addEventListener('session-review.refresh', handleRefresh)
    return () => {
      stream.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.filters.pair, state.filters.strategy, state.filters.modelVersion, state.filters.confidenceBand])

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

  function setPair(pair: string | null): void {
    startTransition(() => {
      setState((current) => ({
        ...current,
        filters: { ...current.filters, pair },
      }))
    })
  }

  async function captureFeedback(
    recordId: number,
    feedbackLabel: 'useful' | 'noise' | 'needs_follow_up',
  ): Promise<void> {
    if (!confirmAction(`Сохранить feedback ${feedbackLabel} для record ${recordId}?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await postCaptureSessionFeedback(recordId, feedbackLabel)
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  return {
    ...state,
    setPair,
    captureFeedback,
  }
}
