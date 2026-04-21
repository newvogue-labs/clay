import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import App from './App'

describe('App', () => {
  let aiControlSnapshot: Record<string, any>
  let controlCenterSnapshot: Record<string, any>
  let demoTradingSnapshot: Record<string, any>
  let sessionReviewSnapshot: Record<string, any>
  let sessionControlSnapshot: Record<string, any>
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
    demoTradingSnapshot = {
      readiness: {
        status: 'collecting',
        operator_message: 'Keep collecting disciplined demo sessions before the review gate unlocks.',
        distinct_session_count: 2,
        total_records: 1,
        resolved_record_count: 0,
        profitable_record_count: 0,
        cumulative_pnl_pct: 0,
        outcome_counts: {
          matched: 0,
          missed: 0,
          late_matched: 0,
          mismatched: 0,
          unresolved: 1,
        },
        gates: [
          {
            gate_id: 'session-count',
            label: 'Session count',
            status: 'warn',
            detail: '2 / 5 demo sessions recorded.',
          },
        ],
      },
      active_session: {
        lifecycle_state: 'active_session',
        session_id: 'session-1',
        current_pair_symbol: 'BTCUSDT',
        current_signal_id: 'sig-btcusdt',
        can_log_decision: true,
        blocking_reason: null,
      },
      records: [
        {
          record_id: 1,
          session_id: 'session-1',
          signal_id: 'sig-btcusdt',
          symbol: 'BTCUSDT',
          executed_symbol: null,
          operator_action: 'entered',
          operator_notes: null,
          recorded_at: '2026-04-21T15:01:00Z',
          external_trade_id: null,
          broker_status: 'awaiting_result',
          entry_price: null,
          exit_price: null,
          pnl_pct: null,
          observed_at: null,
          outcome_status: 'unresolved',
          awaiting_result: true,
        },
      ],
    }
    sessionReviewSnapshot = {
      summary: {
        review_status: 'review_ready',
        total_demo_records: 2,
        resolved_demo_records: 2,
        cumulative_pnl_pct: 1.4,
        feedback_count: 0,
        last_reviewed_at: null,
        operator_message: 'Session evidence is coherent enough for post-session review.',
      },
      filters: {
        pair: null,
        strategy: null,
        model_version: null,
        confidence_band: null,
      },
      filter_options: {
        pairs: ['BTCUSDT', 'SOLUSDT'],
        strategies: ['momentum', 'defensive'],
        model_versions: ['openai-gpt-5.4'],
        confidence_bands: ['high', 'low'],
      },
      records: [
        {
          record_id: 1,
          session_id: 'session-1',
          signal_id: 'sig-btcusdt',
          symbol: 'BTCUSDT',
          strategy_mode: 'momentum',
          model_version: 'openai-gpt-5.4',
          confidence_band: 'high',
          operator_action: 'entered',
          outcome_status: 'matched',
          pnl_pct: 2.4,
          recorded_at: '2026-04-21T15:01:00Z',
          observed_at: '2026-04-21T15:05:00Z',
        },
        {
          record_id: 2,
          session_id: 'session-2',
          signal_id: 'sig-solusdt',
          symbol: 'SOLUSDT',
          strategy_mode: 'defensive',
          model_version: 'openai-gpt-5.4',
          confidence_band: 'low',
          operator_action: 'off_signal',
          outcome_status: 'mismatched',
          pnl_pct: -1,
          recorded_at: '2026-04-21T14:00:00Z',
          observed_at: '2026-04-21T14:15:00Z',
        },
      ],
      feedback: [],
      audit: [
        {
          timestamp: '2026-04-21T15:06:00Z',
          actor: 'operator',
          module: 'demo',
          event_type: 'demo.result.ingested',
          object_id: '1',
          explanation: 'Ingested demo result for BTCUSDT.',
          severity: 'info',
        },
      ],
      ai_review_cards: [
        {
          card_id: 'mismatch-discipline',
          severity: 'warning',
          title: 'Operator discipline drift detected',
          summary: 'At least one demo result was linked to an off-signal execution.',
          recommendations: ['Review why the operator deviated from the focused signal.'],
          confirmation_required_for_changes: true,
        },
      ],
    }
    sessionControlSnapshot = {
      preflight: {
        status: 'pass',
        blocking_reason: null,
        checks: [
          {
            check_id: 'data-freshness',
            label: 'Data freshness',
            status: 'ok',
            reason: 'Market data is fresh enough for session start.',
            blocks_start: false,
          },
        ],
      },
      briefing: {
        shortlist: [
          {
            signal_id: 'sig-btcusdt',
            symbol: 'BTCUSDT',
            direction: 'bullish',
            state: 'active',
            confidence: 0.83,
            ranking_score: 0.88,
            setup_summary: 'Bullish continuation with high liquidity and active conviction.',
          },
        ],
        market_context: 'Market status is fresh, workspace posture is normal.',
        sentiment_summary: 'Signals show acceptable context coverage.',
        active_strategy: 'momentum',
        risk_alerts: ['No elevated risk alerts in the current shortlist.'],
        ai_summary: 'Chief Agent uses GPT-5.4. Active AI conflicts: 0.',
      },
      lifecycle: {
        lifecycle_state: 'idle',
        runtime_state: 'background_monitoring',
        session_id: null,
        current_pair_symbol: null,
        current_signal_id: null,
        started_at: null,
        paused_at: null,
        resume_ready: false,
        can_start: true,
        can_pause: false,
        can_resume: false,
        can_complete: false,
      },
      pending_pair_replacement: null,
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
        technical_context: ['Liquidity high', 'Volatility score 0.64', 'Availability fresh'],
        execution_notes: ['Signal direction: bullish.', 'Look for confirmation on Binance before any manual execution.'],
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

        if (url.endsWith('/demo-trading/overview') && method === 'GET') {
          return Promise.resolve(new Response(JSON.stringify(demoTradingSnapshot), { status: 200 }))
        }

        if (url.endsWith('/demo-trading/log-current') && method === 'POST') {
          demoTradingSnapshot.records.unshift({
            record_id: 2,
            session_id: 'session-1',
            signal_id: 'sig-btcusdt',
            symbol: 'BTCUSDT',
            executed_symbol: null,
            operator_action: 'entered',
            operator_notes: null,
            recorded_at: '2026-04-21T15:02:00Z',
            external_trade_id: null,
            broker_status: 'awaiting_result',
            entry_price: null,
            exit_price: null,
            pnl_pct: null,
            observed_at: null,
            outcome_status: 'unresolved',
            awaiting_result: true,
          })
          demoTradingSnapshot.readiness.total_records = demoTradingSnapshot.records.length
          demoTradingSnapshot.readiness.outcome_counts.unresolved = 2
          return Promise.resolve(new Response(JSON.stringify(demoTradingSnapshot), { status: 200 }))
        }

        if (url.endsWith('/demo-trading/results/ingest') && method === 'POST') {
          demoTradingSnapshot.records[0].broker_status = 'closed'
          demoTradingSnapshot.records[0].pnl_pct = 2.4
          demoTradingSnapshot.records[0].outcome_status = 'matched'
          demoTradingSnapshot.records[0].awaiting_result = false
          demoTradingSnapshot.records[0].observed_at = '2026-04-21T15:05:00Z'
          demoTradingSnapshot.readiness.resolved_record_count = 1
          demoTradingSnapshot.readiness.profitable_record_count = 1
          demoTradingSnapshot.readiness.cumulative_pnl_pct = 2.4
          demoTradingSnapshot.readiness.outcome_counts.matched = 1
          demoTradingSnapshot.readiness.outcome_counts.unresolved = 1
          return Promise.resolve(new Response(JSON.stringify(demoTradingSnapshot), { status: 200 }))
        }

        if (url.includes('/session-review/overview') && method === 'GET') {
          if (url.includes('pair=BTCUSDT')) {
            return Promise.resolve(
              new Response(
                JSON.stringify({
                  ...sessionReviewSnapshot,
                  summary: {
                    ...sessionReviewSnapshot.summary,
                    total_demo_records: 1,
                    resolved_demo_records: 1,
                    cumulative_pnl_pct: 2.4,
                  },
                  filters: { ...sessionReviewSnapshot.filters, pair: 'BTCUSDT' },
                  records: [sessionReviewSnapshot.records[0]],
                }),
                { status: 200 },
              ),
            )
          }
          return Promise.resolve(new Response(JSON.stringify(sessionReviewSnapshot), { status: 200 }))
        }

        if (url.endsWith('/session-review/feedback') && method === 'POST') {
          sessionReviewSnapshot.feedback.unshift({
            feedback_id: 1,
            session_id: 'session-1',
            signal_id: 'sig-btcusdt',
            symbol: 'BTCUSDT',
            strategy_mode: 'momentum',
            model_version: 'openai-gpt-5.4',
            confidence_band: 'high',
            outcome_status: 'matched',
            feedback_label: 'useful',
            notes: null,
            created_at: '2026-04-21T15:10:00Z',
            score: 1,
          })
          sessionReviewSnapshot.summary.feedback_count = 1
          return Promise.resolve(new Response(JSON.stringify(sessionReviewSnapshot), { status: 200 }))
        }

        if (url.endsWith('/session/overview') && method === 'GET') {
          return Promise.resolve(new Response(JSON.stringify(sessionControlSnapshot), { status: 200 }))
        }

        if (url.endsWith('/session/start') && method === 'POST') {
          sessionControlSnapshot.lifecycle = {
            ...sessionControlSnapshot.lifecycle,
            lifecycle_state: 'active_session',
            runtime_state: 'active_session',
            session_id: 'session-1',
            current_pair_symbol: 'BTCUSDT',
            current_signal_id: 'sig-btcusdt',
            started_at: '2026-04-21T15:00:00Z',
            can_start: false,
            can_pause: true,
            can_resume: false,
            can_complete: true,
          }
          return Promise.resolve(new Response(JSON.stringify(sessionControlSnapshot), { status: 200 }))
        }

        if (url.endsWith('/session/replacement/review') && method === 'POST') {
          sessionControlSnapshot.pending_pair_replacement = {
            review_id: 'replacement-1',
            current_symbol: 'BTCUSDT',
            proposed_symbol: 'SOLUSDT',
            severity: 'warning',
            summary: 'Review replacement from BTCUSDT to SOLUSDT.',
            reasons_to_switch: ['SOLUSDT ranking score is 0.91.'],
            risks: ['Focus will move away from BTCUSDT.'],
            approval_required: true,
            blocks_apply: false,
          }
          return Promise.resolve(
            new Response(JSON.stringify(sessionControlSnapshot.pending_pair_replacement), { status: 200 }),
          )
        }

        if (url.endsWith('/session/replacement/apply') && method === 'POST') {
          sessionControlSnapshot.lifecycle.current_pair_symbol = 'SOLUSDT'
          sessionControlSnapshot.pending_pair_replacement = null
          return Promise.resolve(new Response(JSON.stringify(sessionControlSnapshot), { status: 200 }))
        }

        if (url.endsWith('/session/pause') && method === 'POST') {
          sessionControlSnapshot.lifecycle.lifecycle_state = 'paused'
          sessionControlSnapshot.lifecycle.runtime_state = 'paused'
          sessionControlSnapshot.lifecycle.paused_at = '2026-04-21T15:05:00Z'
          sessionControlSnapshot.lifecycle.can_pause = false
          sessionControlSnapshot.lifecycle.can_resume = true
          return Promise.resolve(new Response(JSON.stringify(sessionControlSnapshot), { status: 200 }))
        }

        if (url.endsWith('/session/resume') && method === 'POST') {
          sessionControlSnapshot.lifecycle.lifecycle_state = 'active_session'
          sessionControlSnapshot.lifecycle.runtime_state = 'active_session'
          sessionControlSnapshot.lifecycle.paused_at = null
          sessionControlSnapshot.lifecycle.can_pause = true
          sessionControlSnapshot.lifecycle.can_resume = false
          return Promise.resolve(new Response(JSON.stringify(sessionControlSnapshot), { status: 200 }))
        }

        if (url.endsWith('/session/complete') && method === 'POST') {
          sessionControlSnapshot.lifecycle.lifecycle_state = 'review'
          sessionControlSnapshot.lifecycle.runtime_state = 'review'
          sessionControlSnapshot.lifecycle.can_pause = false
          sessionControlSnapshot.lifecycle.can_resume = false
          sessionControlSnapshot.lifecycle.can_complete = false
          return Promise.resolve(new Response(JSON.stringify(sessionControlSnapshot), { status: 200 }))
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

  it('runs the session lifecycle and pair replacement flow', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /session control/i }))
    expect(await screen.findByRole('heading', { name: /session control/i })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /hard preflight/i })).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /start session/i }))
    expect(await screen.findByText(/current pair: BTCUSDT/i)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /review pair replacement/i }))
    expect(await screen.findByText(/review replacement from BTCUSDT to SOLUSDT/i)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /apply pair replacement/i }))
    expect(await screen.findByText(/current pair: SOLUSDT/i)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /pause session/i }))
    expect(await screen.findByText(/lifecycle:/i)).toBeInTheDocument()
    expect((await screen.findAllByText(/paused/i)).length).toBeGreaterThan(0)

    fireEvent.click(await screen.findByRole('button', { name: /resume session/i }))
    fireEvent.click(await screen.findByRole('button', { name: /complete session/i }))
    expect(await screen.findAllByText(/review/i)).not.toHaveLength(0)
  })

  it('tracks demo validation actions and result ingest', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /demo validation/i }))
    expect(await screen.findByRole('heading', { name: /demo validation/i })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /readiness gates/i })).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /log entered trade/i }))
    expect(await screen.findAllByText(/unresolved/i)).not.toHaveLength(0)

    fireEvent.click((await screen.findAllByRole('button', { name: /mark win/i }))[0])
    expect(await screen.findAllByText(/matched/i)).not.toHaveLength(0)
    expect(await screen.findByText(/cumulative pnl: 2.4%/i)).toBeInTheDocument()
  })

  it('renders session review, filters by pair, and captures feedback', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /session review/i }))
    expect(await screen.findByRole('heading', { name: /session review/i })).toBeInTheDocument()
    expect(await screen.findByText(/operator discipline drift detected/i)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: 'BTCUSDT' }))
    expect(await screen.findByText(/total demo records: 1/i)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: /mark useful/i }))
    expect(await screen.findByText(/feedback count: 1/i)).toBeInTheDocument()
    expect(await screen.findByText(/label: useful/i)).toBeInTheDocument()
  })
})
