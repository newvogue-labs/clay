import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import {
  getEventStreamUrl,
  getPreflight,
  getRuntimeSnapshot,
  getServices,
  runServiceAction as postServiceAction,
  transitionRuntime as postRuntimeTransition,
} from '../api/client'
import type {
  PreflightResult,
  RuntimeSnapshot,
  RuntimeState,
  ServiceAction,
  ServiceRecord,
} from '../types/runtime'

type ControlPlaneState = {
  runtime: RuntimeSnapshot | null
  services: ServiceRecord[]
  preflight: PreflightResult | null
  isLoading: boolean
  isActing: boolean
  error: string | null
}

type ControlPlaneController = ControlPlaneState & {
  transitionRuntime: (target: RuntimeState) => Promise<void>
  runServiceAction: (serviceId: string, action: ServiceAction) => Promise<void>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected control-plane error'
}

async function loadControlPlaneSnapshot(): Promise<{
  runtime: RuntimeSnapshot
  services: ServiceRecord[]
  preflight: PreflightResult
}> {
  const [runtime, services, preflight] = await Promise.all([
    getRuntimeSnapshot(),
    getServices(),
    getPreflight(),
  ])

  return {
    runtime,
    services: services.items,
    preflight,
  }
}

export function useControlPlane(): ControlPlaneController {
  const [state, setState] = useState<ControlPlaneState>({
    runtime: null,
    services: [],
    preflight: null,
    isLoading: true,
    isActing: false,
    error: null,
  })

  const refresh = useEffectEvent(async () => {
    try {
      const next = await loadControlPlaneSnapshot()
      startTransition(() => {
        setState((current) => ({
          ...current,
          ...next,
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

    const stream = new EventSource(getEventStreamUrl())
    const handleRefresh = () => {
      void refresh()
    }

    stream.addEventListener('control.ready', handleRefresh)
    stream.addEventListener('runtime.updated', handleRefresh)
    stream.addEventListener('service.updated', handleRefresh)
    stream.addEventListener('config.updated', handleRefresh)

    return () => {
      stream.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function transitionRuntime(target: RuntimeState): Promise<void> {
    startTransition(() => {
      setState((current) => ({ ...current, isActing: true, error: null }))
    })

    try {
      await postRuntimeTransition(target)
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

  async function runServiceAction(serviceId: string, action: ServiceAction): Promise<void> {
    startTransition(() => {
      setState((current) => ({ ...current, isActing: true, error: null }))
    })

    try {
      await postServiceAction(serviceId, action)
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

  return {
    ...state,
    transitionRuntime,
    runServiceAction,
  }
}
