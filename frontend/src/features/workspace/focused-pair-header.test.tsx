import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { FocusPairSnapshot, WorkspaceStateSnapshot } from '../../types/workspace'
import { FocusedPairHeader } from './focused-pair-header'

const focusPair: FocusPairSnapshot = {
  symbol: 'BTCUSDT',
  display_name: 'BTC / USDT',
  is_focused: true,
  role: 'primary',
  last_price: 65000,
  pct_change_24h: 1.2,
  volatility: 0.4,
  last_scan_at: '2026-06-29T12:00:00Z',
  active_signal_id: null,
  focus_source: 'monitoring_click',
}

function buildWorkspaceState(
  overrides: Partial<WorkspaceStateSnapshot> = {},
): WorkspaceStateSnapshot {
  return {
    runtime_state: 'active_session',
    workspace_posture: 'normal',
    focused_signal_state: 'absent',
    can_open_binance: true,
    can_log_decision: true,
    blocking_reason: null,
    monitored_data_health: 'fresh',
    execution_mode: null,
    execution_override_state: null,
    execution_override_expires_at: null,
    server_time: '2026-06-29T12:00:00Z',
    ...overrides,
  }
}

describe('FocusedPairHeader monitored data health advisory', () => {
  it('shows the monitoring advisory when monitored data is degraded', () => {
    render(
      <FocusedPairHeader
        focusPair={focusPair}
        workspaceState={buildWorkspaceState({ monitored_data_health: 'degraded' })}
      />,
    )

    expect(screen.getByText(/несвежие/i)).toBeInTheDocument()
  })

  it('hides the advisory when monitored data is fresh', () => {
    render(
      <FocusedPairHeader focusPair={focusPair} workspaceState={buildWorkspaceState()} />,
    )

    expect(screen.queryByText(/несвежие/i)).not.toBeInTheDocument()
  })
})
