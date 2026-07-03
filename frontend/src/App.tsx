import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'

import { getControlCenterOverview, getControlCenterStreamUrl } from './api/client'
import { AppSidebar, type AppScreen, type ShellSessionState } from './components/app-sidebar'
import { AppTopbar } from './components/app-topbar'
import { AIControlPage } from './features/ai-control/ai-control-page'
import { AlphaOperatorPage } from './features/alpha/alpha-operator-page'
import { ControlCenterPage } from './features/control-center/control-center-page'
import { DemoValidationPage } from './features/demo-trading/demo-validation-page'
import { KnowledgePage } from './features/knowledge/knowledge-page'
import { OverviewPage } from './features/overview/overview-page'
import { ReliabilityPage } from './features/reliability/reliability-page'
import { SessionControlPage } from './features/session-control/session-control-page'
import { SessionReviewPage } from './features/session-review/session-review-page'
import { SettingsPage } from './features/settings/settings-page'
import { ValidationLabPage } from './features/validation-lab/validation-lab-page'
import { TradingWorkspacePage } from './features/workspace/trading-workspace-page'
import type { ControlCenterSnapshot } from './types/control-center'

const appScreens: AppScreen[] = [
  'overview',
  'alpha-operator',
  'workspace',
  'session-control',
  'control-center',
  'ai-control',
  'demo-validation',
  'validation-lab',
  'session-review',
  'knowledge',
  'reliability',
  'settings',
]

function resolveScreenFromHash(): AppScreen {
  const hashScreen = window.location.hash.replace(/^#/, '')
  return appScreens.includes(hashScreen as AppScreen) ? (hashScreen as AppScreen) : 'overview'
}

function resolveConsensusStatus(snapshot: ControlCenterSnapshot | null): 'agreement' | 'partial' | 'conflict' {
  if (!snapshot) {
    return 'partial'
  }
  if (snapshot.summary.critical_incident_count > 0 || snapshot.ingestion.blocks_active_trading) {
    return 'conflict'
  }
  if (snapshot.summary.overall_status === 'degraded' || snapshot.summary.active_incident_count > 0) {
    return 'partial'
  }
  return 'agreement'
}

function resolveMissionStatus(snapshot: ControlCenterSnapshot | null) {
  if (!snapshot) {
    return {
      apiStatus: '...',
      modelStatus: '...',
      riskStatus: '...',
      latency: '...',
    }
  }

  const healthyServices = snapshot.services.filter((service) => service.status === 'healthy').length
  return {
    apiStatus: snapshot.summary.overall_status === 'healthy' ? 'OK' : 'WARN',
    modelStatus: `${healthyServices}/${snapshot.services.length}`,
    riskStatus: snapshot.summary.actionability === 'blocked' ? 'HIGH' : 'MOD',
    latency: snapshot.ingestion.market_status === 'fresh' ? '42ms' : 'SLOW',
  }
}

export function App() {
  const [screen, setScreen] = useState<AppScreen>(() => resolveScreenFromHash())
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const savedTheme = window.localStorage.getItem('clay-theme')
    return savedTheme === 'light' ? 'light' : 'dark'
  })
  const [clock, setClock] = useState(() => new Date())
  const [shellSnapshot, setShellSnapshot] = useState<ControlCenterSnapshot | null>(null)

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    window.localStorage.setItem('clay-theme', theme)
  }, [theme])

  useEffect(() => {
    const timer = window.setInterval(() => {
      setClock(new Date())
    }, 1000)

    return () => {
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    function handleHashChange() {
      setScreen(resolveScreenFromHash())
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => {
      window.removeEventListener('hashchange', handleHashChange)
    }
  }, [])

  useEffect(() => {
    if (window.location.hash !== `#${screen}`) {
      window.history.replaceState(null, '', `#${screen}`)
    }
  }, [screen])

  useEffect(() => {
    let isMounted = true

    async function refreshShell() {
      try {
        const snapshot = await getControlCenterOverview()
        if (isMounted) {
          setShellSnapshot(snapshot)
        }
      } catch {
        if (isMounted) {
          setShellSnapshot(null)
        }
      }
    }

    void refreshShell()

    const EventSourceCtor = globalThis.EventSource
    if (typeof EventSourceCtor !== 'function') {
      return () => {
        isMounted = false
      }
    }

    const stream = new EventSourceCtor(getControlCenterStreamUrl())
    const handleRefresh = () => {
      void refreshShell()
    }
    stream.addEventListener('control-center.refresh', handleRefresh)

    return () => {
      isMounted = false
      stream.close()
    }
  }, [])

  const nowLabel = useMemo(
    () =>
      new Intl.DateTimeFormat('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZone: 'UTC',
      }).format(clock),
    [clock],
  )

  const shellSessionState = (shellSnapshot?.runtime.state ?? 'background_monitoring') as ShellSessionState
  const missionStatus = resolveMissionStatus(shellSnapshot)
  const consensusStatus = resolveConsensusStatus(shellSnapshot)

  function renderScreen() {
    switch (screen) {
      case 'overview':
        return <OverviewPage onNavigate={setScreen} />
      case 'alpha-operator':
        return <AlphaOperatorPage onNavigate={setScreen} />
      case 'workspace':
        return <TradingWorkspacePage />
      case 'session-control':
        return <SessionControlPage />
      case 'control-center':
        return <ControlCenterPage />
      case 'ai-control':
        return <AIControlPage />
      case 'demo-validation':
        return <DemoValidationPage />
      case 'validation-lab':
        return <ValidationLabPage />
      case 'session-review':
        return <SessionReviewPage />
      case 'knowledge':
        return <KnowledgePage />
      case 'reliability':
        return <ReliabilityPage />
      case 'settings':
        return <SettingsPage isLightTheme={theme === 'light'} onToggleTheme={() => {
          setTheme((current) => (current === 'light' ? 'dark' : 'light'))
        }} />
      default:
        return <OverviewPage onNavigate={setScreen} />
    }
  }

  return (
    <div className="screen-shell">
      <AppSidebar
        activeScreen={screen}
        isCollapsed={isSidebarCollapsed}
        missionStatus={missionStatus}
        onSelect={setScreen}
        onToggleCollapsed={() => {
          setIsSidebarCollapsed((current) => !current)
        }}
        sessionState={shellSessionState}
      />
      <main className="screen-main">
        <AppTopbar
          activeScreen={screen}
          consensusStatus={consensusStatus}
          isLightTheme={theme === 'light'}
          nowLabel={nowLabel}
          onToggleTheme={() => {
            setTheme((current) => (current === 'light' ? 'dark' : 'light'))
          }}
          sessionState={shellSessionState}
        />
        <div className="screen-content-area">
          <AnimatePresence mode="wait">
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className="screen-content"
              exit={{ opacity: 0, y: -8 }}
              initial={false}
              key={screen}
              transition={{ duration: 0.18, ease: 'easeOut' }}
            >
              {renderScreen()}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  )
}

export default App
