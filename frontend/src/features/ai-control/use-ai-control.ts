import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  applyAIAssignment as postApplyAIAssignment,
  getAIControlOverview,
  getAIControlStreamUrl,
  reviewAIAssignment as postReviewAIAssignment,
} from '../../api/ai-control-client'
import type { AIControlSnapshot, ReviewCardSnapshot } from '../../types/ai-control'

type AIControlState = {
  snapshot: AIControlSnapshot | null
  preview: ReviewCardSnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type AIControlController = AIControlState & {
  reviewAssignment: (roleId: string, modelId: string) => Promise<void>
  applyPendingReview: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected ai-control error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

export function useAIControl(): AIControlController {
  const [state, setState] = useState<AIControlState>({
    snapshot: null,
    preview: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getAIControlOverview()
      startTransition(() => {
        setState((current) => ({
          ...current,
          snapshot,
          preview: current.preview ?? snapshot.pending_review,
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

    const stream = new EventSourceCtor(getAIControlStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }

    stream.addEventListener('ai-control.ready', handleRefresh)
    stream.addEventListener('ai-control.refresh', handleRefresh)

    return () => {
      stream.close()
    }
  }, [refresh])

  async function runAction(task: () => Promise<void>): Promise<void> {
    startTransition(() => {
      setState((current) => ({ ...current, isActing: true, error: null }))
    })
    try {
      await task()
      await refresh()
    } catch (error: unknown) {
      startTransition(() => {
        setState((current) => ({
          ...current,
          error: getErrorMessage(error),
        }))
      })
    } finally {
      startTransition(() => {
        setState((current) => ({ ...current, isActing: false }))
      })
    }
  }

  async function reviewAssignment(roleId: string, modelId: string): Promise<void> {
    if (!confirmAction(`Подготовить review-card для ${roleId} -> ${modelId}?`)) {
      return
    }
    await runAction(async () => {
      const preview = await postReviewAIAssignment(roleId, modelId)
      startTransition(() => {
        setState((current) => ({ ...current, preview }))
      })
    })
  }

  async function applyPendingReview(): Promise<void> {
    const review = state.preview ?? state.snapshot?.pending_review ?? null
    if (!review) {
      return
    }
    if (!confirmAction(`Применить review ${review.review_id} для ${review.role_name}?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await postApplyAIAssignment(review.review_id)
      startTransition(() => {
        setState((current) => ({
          ...current,
          snapshot,
          preview: null,
        }))
      })
    })
  }

  return {
    ...state,
    reviewAssignment,
    applyPendingReview,
  }
}
