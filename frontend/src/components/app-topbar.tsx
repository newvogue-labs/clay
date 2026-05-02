import {
  Clock,
  Cpu,
  Info,
  Layout,
  LayoutGrid,
  Moon,
  Play,
  RefreshCw,
  Square,
  Sun,
  Terminal,
  Zap,
} from 'lucide-react'

import type { AppScreen, ShellSessionState } from './app-sidebar'

type AppTopbarProps = {
  activeScreen: AppScreen
  isLightTheme: boolean
  nowLabel: string
  onToggleTheme: () => void
  sessionState: ShellSessionState
  consensusStatus: 'agreement' | 'partial' | 'conflict'
}

const screenLabels: Record<AppScreen, string> = {
  overview: 'Overview',
  workspace: 'Trading Workspace',
  'session-control': 'Session Control',
  'control-center': 'Control Center',
  'ai-control': 'AI Console',
  'demo-validation': 'Demo Validation',
  'validation-lab': 'Validation Lab',
  'session-review': 'Session Review',
  knowledge: 'Knowledge / Research',
  reliability: 'Reliability Center',
  settings: 'Settings',
}

export function AppTopbar({
  activeScreen,
  isLightTheme,
  nowLabel,
  onToggleTheme,
  sessionState,
  consensusStatus,
}: AppTopbarProps) {
  const isActive = sessionState === 'active_session'
  const isPaused = sessionState === 'paused'
  const isDegraded = sessionState === 'degraded'
  const sessionLabel = isActive ? 'Active' : isPaused ? 'Paused' : isDegraded ? 'Degraded' : 'Standby'
  const sessionClass = isActive
    ? 'border-clay-success/25 bg-clay-success/10 text-clay-success'
    : isPaused || isDegraded
      ? 'border-clay-warning/35 bg-clay-warning/10 text-clay-warning'
      : 'border-clay-border bg-clay-muted/10 text-clay-muted'

  return (
    <header className="flex h-14 items-center justify-between border-b border-clay-border bg-clay-card px-6">
      <div className="flex min-w-0 items-center gap-6">
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <span className="mb-0.5 text-[9px] font-bold uppercase tracking-[0.2em] text-clay-muted">Session Mode</span>
            <div className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-tight ${sessionClass}`}>
              {sessionLabel}
            </div>
          </div>
          <div className="flex flex-col">
            <span className="mb-0.5 text-[9px] font-bold uppercase tracking-[0.2em] text-clay-muted">Consensus</span>
            <div className="flex items-center gap-2">
              <div className="flex gap-0.5">
                {[1, 2, 3].map((item) => (
                  <div
                    className={`h-1.5 w-1.5 rounded-sm ${
                      consensusStatus === 'agreement'
                        ? 'bg-clay-success'
                        : consensusStatus === 'partial' && item < 3
                          ? 'bg-clay-success'
                          : consensusStatus === 'conflict' && item === 1
                            ? 'bg-clay-success'
                            : consensusStatus === 'conflict' && item === 2
                              ? 'bg-clay-warning'
                              : 'bg-clay-danger'
                    }`}
                    key={item}
                  />
                ))}
              </div>
              <span className="font-mono text-[9px] font-bold uppercase text-clay-muted">{consensusStatus}</span>
            </div>
          </div>
        </div>

        <div className="hidden h-4 w-px bg-clay-border lg:block" />

        <div className="hidden min-w-0 items-center gap-3 lg:flex">
          <div className="rounded border border-clay-border bg-clay-bg p-1.5 text-clay-accent">
            <Zap className="h-3.5 w-3.5 fill-current" />
          </div>
          <div className="min-w-0">
            <div className="mb-0.5 text-[9px] font-bold uppercase tracking-[0.2em] text-clay-muted">Active View</div>
            <div className="truncate text-[11px] font-bold uppercase tracking-[0.14em] text-clay-text">{screenLabels[activeScreen]}</div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-1.5 px-2 md:flex">
          <button className="topbar-icon-button" title="System logs" type="button">
            <Terminal className="h-3.5 w-3.5" />
          </button>
          <button className="topbar-icon-button" title="Model metrics" type="button">
            <Cpu className="h-3.5 w-3.5" />
          </button>
          <button className="topbar-icon-button" title="Visual settings" type="button">
            <Info className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="hidden h-4 w-px bg-clay-border md:block" />
        <div className="hidden items-center gap-1 rounded border border-clay-border bg-clay-bg p-1 md:flex">
          <button className="rounded border border-clay-border bg-clay-card p-1.5 text-clay-accent" title="Single view" type="button">
            <Layout className="h-3.5 w-3.5" />
          </button>
          <button className="rounded p-1.5 text-clay-muted hover:text-clay-text" title="Hybrid view" type="button">
            <LayoutGrid className="h-3.5 w-3.5" />
          </button>
        </div>
        <button
          aria-label={isActive ? 'Topbar session end indicator' : 'Topbar session start indicator'}
          className={`flex items-center gap-2 rounded px-3 py-1.5 text-[10px] font-bold uppercase transition ${
            isActive
              ? 'border border-clay-border bg-clay-card text-clay-danger hover:bg-clay-danger/10'
              : 'bg-clay-accent text-white hover:bg-clay-accent/80'
          }`}
          type="button"
        >
          {isActive ? <Square className="h-3 w-3 fill-current" /> : <Play className="h-3 w-3 fill-current" />}
          {isActive ? 'End Session' : 'Start Session'}
        </button>
        <div className="flex items-center gap-4 rounded border border-clay-border bg-clay-bg px-3 py-1.5">
          <div className="flex items-center gap-2">
            <Clock className="h-3.5 w-3.5 text-clay-muted" />
            <span className="font-mono text-[11px] font-bold text-clay-muted">{nowLabel}</span>
          </div>
          <div className="hidden items-center gap-2 sm:flex">
            <RefreshCw className={`h-3 w-3 text-clay-accent ${isActive ? 'animate-spin-slow' : ''}`} />
            <span className="font-mono text-[11px] font-bold text-clay-muted">00:42</span>
          </div>
        </div>
        <button
          className="topbar-icon-button"
          onClick={onToggleTheme}
          title={isLightTheme ? 'Switch to dark theme' : 'Switch to light theme'}
          type="button"
        >
          {isLightTheme ? <Moon className="h-4 w-4 text-clay-accent" /> : <Sun className="h-4 w-4 text-clay-warning" />}
        </button>
      </div>
    </header>
  )
}
