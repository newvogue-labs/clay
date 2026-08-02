# Clay ADR Master-Index

Дата: 2026-06-24
Статус: сводный индекс всех ADR проекта

## Правило

**`docs/adr/` — ЕДИНСТВЕННЫЙ канонический дом для всех ADR от 016 и далее.** Новые ADR (016+) создавать только здесь.

**`docs/mission-control/adrs/` — ЗАМОРОЖЕННЫЙ архив ADR 001–015.** Не пополнять, не перенумеровывать. Существующие файлы не перемещать.

**Статусы ADR (канонический словарь):** `Proposed` · `Accepted` · `Rejected` · `Superseded` · `Deprecated`. Статус в шапке — первое слово после `Status:`, регистронезависимо; пояснение после него — свободный текст.

## Полная таблица ADR

| № | Заголовок | Статус | Расположение | Ссылка |
|---|-----------|--------|-------------|--------|
| 001 | Runtime State Model And Control Plane Boundary | Accepted | mc-archive | [`adr-001-runtime-state-model.md`](../mission-control/adrs/adr-001-runtime-state-model.md) |
| 002 | Config Validation And Rollback Policy | Accepted | mc-archive | [`adr-002-config-validation-and-rollback-policy.md`](../mission-control/adrs/adr-002-config-validation-and-rollback-policy.md) |
| 003 | Transport Policy (HTTP / SSE / WebSocket) | Accepted | mc-archive | [`adr-003-transport-policy-http-sse-websocket.md`](../mission-control/adrs/adr-003-transport-policy-http-sse-websocket.md) |
| 004 | Storage Baseline And Phased Extensions | Accepted | mc-archive | [`adr-004-storage-baseline-and-phased-extensions.md`](../mission-control/adrs/adr-004-storage-baseline-and-phased-extensions.md) |
| 005 | Model Provider Abstraction | Accepted | mc-archive | [`adr-005-model-provider-abstraction.md`](../mission-control/adrs/adr-005-model-provider-abstraction.md) |
| 006 | *(reserved-gap)* | — | mc-archive | намеренный пропуск нумерации |
| 007 | Scheduler Side-Effect & Lifecycle Contract | Accepted | mc-archive | [`adr-007-scheduler-side-effect-and-lifecycle-contract.md`](../mission-control/adrs/adr-007-scheduler-side-effect-and-lifecycle-contract.md) |
| 008 | Exchange Abstraction & Multi-Exchange Portability | Proposed | mc-archive | [`adr-008-exchange-abstraction-and-multi-exchange-portability.md`](../mission-control/adrs/adr-008-exchange-abstraction-and-multi-exchange-portability.md) |
| 009 | Внешние LLM только через локальный шлюз за TUN | Accepted | mc-archive | [`adr-009-external-llm-egress-gateway.md`](../mission-control/adrs/adr-009-external-llm-egress-gateway.md) |
| 010 | Chief-agent на Gemini free-tier через шлюз | Accepted | mc-archive | [`adr-010-chief-agent-gemini-free-tier.md`](../mission-control/adrs/adr-010-chief-agent-gemini-free-tier.md) |
| 011 | Forecast: локальная количественная модель | Accepted | mc-archive | [`adr-011-local-quant-forecast-model.md`](../mission-control/adrs/adr-011-local-quant-forecast-model.md) |
| 012 | News/sentiment: demo-источник для v1 | Accepted | mc-archive | [`adr-012-news-sentiment-demo-source-v1.md`](../mission-control/adrs/adr-012-news-sentiment-demo-source-v1.md) |
| 013 | Provider-Pool как resource-manager (homo/hetero) | Proposed | mc-archive | [`adr-013-provider-pool-resource-manager.md`](../mission-control/adrs/adr-013-provider-pool-resource-manager.md) |
| — | Addendum 013 (2026-06-17): граница интеграции, stateful provider-pool | Accepted | mc-archive | [`adr-013-addendum-2026-06-17.md`](../mission-control/adrs/adr-013-addendum-2026-06-17.md) |
| 014 | config_snapshots — версионирование промптов ролей | Proposed | mc-archive | [`adr-014-config-snapshots-prompt-versioning.md`](../mission-control/adrs/adr-014-config-snapshots-prompt-versioning.md) |
| 015 | Degraded-mode AI-слоя | Accepted | mc-archive | [`adr-015-degraded-mode.md`](../mission-control/adrs/adr-015-degraded-mode.md) |
| 016 | Config write-path под автономный reconcile | Accepted | docs/adr | [`016-config-write-path.md`](016-config-write-path.md) |
| 017 | Homogeneous role registry (gemma-4-31b as chief-eligible) | Proposed | docs/adr | [`017-homogeneous-role-registry.md`](017-homogeneous-role-registry.md) |
| 018 | Pool-Health Degraded Mode (never-empty invariant) | Accepted | docs/adr | [`018-pool-health-never-empty.md`](018-pool-health-never-empty.md) |
| 019 | *(резерв: freqtrade-донор)* | — | — | |
| 020 | Position Sizing — Fractional Kelly + EV-Gate | Accepted | docs/adr | [`020-position-sizing-kelly-ev-gate.md`](020-position-sizing-kelly-ev-gate.md) |
| 021 | Session-Level Risk Limits (Admission Gate) | Accepted | docs/adr | [`021-session-risk-limits.md`](021-session-risk-limits.md) |
| 022 | *(резерв: AgentQuant-донор)* | — | — | |
| 023 | ops.ai_agent_runs — Indexes + Retention Policy | Accepted | docs/adr | [`023-ai-agent-runs-retention.md`](023-ai-agent-runs-retention.md) |
| 024 | Deterministic Replay Harness + Trade Provenance | Accepted | docs/adr | [`024-deterministic-replay-and-trade-provenance.md`](024-deterministic-replay-and-trade-provenance.md) |
| 025 | Execution Layer & Real-Money Gate | Accepted | docs/adr | [`025-execution-layer-and-real-money-gate.md`](025-execution-layer-and-real-money-gate.md) |
| 026 | Freshness Dual-Policy (per-pair worst-of + focused-pair gate) | Accepted | docs/adr | [`026-freshness-dual-policy.md`](026-freshness-dual-policy.md) |
| 027 | Min-Volume Floor Guard (anti-slippage signal gate) | Accepted | docs/adr | [`027-min-volume-floor-guard.md`](027-min-volume-floor-guard.md) |
| 028 | *(резерв)* | — | — | |
| 029 | Capital Exposure Hard-Block (dual-tier off-by-default) | Accepted | docs/adr | [`029-capital-exposure-hard-block.md`](029-capital-exposure-hard-block.md) |
| 030 | Advisory #knowledge → chief-agent (advisory-only) | Accepted | docs/adr | [`030-advisory-knowledge-chief-agent.md`](030-advisory-knowledge-chief-agent.md) |
| 031 | Notion-mirror publisher — односторонний sync vault → Notion | Accepted | docs/adr | [`031-notion-mirror-publisher.md`](031-notion-mirror-publisher.md) |
| 032 | Exchange Execution Adapter (Multi-Venue) | Accepted | docs/adr | [`032-exchange-execution-adapter-multi-venue.md`](032-exchange-execution-adapter-multi-venue.md) |
| — | Addendum 032: Bybit Environment → Endpoint Mapping | Accepted | docs/adr | [`032-addendum-bybit-environment-endpoint-mapping.md`](032-addendum-bybit-environment-endpoint-mapping.md) |
| 033 | Execution Proof-Gate | Accepted | docs/adr | [`033-execution-proof-gate.md`](033-execution-proof-gate.md) |
| 034 | Unknown Resolver + Durable Halt Latch | Accepted | docs/adr | [`034-unknown-resolver-halt-latch.md`](034-unknown-resolver-halt-latch.md) |
| 035 | Advisory DB-Size Monitor (D-13 #1) | Accepted | docs/adr | [`035-db-size-monitor.md`](035-db-size-monitor.md) |
| 036 | TimescaleDB Compression for market_bars (D-13 #2) | Accepted | docs/adr | [`036-market-bars-compression.md`](036-market-bars-compression.md) |
| 037 | TimescaleDB Retention for market_bars — default-OFF (D-13 #3) | Accepted | docs/adr | [`037-market-bars-retention.md`](037-market-bars-retention.md) |
| 038 | TimescaleDB Continuous Aggregate market_bars_1d (D-13 #4) | Accepted | docs/adr | [`038-market-bars-continuous-aggregate.md`](038-market-bars-continuous-aggregate.md) |
| 039 | Политика зависимостей — пиннинг, отказ от вендоринга, контракт на границе | Accepted | docs/adr | [`039-dependency-policy.md`](039-dependency-policy.md) |
| 040 | Soak-harness — ручной 24ч soak vs CI, повторяемое оснащение (D-58) | Accepted | docs/adr | [`040-soak-harness-manual-24h.md`](040-soak-harness-manual-24h.md) |
| 041+ | свободны | — | — | |

## Карта номеров

| Номер | Статус | Примечание |
|-------|--------|-----------|
| 006 | намеренный gap | reserved-gap в mc-архиве |
| 018 | pool-health | переименован из ADR-015 (коллизия разрешена 2026-06-24; mc ADR-015 = «Degraded-mode AI-слоя» сохраняет 015) |
| 019 | резерв | freqtrade-донор |
| 022 | резерв | AgentQuant-донор |
| 032 | один номер, один ADR + один аддендум | аддендум не занимает собственный номер, файл с префиксом 032-addendum- |
| — | ccxt без нового номера | реализация ADR-008 (exchange abstraction) |

## Разрешение коллизии 015

mc `adr-015` — «Degraded-mode AI-слоя» (Accepted, 2026-06-13) — старший, густо прошит cross-ref → **сохранил 015**.  
docs/adr `015` → **018** — «Pool-Health Degraded Mode (never-empty invariant)» (Accepted, 2026-06-17).

## Out of scope

- Физический перенос ADR 001–015 из `mission-control/adrs/` → deferred (опциональный S-DOCSYNC-3).
- Абсолютные Obsidian-пути (`/home/emma/Documents/Obsidian/…`) — pre-existing, вне репо, не трогать.
