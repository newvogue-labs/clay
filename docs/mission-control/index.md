# CLAY Mission Control — Index

Дата: 2026-04-01
Статус: project index

## Назначение

Эта папка содержит основные planning-артефакты по проекту `CLAY Mission Control`.

## Документы

- `handoff-2026-03-30.md`
  Базовый handoff-документ с ранним контекстом, ограничениями и стартовой рамкой проекта.

- `next-chat-prompt.md`
  Стартовый промпт для нового planning-чата.

- `blueprint-v1.md`
  Главный инженерный blueprint системы `v1`. §9–§10 — канон AI-слоя (роли, provider-pool, degraded-mode).

- `execution-backlog-v1.md`
  Декомпозиция blueprint в эпики, задачи и подзадачи для дальнейшей разработки.

- `tech-stack-v1.md`
  Канонический документ по технологическому стеку, transport policy, storage baseline и toolchain.

- `session-summary-2026-03-30.md`
  Короткий handoff-summary по точке остановки после planning/day-1: что уже решено и с какого UX-вопроса продолжать дальше.

- `session-summary-2026-03-31.md`
  Актуальный handoff-summary по результатам UI/UX refinement day-2: зафиксированный `v6` baseline, принятый `single focused pair` подход и точка продолжения на завтра.

- `session-summary-2026-04-01.md`
  Финальный handoff-summary по результатам UI refinement day-3: утверждённый `v15` UI baseline, рабочий dark/light theme system и точка продолжения уже после фиксации baseline.

- `build_specs/e3-trading-screen-and-live-signal-workspace.md`
  Build-spec по главному рабочему экрану CLAY: `Trading Workspace`, `single focused pair` baseline, live-state behavior и UI-facing data contracts.

## Архитектура

- ~~[DEPLOY-5 — AI Model Layer](../architecture/deploy5-ai-model-layer.md)~~ **SUPERSEDED (2026-06-13).** Live-правда — `blueprint-v1.md` §9–§10.

## Подпапки

- `build_specs/`
  Build-spec документы по отдельным эпикам.

- `adrs/`
  Короткие архитектурные решения уровня `ADR`.

- `runbooks/`
  Операционные инструкции по preflight, degraded mode, recovery и другим критичным сценариям.

- `implementation_plans/`
  Подробные implementation plans как будущая карта сборки по конкретному эпику; их наличие не означает немедленный старт реализации.

## Уже добавлено

- `tech-stack-v1.md`
- `session-summary-2026-03-30.md`
- `session-summary-2026-03-31.md`
- `session-summary-2026-04-01.md`
- `build_specs/e1-runtime-foundation-control-plane.md`
- `build_specs/e2-data-ingestion-and-local-historical-store.md`
- `build_specs/e3-trading-screen-and-live-signal-workspace.md`
- `adrs/adr-001-runtime-state-model.md`
- `adrs/adr-002-config-validation-and-rollback-policy.md`
- `adrs/adr-003-transport-policy-http-sse-websocket.md`
- `adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `adrs/adr-005-model-provider-abstraction.md`
- `adrs/adr-008-exchange-abstraction-and-multi-exchange-portability.md`
- `runbooks/runbook-001-preflight-degraded-mode.md`
- `runbooks/runbook-002-alpha-operator-path.md`
- `implementation_plans/e1-runtime-foundation-control-plane-implementation-plan.md`
- [ADR-009 — Внешние LLM только через локальный шлюз за TUN](adrs/adr-009-external-llm-egress-gateway.md)
- [ADR-010 — Chief-agent на Gemini free-tier](adrs/adr-010-chief-agent-gemini-free-tier.md)
- [ADR-011 — Forecast: локальная количественная модель](adrs/adr-011-local-quant-forecast-model.md)
- [ADR-012 — News/sentiment: demo-источник для v1](adrs/adr-012-news-sentiment-demo-source-v1.md)
- [ADR-013 — Provider-Pool как resource-manager](adrs/adr-013-provider-pool-resource-manager.md)
- [ADR-014 — config_snapshots: версионирование промптов](adrs/adr-014-config-snapshots-prompt-versioning.md)
- [ADR-015 — Degraded-mode AI-слоя](adrs/adr-015-degraded-mode.md)
- **ADR-006 — reserved-gap** (намеренный пропуск нумерации)
- ~~`build_specs/deploy5-ai-model-layer.md`~~ **SUPERSEDED**
- ~~`implementation_plans/deploy5-ai-model-layer-implementation-plan.md`~~ **SUPERSEDED** (live-правда — blueprint §9–§10)
- `runbooks/runbook-003-killswitch-egress.md`
- `runbooks/runbook-004-litellm-gateway.md`

## Как использовать

Рекомендуемый порядок чтения:

1. `handoff-2026-03-30.md`
2. `blueprint-v1.md`
3. `tech-stack-v1.md`
4. `session-summary-2026-04-01.md`
5. `build_specs/e3-trading-screen-and-live-signal-workspace.md`
6. `session-summary-2026-03-31.md`
7. `session-summary-2026-03-30.md`
8. `execution-backlog-v1.md`

`next-chat-prompt.md` использовать как стартовую точку для нового planning-чата при необходимости.

## Следующий шаг

Следующий рабочий артефакт / шаг:

- `E3 build-spec` уже собран и может использоваться как рабочая опора
- следующая зафиксированная развилка:
  - сначала `E2 implementation plan`, если хотим строгий dependency-first pipeline
  - или сразу `E3 implementation plan`, если главный приоритет уже сместился на `Trading Workspace`
- `E2 implementation plan` в таком случае остаётся документным долгом, который нужно будет догнать отдельно
