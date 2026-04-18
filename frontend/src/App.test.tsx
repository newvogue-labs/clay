import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import App from './App'

describe('App', () => {
  let aiControlSnapshot: Record<string, any>
  let controlCenterSnapshot: Record<string, any>
  let workspaceSnapshot: Record<string, any>

  beforeEach(() => {
    aiControlSnapshot = {
      summary: {
        overall_status: 'degraded',
        chief_agent_model: 'GPT-5.4',
        active_conflict_count: 2,
        degraded_role_count: 1,
        fallback_active: false,
        last_reviewed_at: null,
      },
      roles: [
        {
          role_id: 'chief-agent',
          role_name: 'Chief Agent',
          responsibility: 'Final synthesis.',
          inputs: ['ranked signals'],
          outputs: ['session thesis'],
          allowed_actions: ['synthesize'],
          constraints: ['must expose conflicts'],
          explanation_owner: true,
          synthesis_owner: true,
        },
        {
          role_id: 'forecast-model',
          role_name: 'Forecast Model',
          responsibility: 'Directional forecast hints.',
          inputs: ['market features'],
          outputs: ['forecast bias'],
          allowed_actions: ['forecast'],
          constraints: ['cannot auto-activate strategy'],
          explanation_owner: false,
          synthesis_owner: false,
        },
      ],
      models: [
        {
          model_id: 'openai-gpt-5.4',
          display_name: 'GPT-5.4',
          provider: 'OpenAI',
          source: 'cloud',
          training_date: '2026-02-01',
          metrics_summary: 'Strong synthesis.',
          notes: 'Preferred for synthesis.',
          activation_status: 'active',
          compatible_roles: ['chief-agent'],
          fallback_ready: true,
        },
        {
          model_id: 'gemini-2.5-flash',
          display_name: 'Gemini 2.5 Flash',
          provider: 'Google',
          source: 'cloud',
          training_date: '2026-01-20',
          metrics_summary: 'Fast forecast.',
          notes: 'Default forecast assistant.',
          activation_status: 'active',
          compatible_roles: ['forecast-model'],
          fallback_ready: true,
        },
        {
          model_id: 'forecast-lite-v1',
          display_name: 'Forecast Lite v1',
          provider: 'Local',
          source: 'local',
          training_date: '2025-12-10',
          metrics_summary: 'Compact fallback.',
          notes: 'Safe fallback.',
          activation_status: 'standby',
          compatible_roles: ['forecast-model'],
          fallback_ready: true,
        },
      ],
      assignments: [
        {
          role_id: 'chief-agent',
          role_name: 'Chief Agent',
          model_id: 'openai-gpt-5.4',
          model_display_name: 'GPT-5.4',
          provider: 'OpenAI',
          assignment_mode: 'active',
          assignment_health: 'healthy',
          confidence_penalty: 0,
          review_required: false,
          reason: 'GPT-5.4 is assigned and ready.',
        },
        {
          role_id: 'forecast-model',
          role_name: 'Forecast Model',
          model_id: 'gemini-2.5-flash',
          model_display_name: 'Gemini 2.5 Flash',
          provider: 'Google',
          assignment_mode: 'active',
          assignment_health: 'review_required',
          confidence_penalty: 0.1,
          review_required: true,
          reason: 'Provider mix creates a reviewable conflict.',
        },
      ],
      conflicts: [
        {
          conflict_id: 'provider-mix-forecast-model',
          severity: 'warning',
          title: 'Provider mix needs review',
          description: 'Forecast Model uses Google while Chief Agent uses OpenAI.',
          affected_roles: ['chief-agent', 'forecast-model'],
          recommended_action: 'Review the provider split.',
        },
      ],
      fallback: {
        fallback_active: false,
        local_fallback_ready: false,
        degraded_roles: ['news-sentiment-agent'],
        operator_message: 'Some roles have no safe fallback path.',
      },
      pending_review: null,
    }

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

        if (url.endsWith('/ai-control/overview') && method === 'GET') {
          return Promise.resolve(new Response(JSON.stringify(aiControlSnapshot), { status: 200 }))
        }

        if (url.endsWith('/ai-control/assignments/review') && method === 'POST') {
          aiControlSnapshot.pending_review = {
            review_id: 'review-forecast-lite',
            role_id: 'forecast-model',
            role_name: 'Forecast Model',
            current_model_id: 'gemini-2.5-flash',
            proposed_model_id: 'forecast-lite-v1',
            proposed_model_name: 'Forecast Lite v1',
            severity: 'warning',
            approval_required: true,
            blocks_apply: false,
            summary: 'Review required before assigning Forecast Lite v1 to Forecast Model.',
            risks: ['Provider switch changes latency/error/fallback profile for this role.'],
            expected_effects: ['Forecast Model will switch from Gemini 2.5 Flash to Forecast Lite v1.'],
            resulting_confidence_penalty: 0.2,
            resulting_conflicts: [],
          }
          return Promise.resolve(
            new Response(JSON.stringify(aiControlSnapshot.pending_review), { status: 200 }),
          )
        }

        if (url.endsWith('/ai-control/assignments/apply') && method === 'POST') {
          aiControlSnapshot.assignments[1].model_id = 'forecast-lite-v1'
          aiControlSnapshot.assignments[1].model_display_name = 'Forecast Lite v1'
          aiControlSnapshot.assignments[1].provider = 'Local'
          aiControlSnapshot.assignments[1].assignment_health = 'healthy'
          aiControlSnapshot.assignments[1].reason = 'Forecast Lite v1 is assigned and ready.'
          aiControlSnapshot.summary.active_conflict_count = 0
          aiControlSnapshot.conflicts = []
          aiControlSnapshot.pending_review = null
          return Promise.resolve(new Response(JSON.stringify(aiControlSnapshot), { status: 200 }))
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

  it('renders ai control and applies a reviewed assignment', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /ai control/i }))
    expect(await screen.findByRole('heading', { name: /ai control/i })).toBeInTheDocument()
    expect(await screen.findByText(/provider mix needs review/i)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /review forecast lite v1/i }))
    expect(await screen.findByText(/review required before assigning forecast lite v1/i)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /apply reviewed assignment/i }))
    expect(await screen.findByText(/forecast lite v1 is assigned and ready/i)).toBeInTheDocument()
  })
})
