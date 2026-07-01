import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  applyActivation as postApplyActivation,
  getValidationLabOverview,
  getValidationLabStreamUrl,
  reviewActivation as postReviewActivation,
  runValidation as postRunValidation,
} from '../../api/validation-lab-client'
import type { ActivationReviewSnapshot, ValidationLabSnapshot } from '../../types/validation-lab'

type ValidationLabState = {
  snapshot: ValidationLabSnapshot | null
  pendingReview: ActivationReviewSnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type ValidationLabController = ValidationLabState & {
  runReplay: (runType: 'strategy_replay' | 'model_comparison' | 'signal_quality') => Promise<void>
  reviewStrategyActivation: () => Promise<void>
  reviewModelActivation: () => Promise<void>
  applyActivation: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected validation-lab error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

export function useValidationLab(): ValidationLabController {
  const [state, setState] = useState<ValidationLabState>({
    snapshot: null,
    pendingReview: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getValidationLabOverview()
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
    const stream = new EventSourceCtor(getValidationLabStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }
    stream.addEventListener('validation-lab.ready', handleRefresh)
    stream.addEventListener('validation-lab.refresh', handleRefresh)
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

  async function runReplay(
    runType: 'strategy_replay' | 'model_comparison' | 'signal_quality',
  ): Promise<void> {
    if (!confirmAction(`Запустить ${runType} validation run?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await postRunValidation(runType, `${runType} replay`)
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  async function reviewStrategyActivation(): Promise<void> {
    if (!confirmAction('Подготовить activation review для strategy mode?')) {
      return
    }
    await runAction(async () => {
      const pendingReview = await postReviewActivation('strategy_mode', 'global-strategy', 'defensive')
      startTransition(() => {
        setState((current) => ({ ...current, pendingReview }))
      })
    })
  }

  async function reviewModelActivation(): Promise<void> {
    if (!confirmAction('Подготовить activation review для forecast model?')) {
      return
    }
    await runAction(async () => {
      const pendingReview = await postReviewActivation('model_assignment', 'forecast-model', 'forecast-lite-v1')
      startTransition(() => {
        setState((current) => ({ ...current, pendingReview }))
      })
    })
  }

  async function applyActivation(): Promise<void> {
    const review = state.pendingReview
    if (!review) {
      return
    }
    if (!confirmAction(`Применить activation review ${review.review_id}?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await postApplyActivation(review.review_id)
      startTransition(() => {
        setState((current) => ({ ...current, snapshot, pendingReview: null }))
      })
    })
  }

  return {
    ...state,
    runReplay,
    reviewStrategyActivation,
    reviewModelActivation,
    applyActivation,
  }
}
