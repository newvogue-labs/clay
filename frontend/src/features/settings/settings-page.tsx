import {
  AlertTriangle,
  Bell,
  Database,
  Key,
  Layout,
  Moon,
  RefreshCw,
  Shield,
  Sun,
  Upload,
  Zap,
} from 'lucide-react'

import { useAIControl } from '../ai-control/use-ai-control'

type SettingsPageProps = {
  isLightTheme: boolean
  onToggleTheme: () => void
}

export function SettingsPage({ isLightTheme, onToggleTheme }: SettingsPageProps) {
  const { snapshot } = useAIControl()
  const chiefAssignment = snapshot?.assignments.find((a) => a.role_id === 'chief-agent')
  const marketScannerAssignment = snapshot?.assignments.find((a) => a.role_id === 'market-scanner')
  const chiefModel = chiefAssignment?.model_display_name ?? 'Loading\u2026'
  const marketModel = marketScannerAssignment?.model_display_name ?? 'Loading\u2026'
  return (
    <div aria-label="settings-page" className="screen-page settings-page" data-screen="settings">
      <header className="screen-page-header">
        <div>
          <h2>Settings</h2>
          <p>Operational configuration, providers, risk limits, and UI preferences</p>
        </div>
        <span className="settings-freeze-badge">Config Review Required</span>
      </header>

      <div className="settings-grid">
        <section className="settings-panel">
          <div className="panel-title-row">
            <h3>Appearance</h3>
            <Layout className="h-4 w-4 text-clay-accent" />
          </div>
          <div className="theme-choice-grid">
            <button
              className={!isLightTheme ? 'selected-theme-card' : ''}
              onClick={onToggleTheme}
              type="button"
            >
              <Moon className="h-4 w-4" />
              <span>Dark Mode</span>
              <em>Terminal style</em>
            </button>
            <button
              className={isLightTheme ? 'selected-theme-card' : ''}
              onClick={onToggleTheme}
              type="button"
            >
              <Sun className="h-4 w-4" />
              <span>Light Mode</span>
              <em>Review fallback</em>
            </button>
          </div>
          <SettingsRow label="Layout Density" status="Unimplemented" value="Compact" />
          <SettingsRow label="Animations" status="Unimplemented" value="Enabled" />
          <SettingsRow label="Order Book Panel" status="Unimplemented" value="Hidden" />
        </section>

        <section className="settings-panel">
          <div className="panel-title-row">
            <h3>API Connectors</h3>
            <Key className="h-4 w-4 text-clay-success" />
          </div>
          <ConnectorRow name="Binance API" status="connected" value="Sync 2m ago" />
          <ConnectorRow name="Bybit API" status="standby" value="Manual setup" />
          <ConnectorRow name="Coinbase Advanced" status="disabled" value="Not configured" />
          <button className="settings-command" type="button">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh Connectors
          </button>
        </section>

        <section className="settings-panel">
          <div className="panel-title-row">
            <h3>Risk Limits</h3>
            <Shield className="h-4 w-4 text-clay-warning" />
          </div>
          <RiskLimit label="Max Risk Per Trade" value="2.0%" />
          <RiskLimit label="Daily Loss Cap" value="5.0%" />
          <div className="risk-warning-box">
            <AlertTriangle className="h-4 w-4" />
            <p>Defensive mode should stay operator-reviewed until live demo evidence is collected.</p>
          </div>
        </section>

        <section className="settings-panel">
          <div className="panel-title-row">
            <h3>Delivery Channels</h3>
            <Bell className="h-4 w-4 text-clay-accent" />
          </div>
          <SettingsRow label="Signal Alerts" value="Enabled" />
          <SettingsRow label="Degraded State Alerts" value="Enabled" />
          <SettingsRow label="Mobile Push" status="Unimplemented" value="Draft" />
        </section>

        <section className="settings-panel wide-settings-panel">
          <div className="panel-title-row">
            <h3>Data Sources & Config Review</h3>
            <Database className="h-4 w-4 text-clay-accent" />
          </div>
          <div className="settings-data-grid">
            <SettingsStat label="Cache Usage" value="1.24 GB" />
            <SettingsStat label="Retention Window" value="90 Days" />
            <SettingsStat label="Last Backup" value="2h ago" />
          </div>
          <div className="config-review-card">
            <Upload className="h-4 w-4 text-clay-warning" />
            <div>
              <strong>Config restore/apply requires review</strong>
              <span>Operator confirmation remains mandatory before changing runtime, risk, or provider defaults.</span>
            </div>
          </div>
        </section>

        <section className="settings-panel">
          <div className="panel-title-row">
            <h3>Model Defaults</h3>
            <Zap className="h-4 w-4 text-clay-accent" />
          </div>
          <SettingsRow label="Chief Agent" value={chiefModel} />
          <SettingsRow label="Market Analyst" value={marketModel} />
          <SettingsRow label="Fallback Policy" value="Review Required" />
        </section>
      </div>
    </div>
  )
}

function SettingsRow({ label, value, status }: { label: string; value: string; status?: string }) {
  return (
    <div className="settings-row">
      <span>{label}</span>
      <div>
        {status ? <em>{status}</em> : null}
        <strong>{value}</strong>
      </div>
    </div>
  )
}

function ConnectorRow({ name, status, value }: { name: string; status: string; value: string }) {
  const toneClass = status === 'connected' ? 'text-clay-success' : status === 'standby' ? 'text-clay-warning' : 'text-clay-muted'
  return (
    <div className="connector-row">
      <div>
        <strong>{name}</strong>
        <span>{value}</span>
      </div>
      <em className={toneClass}>{status}</em>
    </div>
  )
}

function RiskLimit({ label, value }: { label: string; value: string }) {
  return (
    <div className="risk-limit-row">
      <span>{label}</span>
      <strong>{value}</strong>
      <div>
        <span style={{ width: value === '2.0%' ? '40%' : '70%' }} />
      </div>
    </div>
  )
}

function SettingsStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="settings-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
