import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  applyPairReplacement as postApplyPairReplacement,
  completeSession as postCompleteSession,
  getSessionOverview,
  getSessionStreamUrl,
  pauseSession as postPauseSession,
  resumeSession as postResumeSession,
  reviewPairReplacement as postReviewPairReplacement,
  startSession as postStartSession,
} from '../../api/session-client'
import type {
  PairReplacementReviewSnapshot,
  SessionControlSnapshot,
} from '../../types/session-control'

type SessionControlState = {
  snapshot: SessionControlSnapshot | null
  replacementReview: PairReplacementReviewSnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type SessionControlController = SessionControlState & {
  startSession: () => Promise<void>
  pauseSession: () => Promise<void>
  resumeSession: () => Promise<void>
  completeSession: () => Promise<void>
  reviewReplacement: (proposedSymbol?: string) => Promise<void>
  applyReplacement: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected session-control error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

export function useSessionControl(): SessionControlController {
  const [state, setState] = useState<SessionControlState>({
    snapshot: null,
    replacementReview: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getSessionOverview()
      startTransition(() => {
        setState((current) => ({
          ...current,
          snapshot,
          replacementReview: current.replacementReview ?? snapshot.pending_pair_replacement,
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
    const stream = new EventSourceCtor(getSessionStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }
    stream.addEventListener('session.ready', handleRefresh)
    stream.addEventListener('session.refresh', handleRefresh)
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

  async function startSession(): Promise<void> {
    if (!confirmAction('Запустить новую session?')) {
      return
    }
    await runAction(async () => {
      const snapshot = await postStartSession()
      startTransition(() => {
        setState((current) => ({ ...current, snapshot, replacementReview: null }))
      })
    })
  }

  async function pauseSession(): Promise<void> {
    if (!confirmAction('Поставить session на паузу?')) {
      return
    }
    await runAction(async () => {
      const snapshot = await postPauseSession()
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  async function resumeSession(): Promise<void> {
    if (!confirmAction('Возобновить session?')) {
      return
    }
    await runAction(async () => {
      const snapshot = await postResumeSession()
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  async function completeSession(): Promise<void> {
    if (!confirmAction('Завершить session и перейти в review?')) {
      return
    }
    await runAction(async () => {
      const snapshot = await postCompleteSession()
      startTransition(() => {
        setState((current) => ({ ...current, snapshot, replacementReview: null }))
      })
    })
  }

  async function reviewReplacement(proposedSymbol?: string): Promise<void> {
    if (!confirmAction('Подготовить review для pair replacement?')) {
      return
    }
    await runAction(async () => {
      const replacementReview = await postReviewPairReplacement(proposedSymbol)
      startTransition(() => {
        setState((current) => ({ ...current, replacementReview }))
      })
    })
  }

  async function applyReplacement(): Promise<void> {
    const review = state.replacementReview ?? state.snapshot?.pending_pair_replacement ?? null
    if (!review) {
      return
    }
    if (!confirmAction(`Применить replacement ${review.current_symbol} -> ${review.proposed_symbol}?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await postApplyPairReplacement(review.review_id)
      startTransition(() => {
        setState((current) => ({ ...current, snapshot, replacementReview: null }))
      })
    })
  }

  return {
    ...state,
    startSession,
    pauseSession,
    resumeSession,
    completeSession,
    reviewReplacement,
    applyReplacement,
  }
}
