import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  applyConfig as postApplyConfig,
  getConfigs,
  getConfigsStreamUrl,
  restoreConfig as postRestoreConfig,
} from '../../api/settings-client'
import type { ConfigsSnapshot } from '../../types/settings'

type SettingsState = {
  configs: ConfigsSnapshot | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type SettingsController = SettingsState & {
  applyConfig: (scope: string, config: Record<string, unknown>) => Promise<void>
  restoreConfig: (scope: string) => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected settings error'
}

function confirmAction(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true
  }
  return window.confirm(message)
}

export function useSettings(): SettingsController {
  const [state, setState] = useState<SettingsState>({
    configs: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const configs = await getConfigs()
      startTransition(() => {
        setState((current) => ({
          ...current,
          configs,
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
    const stream = new EventSourceCtor(getConfigsStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }
    stream.addEventListener('config.updated', handleRefresh)
    stream.addEventListener('events.ready', handleRefresh)
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

  async function applyConfig(scope: string, config: Record<string, unknown>): Promise<void> {
    if (!confirmAction(`Применить конфиг для "${scope}"?`)) {
      return
    }
    await runAction(async () => {
      await postApplyConfig(scope, config)
    })
  }

  async function restoreConfig(scope: string): Promise<void> {
    if (!confirmAction(`Восстановить конфиг "${scope}" из последней валидной версии?`)) {
      return
    }
    await runAction(async () => {
      await postRestoreConfig(scope)
    })
  }

  return {
    ...state,
    applyConfig,
    restoreConfig,
  }
}
