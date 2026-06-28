import { startTransition, useCallback, useEffect, useEffectEvent, useState } from 'react'

import {
  confirmOverride as clientConfirmOverride,
  getTradingWorkspace,
  getTradingWorkspaceStreamUrl,
  revokeOverride as clientRevokeOverride,
  setTradingWorkspaceFocus,
} from '../../api/workspace-client'
import type { WorkspaceSnapshot } from '../../types/workspace'

type WorkspaceState = {
  snapshot: WorkspaceSnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type WorkspaceController = WorkspaceState & {
  focusSignal: (signalId: string, symbol: string) => Promise<void>
  focusMonitoringPair: (symbol: string) => Promise<void>
  refetch: () => void
  confirmOverride: () => Promise<void>
  revokeOverride: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected workspace error'
}

export function useWorkspace(): WorkspaceController {
  const [state, setState] = useState<WorkspaceState>({
    snapshot: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await getTradingWorkspace()
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

  const [refetchNonce, setRefetchNonce] = useState(0)
  const refetch = useCallback(() => setRefetchNonce((n) => n + 1), [])
  useEffect(() => {
    if (refetchNonce === 0) return
    void refresh()
  }, [refetchNonce])

  useEffect(() => {
    void refresh()

    const EventSourceCtor = globalThis.EventSource
    if (typeof EventSourceCtor !== 'function') {
      return
    }

    const stream = new EventSourceCtor(getTradingWorkspaceStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }

    stream.addEventListener('workspace.ready', handleRefresh)
    stream.addEventListener('workspace.refresh', handleRefresh)

    return () => {
      stream.close()
    }
  }, [refresh])

  async function runAction(task: () => Promise<unknown>): Promise<void> {
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

  async function focusSignal(signalId: string, symbol: string): Promise<void> {
    await runAction(async () => {
      await setTradingWorkspaceFocus(symbol, 'signal_click', signalId)
    })
  }

  async function focusMonitoringPair(symbol: string): Promise<void> {
    await runAction(async () => {
      await setTradingWorkspaceFocus(symbol, 'monitoring_click', null)
    })
  }

  async function confirmOverride(): Promise<void> {
    await runAction(async () => {
      await clientConfirmOverride()
    })
  }

  async function revokeOverride(): Promise<void> {
    await runAction(async () => {
      await clientRevokeOverride()
    })
  }

  return {
    ...state,
    focusSignal,
    focusMonitoringPair,
    confirmOverride,
    revokeOverride,
    refetch,
  }
}
