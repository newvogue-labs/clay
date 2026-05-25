import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import { getAlphaOverview } from '../../api/alpha-client'
import type { AlphaReadinessSnapshot } from '../../types/alpha'

type AlphaReadinessState = {
  snapshot: AlphaReadinessSnapshot | null
  isLoading: boolean
  error: string | null
}

type AlphaReadinessController = AlphaReadinessState & {
  refresh: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected alpha readiness error'
}

export function useAlphaReadiness(): AlphaReadinessController {
  const [state, setState] = useState<AlphaReadinessState>({
    snapshot: null,
    isLoading: true,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getAlphaOverview()
      startTransition(() => {
        setState({
          snapshot,
          isLoading: false,
          error: null,
        })
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
  }, [refresh])

  return {
    ...state,
    refresh,
  }
}
