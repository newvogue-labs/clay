import type { LucideIcon } from 'lucide-react'
import {
  BarChart3,
  BookOpen,
  Bot,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FlaskConical,
  History,
  LayoutDashboard,
  Radio,
  Settings,
  Signal,
  Zap,
  Activity,
  Radar,
} from 'lucide-react'
import { motion } from 'motion/react'

export type AppScreen =
  | 'overview'
  | 'workspace'
  | 'session-control'
  | 'control-center'
  | 'ai-control'
  | 'demo-validation'
  | 'validation-lab'
  | 'session-review'
  | 'knowledge'
  | 'reliability'
  | 'settings'

export type ShellSessionState =
  | 'background_monitoring'
  | 'pre_session'
  | 'active_session'
  | 'paused'
  | 'review'
  | 'degraded'

type SidebarProps = {
  activeScreen: AppScreen
  onSelect: (screen: AppScreen) => void
  isCollapsed: boolean
  onToggleCollapsed: () => void
  sessionState: ShellSessionState
  missionStatus: {
    apiStatus: string
    modelStatus: string
    riskStatus: string
    latency: string
  }
}

type NavItem = {
  id: AppScreen
  label: string
  ariaLabel?: string
  icon: LucideIcon
}

const navItems: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'workspace', label: 'Trading Workspace', icon: BarChart3 },
  { id: 'session-control', label: 'Session Control', icon: Zap },
  { id: 'control-center', label: 'Control Center', icon: Radio },
  { id: 'ai-control', label: 'AI Console', ariaLabel: 'AI Control', icon: Bot },
  { id: 'demo-validation', label: 'Demo Validation', icon: ClipboardList },
  { id: 'validation-lab', label: 'Validation Lab', icon: FlaskConical },
  { id: 'session-review', label: 'Session Review', icon: History },
  { id: 'knowledge', label: 'Knowledge / Research', ariaLabel: 'Knowledge Base', icon: BookOpen },
  { id: 'reliability', label: 'Reliability Center', icon: Radar },
]

function getSessionLabel(sessionState: ShellSessionState): string {
  if (sessionState === 'active_session') {
    return 'Active'
  }
  if (sessionState === 'paused') {
    return 'Paused'
  }
  if (sessionState === 'degraded') {
    return 'Degraded'
  }
  if (sessionState === 'review') {
    return 'Review'
  }
  return 'Standby'
}

function getSessionColor(sessionState: ShellSessionState): string {
  if (sessionState === 'active_session') {
    return 'text-clay-success'
  }
  if (sessionState === 'paused' || sessionState === 'degraded') {
    return 'text-clay-warning'
  }
  return 'text-clay-muted'
}

