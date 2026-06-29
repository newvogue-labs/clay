# Clay ADR Master-Index

Дата: 2026-06-24
Статус: сводный индекс всех ADR проекта

## Правило

**`docs/adr/` — ЕДИНСТВЕННЫЙ канонический дом для всех ADR от 016 и далее.** Новые ADR (016+) создавать только здесь.

**`docs/mission-control/adrs/` — ЗАМОРОЖЕННЫЙ архив ADR 001–015.** Не пополнять, не перенумеровывать. Существующие файлы не перемещать.

## Полная таблица ADR

| № | Заголовок | Статус | Расположение | Ссылка |
|---|-----------|--------|-------------|--------|
| 001 | Runtime State Model And Control Plane Boundary | accepted | mc-archive | [`adr-001-runtime-state-model.md`](../mission-control/adrs/adr-001-runtime-state-model.md) |
| 002 | Config Validation And Rollback Policy | accepted | mc-archive | [`adr-002-config-validation-and-rollback-policy.md`](../mission-control/adrs/adr-002-config-validation-and-rollback-policy.md) |
| 003 | Transport Policy (HTTP / SSE / WebSocket) | accepted | mc-archive | [`adr-003-transport-policy-http-sse-websocket.md`](../mission-control/adrs/adr-003-transport-policy-http-sse-websocket.md) |
| 004 | Storage Baseline And Phased Extensions | accepted | mc-archive | [`adr-004-storage-baseline-and-phased-extensions.md`](../mission-control/adrs/adr-004-storage-baseline-and-phased-extensions.md) |
| 005 | Model Provider Abstraction | accepted | mc-archive | [`adr-005-model-provider-abstraction.md`](../mission-control/adrs/adr-005-model-provider-abstraction.md) |
| 006 | *(reserved-gap)* | — | mc-archive | намеренный пропуск нумерации |
| 007 | Scheduler Side-Effect & Lifecycle Contract | accepted | mc-archive | [`adr-007-scheduler-side-effect-and-lifecycle-contract.md`](../mission-control/adrs/adr-007-scheduler-side-effect-and-lifecycle-contract.md) |
| 008 | Exchange Abstraction & Multi-Exchange Portability | Proposed | mc-archive | [`adr-008-exchange-abstraction-and-multi-exchange-portability.md`](../mission-control/adrs/adr-008-exchange-abstraction-and-multi-exchange-portability.md) |
| 009 | Внешние LLM только через локальный шлюз за TUN | accepted | mc-archive | [`adr-009-external-llm-egress-gateway.md`](../mission-control/adrs/adr-009-external-llm-egress-gateway.md) |
| 010 | Chief-agent на Gemini free-tier через шлюз | accepted | mc-archive | [`adr-010-chief-agent-gemini-free-tier.md`](../mission-control/adrs/adr-010-chief-agent-gemini-free-tier.md) |
| 011 | Forecast: локальная количественная модель | accepted | mc-archive | [`adr-011-local-quant-forecast-model.md`](../mission-control/adrs/adr-011-local-quant-forecast-model.md) |
| 012 | News/sentiment: demo-источник для v1 | accepted | mc-archive | [`adr-012-news-sentiment-demo-source-v1.md`](../mission-control/adrs/adr-012-news-sentiment-demo-source-v1.md) |
| 013 | Provider-Pool как resource-manager (homo/hetero) | Proposed | mc-archive | [`adr-013-provider-pool-resource-manager.md`](../mission-control/adrs/adr-013-provider-pool-resource-manager.md) |
| — | Addendum 013 (2026-06-17): граница интеграции, stateful provider-pool | Accepted | mc-archive | [`adr-013-addendum-2026-06-17.md`](../mission-control/adrs/adr-013-addendum-2026-06-17.md) |
| 014 | config_snapshots — версионирование промптов ролей | Proposed | mc-archive | [`adr-014-config-snapshots-prompt-versioning.md`](../mission-control/adrs/adr-014-config-snapshots-prompt-versioning.md) |
| 015 | Degraded-mode AI-слоя | accepted | mc-archive | [`adr-015-degraded-mode.md`](../mission-control/adrs/adr-015-degraded-mode.md) |
| 016 | Config write-path под автономный reconcile | accepted | docs/adr | [`016-config-write-path.md`](016-config-write-path.md) |
| 017 | Homogeneous role registry (gemma-4-31b as chief-eligible) | Proposed | docs/adr | [`017-homogeneous-role-registry.md`](017-homogeneous-role-registry.md) |
| 018 | Pool-Health Degraded Mode (never-empty invariant) | accepted | docs/adr | [`018-pool-health-never-empty.md`](018-pool-health-never-empty.md) |
| 019 | *(резерв: freqtrade-донор)* | — | — | |
| 020 | Position Sizing — Fractional Kelly + EV-Gate | accepted | docs/adr | [`020-position-sizing-kelly-ev-gate.md`](020-position-sizing-kelly-ev-gate.md) |
| 021 | Session-Level Risk Limits (Admission Gate) | Proposed | docs/adr | [`021-session-risk-limits.md`](021-session-risk-limits.md) |
| 022 | *(резерв: AgentQuant-донор)* | — | — | |
| 023 | ops.ai_agent_runs — Indexes + Retention Policy | accepted | docs/adr | [`023-ai-agent-runs-retention.md`](023-ai-agent-runs-retention.md) |
| 024 | Deterministic Replay Harness + Trade Provenance | Proposed | docs/adr | [`024-deterministic-replay-and-trade-provenance.md`](024-deterministic-replay-and-trade-provenance.md) |
| 025 | Execution Layer & Real-Money Gate | accepted | docs/adr | [`025-execution-layer-and-real-money-gate.md`](025-execution-layer-and-real-money-gate.md) |
| 026 | Freshness Dual-Policy (per-pair worst-of + focused-pair gate) | accepted | docs/adr | [`026-freshness-dual-policy.md`](026-freshness-dual-policy.md) |
| 027 | Min-Volume Floor Guard (anti-slippage signal gate) | accepted | docs/adr | [`027-min-volume-floor-guard.md`](027-min-volume-floor-guard.md) |
| 028+ | свободны | — | — | |

## Карта номеров

| Номер | Статус | Примечание |
|-------|--------|-----------|
| 006 | намеренный gap | reserved-gap в mc-архиве |
| 018 | pool-health | переименован из ADR-015 (коллизия разрешена 2026-06-24; mc ADR-015 = «Degraded-mode AI-слоя» сохраняет 015) |
| 019 | резерв | freqtrade-донор |
| 022 | резерв | AgentQuant-донор |
| — | ccxt без нового номера | реализация ADR-008 (exchange abstraction) |

## Разрешение коллизии 015

mc `adr-015` — «Degraded-mode AI-слоя» (Accepted, 2026-06-13) — старший, густо прошит cross-ref → **сохранил 015**.  
docs/adr `015` → **018** — «Pool-Health Degraded Mode (never-empty invariant)» (Accepted, 2026-06-17).

## Out of scope

- Физический перенос ADR 001–015 из `mission-control/adrs/` → deferred (опциональный S-DOCSYNC-3).
- Абсолютные Obsidian-пути (`/home/emma/Documents/Obsidian/…`) — pre-existing, вне репо, не трогать.
