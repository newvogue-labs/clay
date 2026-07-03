import { useEffect, useState } from 'react'
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
import { useSettings } from './use-settings'

type SettingsPageProps = {
  isLightTheme: boolean
  onToggleTheme: () => void
}

export function SettingsPage({ isLightTheme, onToggleTheme }: SettingsPageProps) {
  const { configs, isLoading, isActing, applyConfig, restoreConfig } = useSettings()
  const { snapshot: aiSnapshot } = useAIControl()

  const chiefAssignment = aiSnapshot?.assignments.find((a) => a.role_id === 'chief-agent')
  const marketScannerAssignment = aiSnapshot?.assignments.find((a) => a.role_id === 'market-scanner')
  const chiefModel = chiefAssignment?.model_display_name ?? 'Loading\u2026'
  const marketModel = marketScannerAssignment?.model_display_name ?? 'Loading\u2026'

  const riskConfig = configs?.items.risk
  const runtimeConfig = configs?.items.runtime
  const mutableScopes = configs?.ui_mutable_scopes ?? []

  const kellyCapPct = riskConfig ? (riskConfig.kelly.cap * 100).toFixed(1) : '\u2026'
  const maxExposurePct = riskConfig ? riskConfig.session_limits.max_total_exposure_pct.toFixed(1) : '\u2026'
  const maxDrawdownPct = riskConfig ? riskConfig.session_limits.max_drawdown_pct.toFixed(1) : '\u2026'
  const maxConsecutiveLosses = riskConfig?.session_limits.max_consecutive_losses ?? '\u2026'

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
            <Key className="h-4 w-4 text-clay-muted" />
          </div>
          <SettingsRow label="Binance API" status="Unimplemented" value="Pending setup" />
          <SettingsRow label="Bybit API" status="Unimplemented" value="Pending setup" />
          <SettingsRow label="Coinbase Advanced" status="Unimplemented" value="Pending setup" />
        </section>

        <section className="settings-panel">
          <div className="panel-title-row">
            <h3>Risk Limits</h3>
            <Shield className="h-4 w-4 text-clay-warning" />
          </div>
          {isLoading ? (
            <div className="settings-loading-line">Loading risk limits...</div>
          ) : (
            <>
              <RiskLimit label="Max Risk Per Trade" value={`${kellyCapPct}%`} pct={riskConfig ? riskConfig.kelly.cap * 100 : 0} />
              <RiskLimit label="Max Total Exposure" value={`${maxExposurePct}%`} pct={riskConfig ? riskConfig.session_limits.max_total_exposure_pct : 0} />
              <RiskLimit label="Max Drawdown" value={`${maxDrawdownPct}%`} pct={riskConfig ? riskConfig.session_limits.max_drawdown_pct : 0} />
              <SettingsRow label="Max Consecutive Losses" value={String(maxConsecutiveLosses)} />
              <div className="risk-warning-box">
                <AlertTriangle className="h-4 w-4" />
                <p>Defensive mode should stay operator-reviewed until live demo evidence is collected.</p>
              </div>
            </>
          )}
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
            <SettingsStat label="Cache Usage" status="Unimplemented" value="Pending" />
            <SettingsStat label="Retention Window" status="Unimplemented" value="Pending" />
            <SettingsStat label="Last Backup" status="Unimplemented" value="Pending" />
          </div>
          {configs ? (
            <div className="config-review-panel">
              <div className="config-review-card">
                <Upload className="h-4 w-4 text-clay-warning" />
                <div>
                  <strong>Config restore/apply requires review</strong>
                  <span>Operator confirmation remains mandatory before changing runtime, risk, or provider defaults.</span>
                </div>
              </div>
              {mutableScopes.map((scope) => {
                const scopeConfig = configs.items[scope as keyof typeof configs.items]
                return (
                  <ConfigScopeRow
                    key={scope}
                    scope={scope}
                    isActing={isActing}
                    onApply={() => applyConfig(scope, scopeConfig as Record<string, unknown>)}
                    onRestore={() => restoreConfig(scope)}
                  />
                )
              })}
            </div>
          ) : null}
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

function RiskLimit({ label, value, pct }: { label: string; value: string; pct: number }) {
  const barWidth = Math.min(pct * 5, 100)
  return (
    <div className="risk-limit-row">
      <span>{label}</span>
      <strong>{value}</strong>
      <div>
        <span style={{ width: `${barWidth}%` }} />
      </div>
    </div>
  )
}

function SettingsStat({ label, value, status }: { label: string; value: string; status?: string }) {
  return (
    <div className="settings-stat">
      <span>{label}</span>
      {status ? <em>{status}</em> : null}
      <strong>{value}</strong>
    </div>
  )
}

function ConfigScopeRow({
  scope,
  isActing,
  onApply,
  onRestore,
}: {
  scope: string
  isActing: boolean
  onApply: () => void
  onRestore: () => void
}) {
  const [showApply, setShowApply] = useState(false)
  const [wasActing, setWasActing] = useState(false)

  useEffect(() => {
    if (wasActing && !isActing) {
      setShowApply(false)
    }
    setWasActing(isActing)
  }, [isActing, wasActing])

  return (
    <div className="config-scope-row">
      <div className="config-scope-header">
        <strong>{scope}</strong>
        <span className="config-scope-badge">mutable</span>
      </div>
      <p>Apply or restore the <strong>{scope}</strong> configuration scope.</p>
      <div className="config-scope-actions">
        <button disabled={isActing} onClick={() => setShowApply((v) => !v)} type="button">
          <Upload className="h-3.5 w-3.5" />
          Apply config
        </button>
        <button disabled={isActing} onClick={onRestore} type="button">
          <RefreshCw className="h-3.5 w-3.5" />
          Restore default
        </button>
      </div>
      {showApply ? (
        <div className="config-apply-confirm">
          <p>This will re-apply the current in-memory values to the <strong>{scope}</strong> config file.</p>
          <button disabled={isActing} onClick={onApply} type="button">
            Confirm Apply
          </button>
          <button disabled={isActing} onClick={() => setShowApply(false)} type="button">
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  )
}