export function AppSidebar({
  activeScreen,
  onSelect,
  isCollapsed,
  onToggleCollapsed,
  sessionState,
  missionStatus,
}: SidebarProps) {
  const sessionLabel = getSessionLabel(sessionState)
  const sessionColor = getSessionColor(sessionState)

  return (
    <motion.aside
      animate={{ width: isCollapsed ? 64 : 240 }}
      className="app-sidebar"
      initial={false}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      <div className={`flex h-14 items-center ${isCollapsed ? 'justify-center' : 'gap-3 border-b border-clay-border px-5'}`}>
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-clay-accent/20 bg-clay-accent/10">
          <Activity className="h-4 w-4 text-clay-accent" />
        </div>
        {!isCollapsed ? (
          <div className="flex min-w-0 flex-col">
            <h1 aria-label="Clay" className="truncate text-sm font-bold leading-tight tracking-tight text-clay-text">CLAY</h1>
            <span className="text-[9px] font-bold uppercase leading-tight tracking-[0.2em] text-clay-muted">Terminal v17</span>
          </div>
        ) : null}
      </div>

      <nav className="custom-scrollbar flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = activeScreen === item.id
          return (
            <button
              key={item.id}
              aria-label={item.ariaLabel ?? item.label}
              className={`group relative flex w-full items-center rounded px-2.5 py-2 text-left transition ${
                isActive
                  ? 'border border-clay-accent/20 bg-clay-accent/10 text-clay-accent shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                  : 'border border-transparent text-clay-muted hover:bg-clay-bg hover:text-clay-text'
              } ${isCollapsed ? 'justify-center' : 'gap-3'}`}
              onClick={() => {
                onSelect(item.id)
              }}
              title={isCollapsed ? item.label : undefined}
              type="button"
            >
              {isActive ? <div className="absolute left-0 h-4 w-[3px] rounded-r-full bg-clay-accent" /> : null}
              <Icon className="h-4 w-4 shrink-0 transition-colors" />
              {!isCollapsed ? (
                <span className="truncate text-xs font-bold tracking-tight">{item.label}</span>
              ) : null}
            </button>
          )
        })}
      </nav>

      <div className="border-t border-clay-border bg-clay-bg/50 p-3">
        <div className="mb-3 space-y-0.5">
          <button
            aria-label="Settings"
            className={`flex w-full items-center rounded px-2.5 py-2 transition ${
              activeScreen === 'settings'
                ? 'border border-clay-accent/20 bg-clay-accent/10 text-clay-accent'
                : 'border border-transparent text-clay-muted hover:bg-clay-card hover:text-clay-text'
            } ${isCollapsed ? 'justify-center' : 'gap-3'}`}
            onClick={() => {
              onSelect('settings')
            }}
            title={isCollapsed ? 'Settings' : undefined}
            type="button"
          >
            <Settings className="h-4 w-4 shrink-0" />
            {!isCollapsed ? <span className="text-xs font-bold tracking-tight">Settings</span> : null}
          </button>

          <button
            className={`flex w-full items-center rounded border border-transparent px-2.5 py-2 text-clay-muted transition hover:bg-clay-card hover:text-clay-text ${isCollapsed ? 'justify-center' : 'gap-3'}`}
            onClick={onToggleCollapsed}
            title={isCollapsed ? 'Expand' : 'Collapse'}
            type="button"
          >
            {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            {!isCollapsed ? <span className="text-xs font-bold tracking-tight">Collapse</span> : null}
          </button>
        </div>

        {!isCollapsed ? (
          <div className="rounded border border-clay-border/60 bg-clay-card p-3 shadow-sm">
            <div className="mb-2.5 flex items-center justify-between border-b border-clay-border/50 pb-2">
              <span className="text-[9px] font-bold uppercase tracking-[0.2em] text-clay-muted">Mission Status</span>
              <div className="flex items-center gap-1.5">
                <span className={`text-[9px] font-bold uppercase tracking-[0.16em] ${sessionColor}`}>{sessionLabel}</span>
                <div className={`h-1.5 w-1.5 rounded-full ${sessionState === 'active_session' ? 'animate-pulse bg-clay-success' : sessionState === 'paused' || sessionState === 'degraded' ? 'animate-pulse bg-clay-warning' : 'bg-clay-muted'}`} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <MissionCell label="API" value={missionStatus.apiStatus} tone="success" />
              <MissionCell label="MDL" value={missionStatus.modelStatus} />
              <MissionCell label="RSK" value={missionStatus.riskStatus} tone="warning" />
              <MissionCell label="LAT" value={missionStatus.latency} tone="success" />
            </div>
          </div>
        ) : null}
      </div>
    </motion.aside>
  )
}

type MissionCellProps = {
  label: string
  value: string
  tone?: 'default' | 'success' | 'warning'
}

function MissionCell({ label, value, tone = 'default' }: MissionCellProps) {
  const toneClass =
    tone === 'success'
      ? 'text-clay-success'
      : tone === 'warning'
        ? 'text-clay-warning'
        : 'text-clay-text'

  return (
    <div className="flex items-center justify-between rounded border border-clay-border/30 bg-clay-bg/50 px-1.5 py-1">
      <span className="text-[8px] font-bold uppercase tracking-[0.16em] text-clay-muted">{label}</span>
      <span className={`font-mono text-[9px] font-bold uppercase ${toneClass}`}>{value}</span>
    </div>
  )
}
