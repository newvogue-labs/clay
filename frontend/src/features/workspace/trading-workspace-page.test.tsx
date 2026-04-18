import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { TradingWorkspacePage } from './trading-workspace-page'

describe('TradingWorkspacePage', () => {
  let workspaceSnapshot: Record<string, any>

  beforeEach(() => {
    workspaceSnapshot = {
      focus_pair: {
        symbol: 'BTCUSDT',
        display_name: 'BTC / USDT',
        is_focused: true,
        role: 'primary',
        last_price: 70420.5,
        pct_change_24h: 2.8,
        volatility: 0.64,
        last_scan_at: '2026-04-18T12:00:00Z',
        active_signal_id: 'sig-btcusdt',
        focus_source: 'system_recommendation',
      },
      workspace_state: {
        runtime_state: 'background_monitoring',
        workspace_posture: 'normal',
        focused_signal_state: 'active',
        can_open_binance: true,
        can_log_decision: true,
        blocking_reason: null,
      },
      signals: [
        {
          signal_id: 'sig-btcusdt',
          pair: 'BTCUSDT',
          direction: 'bullish',
          state: 'active',
          confidence: 0.83,
          ranking_score: 0.88,
          confidence_penalty: 0.0,
          response_action: 'warning_only',
          strategy_mode: 'momentum',
          setup_summary: 'Bullish continuation with high liquidity and active conviction.',
          last_updated_at: '2026-04-18T12:00:00Z',
        },
      ],
      monitoring_pool: [
        {
          symbol: 'BTCUSDT',
          display_name: 'BTC / USDT',
          role: 'primary',
          availability_status: 'fresh',
          last_price: 70420.5,
          pct_change_24h: 2.8,
          volatility: 0.64,
          has_active_signal: true,
          is_focused: true,
        },
        {
          symbol: 'SOLUSDT',
          display_name: 'SOL / USDT',
          role: 'backup',
          availability_status: 'fresh',
          last_price: 182.3,
          pct_change_24h: 1.9,
          volatility: 0.52,
          has_active_signal: false,
          is_focused: false,
        },
      ],
      situation_map: {
        directional_bias: 'bullish',
        entry_hint: 'Watch reaction near 70561.341',
        target_hint: 'First decision zone near 71265.546',
        invalidation_hint: 'Treat a move through 69997.136 as invalidation',
        analyst_note: 'BTCUSDT is the cleanest decision-support candidate in the current shortlist.',
      },
      reasoning: {
        thesis: 'Bullish continuation with high liquidity and active conviction.',
        technical_context: ['Liquidity high'],
        execution_notes: ['Look for confirmation on Binance before any manual execution.'],
      },
      risk: {
        risk_posture: 'normal',
        confidence_label: 'high',
        confidence_penalty: 0.0,
        response_action: 'warning_only',
        strategy_mode: 'momentum',
        risk_reward_hint: 'Bullish setup supports a structured asymmetric plan.',
        action_guidance: 'Open Binance in parallel and validate the execution context manually.',
        active_triggers: [],
      },
      news: [],
      sentiment: [],
      update_meta: {
        focus_last_updated_at: '2026-04-18T12:00:00Z',
        market_status: 'fresh',
        context_status: 'fresh',
        last_ingestion_at: '2026-04-18T12:01:00Z',
      },
    }

    vi.stubGlobal(
      'fetch',
      vi.fn((input: string | URL | Request, init?: RequestInit) => {
        const url = String(input)
        const method = init?.method ?? 'GET'

        if (url.endsWith('/workspace/trading') && method === 'GET') {
          return Promise.resolve(new Response(JSON.stringify(workspaceSnapshot), { status: 200 }))
        }

        if (url.endsWith('/workspace/trading/focus') && method === 'POST') {
          workspaceSnapshot.focus_pair.symbol = 'SOLUSDT'
          workspaceSnapshot.focus_pair.display_name = 'SOL / USDT'
          workspaceSnapshot.focus_pair.focus_source = 'monitoring_click'
          workspaceSnapshot.focus_pair.active_signal_id = null
          workspaceSnapshot.workspace_state.focused_signal_state = 'absent'
          return Promise.resolve(
            new Response(
              JSON.stringify({
                focus_pair: workspaceSnapshot.focus_pair,
                workspace_state: workspaceSnapshot.workspace_state,
              }),
              { status: 200 },
            ),
          )
        }

        return Promise.resolve(new Response('Not found', { status: 404 }))
      }),
    )

    class EventSourceMock {
      addEventListener() {}

      close() {}
    }

    vi.stubGlobal('EventSource', EventSourceMock)
    Object.defineProperty(globalThis, 'EventSource', {
      value: EventSourceMock,
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders active signals and monitoring pool regions', async () => {
    render(<TradingWorkspacePage />)

    expect(await screen.findByRole('heading', { name: /trading workspace/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /active signals/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /monitoring pool/i })).toBeInTheDocument()
    expect((await screen.findAllByText(/bullish continuation/i)).length).toBeGreaterThan(0)
  })

  it('switches the focused pair when a monitoring item is selected', async () => {
    render(<TradingWorkspacePage />)

    fireEvent.click(await screen.findByRole('button', { name: /SOLUSDT/i }))

    expect(await screen.findByText(/SOL \/ USDT/i)).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /no active signal/i })).toBeInTheDocument()
  })
})
