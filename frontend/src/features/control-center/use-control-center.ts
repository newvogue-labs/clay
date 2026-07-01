import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  getControlCenterOverview,
  getControlCenterStreamUrl,
  restoreConfig as postRestoreConfig,
  runIngestionCycle as postRunIngestionCycle,
  runServiceAction as postServiceAction,
  transitionRuntime as postRuntimeTransition,
} from '../../api/client'
import type { ControlCenterSnapshot } from '../../types/control-center'
import type { RuntimeState, ServiceAction } from '../../types/runtime'

type ControlCenterState = {
  snapshot: ControlCenterSnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type ControlCenterController = ControlCenterState & {
  transitionRuntime: (target: RuntimeState) => Promise<void>
  runServiceAction: (serviceId: string, action: ServiceAction) => Promise<void>
  restoreConfig: (scope: string) => Promise<void>
  runIngestionCycle: () => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected control-center error'
}

async function loadSnapshot(): Promise<ControlCenterSnapshot> {
  return getControlCenterOverview()
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

export function useControlCenter(): ControlCenterController {
  const [state, setState] = useState<ControlCenterState>({
    snapshot: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const snapshot = await loadSnapshot()
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

    const stream = new EventSourceCtor(getControlCenterStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }

    stream.addEventListener('control-center.ready', handleRefresh)
    stream.addEventListener('control-center.refresh', handleRefresh)

    return () => {
      stream.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  async function transitionRuntime(target: RuntimeState): Promise<void> {
    if (!confirmAction(`Перевести runtime в ${target}?`)) {
      return
    }
    await runAction(async () => {
      await postRuntimeTransition(target)
    })
  }

  async function runServiceAction(serviceId: string, action: ServiceAction): Promise<void> {
    if (!confirmAction(`Выполнить ${action} для ${serviceId}?`)) {
      return
    }
    await runAction(async () => {
      await postServiceAction(serviceId, action)
    })
  }

  async function restoreConfig(scope: string): Promise<void> {
    if (!confirmAction(`Восстановить last-valid config для ${scope}?`)) {
      return
    }
    await runAction(async () => {
      await postRestoreConfig(scope)
    })
  }

  async function runIngestionCycle(): Promise<void> {
    if (!confirmAction('Запустить ручной ingestion cycle?')) {
      return
    }
    await runAction(async () => {
      await postRunIngestionCycle()
    })
  }

  return {
    ...state,
    transitionRuntime,
    runServiceAction,
    restoreConfig,
    runIngestionCycle,
  }
}
