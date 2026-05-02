# CLAY Mission Control v1 — Project Overview Report

Дата: 2026-04-16
Статус: quick orientation report

## 1. Назначение проекта

`CLAY Mission Control v1` — это локальная `web-first` торгово-аналитическая панель для ручной работы на `Binance Spot`.

Проект предназначен для:

- фонового мониторинга крипторынка;
- сбора рыночных и внешних данных;
- генерации ранжированных торговых сигналов;
- поддержки ручного принятия решений через UI и AI-assisted workflow;
- накопления истории, audit trail, feedback и demo-validation evidence.

Ключевое ограничение `v1`:

- система **не исполняет сделки автоматически**;
- пользователь совершает сделки вручную;
- архитектура строится вокруг explainability, operator control, risk-discipline и degraded behavior.

## 2. Текущее состояние проекта

Проект находится не на стадии готового приложения, а на стадии **полного инженерного planning package**.

В рабочем дереве сейчас нет прикладного исходного кода `frontend/backend`.
Основное содержимое проекта — это planning-артефакты, которые подготавливают реализацию:

- `blueprint`;
- `execution backlog`;
- `ADR`;
- `build specs`;
- `implementation plans`;
- `runbook`;
- handoff/session-summary документы;
- финальный `master planning review`.

Иными словами: это не “пустой проект”, а **подробно спроектированный проект перед фазой разработки**.

## 3. Структура каталогов

### Корень проекта

В корне лежат основные документы верхнего уровня:

- `blueprint-v1.md` — главный инженерный blueprint;
- `execution-backlog-v1.md` — декомпозиция на эпики, задачи и подзадачи;
- `tech-stack-v1.md` — канонический стек и baseline toolchain;
- `index.md` — обзорный индекс проекта;
- `master-planning-review-v1.md` — итоговый review и approval-мост перед реализацией;
- `session-summary-*.md`, `handoff-*.md`, `next-chat-prompt.md` — continuity и handoff-контекст между planning-сессиями.

### `adrs/`

Содержит архитектурные решения уровня `ADR`:

- runtime state model;
- config validation and rollback policy;
- transport policy (`HTTP/JSON`, `SSE`, `WebSocket`);
- storage baseline and phased extensions;
- model/provider abstraction.

Это слой фиксированных архитектурных решений, чтобы реализация потом не превращалась в freestyle-config-metal.

### `build_specs/`

Содержит `12` per-epic build-spec документов: от `E1` до `E12`.

Они описывают:

- цель каждого эпика;
- scope / out-of-scope;
- пользовательские сценарии;
- канонические сущности;
- UI/API/data expectations;
- acceptance criteria.

### `implementation_plans/`

Содержит execution-grade implementation plans по эпикам `E1–E12` и `README`.

Это самый прикладной planning-слой: в нём уже разложены:

- file structure;
- backend/frontend responsibilities;
- TDD-порядок задач;
- тестовые шаги;
- команды запуска;
- логика реализации по конкретным задачам.

### `runbooks/`

Содержит operational documentation по критическим runtime-сценариям.

Сейчас там есть runbook по:

- `preflight`;
- `degraded mode`;
- recovery-oriented поведению.

## 4. Ключевые модули проекта

Проект логически разбит на эпики `E1–E12`.

### Foundation

- `E1` — runtime foundation and local control plane
- `E2` — data ingestion and local historical store
- `E4` — control center and runtime operations

Это фундамент системы: состояния, конфиги, сервисное управление, ingestion и operational visibility.

### Analyst workflow

- `E3` — trading screen and live signal workspace
- `E5` — AI roles, orchestration and model assignment
- `E6` — signal lifecycle, ranking and risk-control
- `E7` — session lifecycle: preflight, briefing, active mode, pause

Это основной рабочий цикл аналитика/трейдера.

### Validation and review

- `E8` — demo trading integration and result tracking
- `E9` — audit trail, feedback and session review

Это validation-contour, который связывает сигналы с реальными demo outcomes и review loop.

### Extensions and hardening

- `E10` — knowledge base and research layer
- `E11` — backtesting, replay and model/strategy activation
- `E12` — reliability, degraded mode and release readiness

Это слой расширения, проверки и operational hardening.

## 5. Используемые технологии и инструменты

По зафиксированному стеку `v1` проект ориентирован на следующий baseline.

### Frontend

- `React 19`
- `TypeScript 5.x`
- `Vite`
- `React Router`
- `Zustand`
- `TanStack Query`
- `shadcn/ui`
- `Tailwind CSS 4`
- `TanStack Table`
- `Lightweight Charts`
- `Recharts`
- `Vitest`
- `Testing Library`
- `Playwright`

### Backend

- `Python 3.12+`
- `FastAPI`
- `Pydantic v2`
- `SQLAlchemy 2.x`
- `Alembic`
- `httpx`
- `APScheduler`
- `pytest`
- `ruff`
- `mypy`
- `uv`

### Storage

- `PostgreSQL 16+`
- `TimescaleDB 2.x`
- `pgvector` как phase-later extension для knowledge/retrieval слоя

## 6. Основные особенности проекта

### Planning-first architecture

Проект спроектирован сверху вниз:

- сначала source-of-truth;
- затем backlog;
- затем ADR;
- затем build-spec по эпикам;
- затем implementation plans;
- затем master review.

Это сильная сторона проекта: архитектура и sequencing зафиксированы до старта кода.

### Control-first и explainability-first

Архитектура строится вокруг:

- operator visibility;
- hard preflight;
- risk controls;
- audit trail;
- review loop;
- degraded mode;
- explicit confirmations вместо silent automation.

### Чёткие границы `v1`

Из planning явно исключены:

- auto-execution;
- `Binance Futures`;
- multi-user access model;
- hidden autonomous strategy/model switching;
- knowledge layer в hot path каждого сигнала.

## 7. Потенциальные проблемы и риски

### 1. В проекте пока нет прикладного кода

Это не баг анализа, а факт состояния.
Проект implementation-ready на уровне planning, но ещё не implementation-complete.

### 2. Высокая архитектурная насыщенность

Документация зрелая и подробная, но при старте разработки есть риск:

- расползания scope;
- попытки реализовывать слишком много сразу;
- преждевременного polishing UI без backend truth.

### 3. Риск путаницы между planning-ready и product-ready

Planning phase завершена, но это ещё не означает:

- готовность к demo-stage;
- готовность к устойчивому runtime;
- готовность к реальной торговле.

### 4. Индекс `index.md` частично устарел

Он полезен как историческая точка входа, но уже не отражает полное текущее состояние planning-chain так хорошо, как `implementation_plans/README.md` и `master-planning-review-v1.md`.

## 8. Итоговый вывод

`CLAY Mission Control v1` — это хорошо структурированный, зрелый planning-проект для локальной trading/analysis панели с AI-assisted workflow и жёстким акцентом на контроль, explainability и validation.

Сильнейшая сторона проекта:

- planning уже собран как цельная инженерная система `E1–E12`.

Главное текущее ограничение:

- проект ещё не перешёл из planning-phase в фактическую реализацию.

Лучший практический вывод для быстрого ознакомления:

- проект **готов к началу разработки**;
- структура проекта описана достаточно полно;
- основная логика, зависимости и ограничения уже зафиксированы;
- следующий реальный шаг — не дописывать ещё десяток планов, а начинать implementation по волнам, начиная с foundation.
