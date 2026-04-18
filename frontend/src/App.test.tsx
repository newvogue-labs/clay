import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import App from './App'

describe('App', () => {
  let controlCenterSnapshot: Record<string, any>
  let workspaceSnapshot: Record<string, any>

  beforeEach(() => {
    controlCenterSnapshot = {
      summary: {
        runtime_state: 'background_monitoring',
        overall_status: 'degraded',
        actionability: 'limited',
        active_incident_count: 1,
        critical_incident_count: 0,
        last_status_refresh_at: '2026-04-16T12:00:00Z',
        blocking_reason: null,
      },
      runtime: {
        state: 'background_monitoring',
        allowed_transitions: ['pre_session', 'degraded'],
        preflight_status: 'pass',
        blocking_reason: null,
      },
      services: [
        {
          service_id: 'control-api',
          service_name: 'Control Api',
          service_kind: 'api',
          lifecycle_class: 'always-on',
          criticality: 'critical',
          status: 'healthy',
          last_heartbeat_at: null,
          last_error: null,
          freshness_status: null,
          allowed_actions: [],
        },
        {
          service_id: 'pair-scanner',
          service_name: 'Pair Scanner',
          service_kind: 'worker',
          lifecycle_class: 'on-demand',
          criticality: 'optional',
          status: 'stopped',
          last_heartbeat_at: null,
          last_error: null,
          freshness_status: null,
          allowed_actions: ['start', 'restart'],
        },
      ],
      ingestion: {
        market_status: 'fresh',
        context_status: 'degraded',
        blocks_active_trading: false,
        market_items: [
          {
            symbol: 'BTCUSDT',
            timeframe: '15m',
            status: 'fresh',
            evaluated_at: '2026-04-16T12:00:00Z',
            latest_bar_open_time: '2026-04-16T11:45:00Z',
            reason: 'delta=0:10:00',
          },
        ],
        connectors: [
          {
            connector_id: 'demo-news',
            connector_type: 'news',
            status: 'degraded',
            observed_at: '2026-04-16T12:00:00Z',
          },
        ],
      },
      incidents: [
        {
          source_name: 'demo_news_feed',
          severity: 'warning',
          message: 'connector recovered after retry',
          recorded_at: '2026-04-16T12:00:00Z',
        },
      ],
      audit: [
        {
          timestamp: '2026-04-16T12:00:00Z',
          event_type: 'runtime.transitioned',
          payload: { target: 'background_monitoring' },
        },
      ],
      config: {
        config_dir: '/tmp/clay-config',
        scopes: [
          {
            scope: 'runtime',
            mutable: true,
            values: {
              work_window_start: '09:00',
              work_window_end: '22:00',
              default_state: 'background_monitoring',
            },
          },
        ],
      },
    }
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
        technical_context: ['Liquidity high', 'Volatility score 0.64', 'Availability fresh'],
        execution_notes: ['Signal direction: bullish.', 'Look for confirmation on Binance before any manual execution.'],
      },
      risk: {
        risk_posture: 'normal',
        confidence_label: 'high',
        risk_reward_hint: 'Bullish setup supports a structured asymmetric plan.',
        action_guidance: 'Open Binance in parallel and validate the execution context manually.',
      },
      news: [
        {
          headline: 'BTC keeps leadership',
          summary: 'Momentum stays constructive on intraday pullbacks.',
          source_name: 'demo_news_feed',
          published_at: '2026-04-18T11:30:00Z',
          source_url: 'https://example.invalid/news/btc',
        },
      ],
      sentiment: [
        {
          source_name: 'demo_sentiment_feed',
          sentiment_label: 'bullish',
          sentiment_score: 0.83,
          captured_at: '2026-04-18T11:40:00Z',
        },
      ],
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

        if (url.endsWith('/control-center/overview') && method === 'GET') {
          return Promise.resolve(
            new Response(JSON.stringify(controlCenterSnapshot), { status: 200 }),
          )
        }

        if (url.endsWith('/runtime/transition') && method === 'POST') {
          controlCenterSnapshot.runtime.state = 'pre_session'
          controlCenterSnapshot.runtime.allowed_transitions = ['active_session', 'degraded']
          controlCenterSnapshot.summary.runtime_state = 'pre_session'
          return Promise.resolve(
            new Response(JSON.stringify(controlCenterSnapshot.runtime), { status: 200 }),
          )
        }

        if (url.endsWith('/services/pair-scanner/actions') && method === 'POST') {
          controlCenterSnapshot.services[1].status = 'healthy'
          controlCenterSnapshot.services[1].allowed_actions = ['stop', 'restart']
          return Promise.resolve(
            new Response(
              JSON.stringify({
                service_id: 'pair-scanner',
                status: 'healthy',
              }),
              { status: 200 },
            ),
          )
        }

        if (url.endsWith('/ingestion/run') && method === 'POST') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                started_at: '2026-04-16T12:00:00Z',
                finished_at: '2026-04-16T12:01:00Z',
                market_records_written: 4,
                news_records_written: 1,
                sentiment_records_written: 1,
                freshness_updates_written: 2,
                connector_statuses: [],
                incidents: [],
              }),
              { status: 200 },
            ),
          )
        }

        if (url.endsWith('/configs/runtime/restore') && method === 'POST') {
          controlCenterSnapshot.config.scopes[0].values.default_state = 'background_monitoring'
          return Promise.resolve(
            new Response(
              JSON.stringify({
                scope: 'runtime',
                config: controlCenterSnapshot.config.scopes[0].values,
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

    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('EventSource', EventSourceMock)
    Object.defineProperty(globalThis, 'EventSource', {
      value: EventSourceMock,
      writable: true,
      configurable: true,
    })
    Object.defineProperty(window, 'EventSource', {
      value: EventSourceMock,
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the runtime foundation shell with live control data', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Clay' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /trading workspace/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /focused pair/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /active signals/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /monitoring pool/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /risk assessment/i })).toBeInTheDocument()
    expect(await screen.findByText(/BTC \/ USDT/i)).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /open in binance/i })).toBeInTheDocument()
  })

  it('switches between workspace and control center screens', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /control center/i }))
    expect(await screen.findByRole('heading', { name: /control center/i })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /system health/i })).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /trading workspace/i }))
    expect(await screen.findByRole('heading', { name: /trading workspace/i })).toBeInTheDocument()
  })
})
