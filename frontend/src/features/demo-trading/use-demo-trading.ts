import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  getDemoTradingOverview,
  getDemoTradingStreamUrl,
  ingestDemoResult as postIngestDemoResult,
  logCurrentDemoTrade as postLogCurrentDemoTrade,
} from '../../api/demo-trading-client'
import type { DemoTradeRecordSnapshot, DemoTradingSnapshot } from '../../types/demo-trading'

type DemoTradingState = {
  snapshot: DemoTradingSnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type DemoTradingController = DemoTradingState & {
  logTrade: (operatorAction: DemoTradeRecordSnapshot['operator_action']) => Promise<void>
  markResult: (recordId: number, resultProfile: 'win' | 'flat' | 'loss') => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected demo-trading error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

function resultProfileToPnl(resultProfile: 'win' | 'flat' | 'loss'): number {
  if (resultProfile === 'win') {
    return 2.4
  }
  if (resultProfile === 'loss') {
    return -1.6
  }
  return 0
}

export function useDemoTrading(): DemoTradingController {
  const [state, setState] = useState<DemoTradingState>({
    snapshot: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getDemoTradingOverview()
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

    const stream = new EventSourceCtor(getDemoTradingStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }
    stream.addEventListener('demo.ready', handleRefresh)
    stream.addEventListener('demo.refresh', handleRefresh)

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

  async function logTrade(
    operatorAction: DemoTradeRecordSnapshot['operator_action'],
  ): Promise<void> {
    if (!confirmAction(`Зафиксировать demo action: ${operatorAction}?`)) {
      return
    }
    await runAction(async () => {
      const snapshot = await postLogCurrentDemoTrade(operatorAction)
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  async function markResult(
    recordId: number,
    resultProfile: 'win' | 'flat' | 'loss',
  ): Promise<void> {
    if (!confirmAction(`Загрузить demo result (${resultProfile}) для record ${recordId}?`)) {
      return
    }
    const pnlPct = resultProfileToPnl(resultProfile)
    await runAction(async () => {
      const snapshot = await postIngestDemoResult(recordId, pnlPct, {
        entryPrice: 100,
        exitPrice: 100 + pnlPct,
        externalTradeId: `demo-${recordId}-${resultProfile}`,
      })
      startTransition(() => {
        setState((current) => ({ ...current, snapshot }))
      })
    })
  }

  return {
    ...state,
    logTrade,
    markResult,
  }
}
