> **Перенесено из `docs/planning/` (2026-06-13).** Апрельский артефакт планирования,
> сохранён как канон в mission-control. Историю происхождения см. git log --follow.

# Clay v1 — Approved Stack

Дата: 2026-04-16
Статус: approved baseline for implementation start

## 1. Цель документа

Этот документ фиксирует утверждённый baseline-стек для начала реализации `Clay v1`.

Он нужен, чтобы:

- не возвращаться к выбору стека перед каждым стартом задачи;
- не расползаться в альтернативы без реальной причины;
- удерживать согласованность между backend, frontend, storage, transport и AI integration.

## 2. Итоговый вывод

Текущий стек считается **правильно выбранным, современным и подходящим** для `Clay v1`.

Он согласуется с типом продукта:

- `local web-first trading workspace`
- `manual trading support`
- `AI-assisted analysis`
- `review and risk-control`
- `operator-visible degraded behavior`

Важно:

- стек подходит для `Clay` как analyst/control system;
- стек не проектируется как `HFT`-движок или ultra-low-latency auto-execution platform;
- это соответствует реальным границам `v1`.

## 3. Approved languages

### Frontend

- `TypeScript`

Почему:

- даёт safety на UI contracts;
- хорошо сочетается с React ecosystem;
- удобен для typed API contracts и realtime UI state.

### Backend

- `Python 3.14`

Почему:

- хорошо подходит для API/orchestration/data pipelines;
- удобен для AI/provider integrations;
- хорошо согласуется с FastAPI, Pydantic, SQLAlchemy и async I/O;
- для greenfield-проекта логично стартовать уже с актуальной stable веткой `3.14`.

## 4. Approved frontend stack

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

Почему этот набор подходит:

- быстро поднимает современный UI;
- хорошо подходит для live workspace, cards, tables, dashboards и signals;
- поддерживает нормальный DX без чрезмерной сложности;
- позволяет держать typed contracts между backend и frontend.

## 5. Approved backend stack

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

Почему этот набор подходит:

- хорошо решает задачи API, orchestration и service control;
- поддерживает async workflows;
- нормально подходит для provider integrations и background processing;
- остаётся достаточно лёгким для single-user local-first architecture.

## 6. Approved storage stack

- `PostgreSQL 16+`
- `TimescaleDB 2.x`
- `pgvector` только как `phase-later` extension

Почему:

- `PostgreSQL` даёт strong baseline для config, sessions, audit, review и relational state;
- `TimescaleDB` хорошо подходит для market/history time-series workloads;
- `pgvector` нужен не в day-one foundation, а только когда реально включается semantic retrieval layer.

## 7. Approved transport policy

### Основной transport

- `HTTP/JSON` для:
  - commands
  - snapshots
  - config actions
  - CRUD-like requests

- `SSE` для:
  - live status updates
  - signal updates
  - timers
  - incident/degraded events
  - AI streaming output

### Ограниченное использование `WebSocket`

`WebSocket` разрешён только там, где действительно нужна двусторонняя realtime-коммуникация.

Для `Clay v1` он не является transport default.

Причина:

- `SSE` лучше совпадает с реальным профилем UI;
- `SSE` естественно ложится на AI streaming;
- не нужно превращать каждую live-поверхность в websocket-культ.

## 8. AI integration compatibility

Текущий стек хорошо согласуется с современными AI provider APIs.

Причина:

- OpenAI streaming поддерживает `SSE`
- Anthropic streaming поддерживает `SSE`
- Gemini streaming поддерживает streaming content generation

Следовательно, наш backend stack хорошо подходит для:

- provider API calls;
- async orchestration;
- stream normalization;
- AI response routing в UI.

## 9. Обязательные архитектурные правила для AI layer

Чтобы стек реально работал хорошо вместе с AI-моделями, нужно соблюдать следующие правила:

### 1. Backend-only provider access

Frontend не должен ходить напрямую в provider APIs.

Только backend:

- хранит provider integration logic;
- обрабатывает auth/secrets;
- нормализует ответы;
- передаёт в UI уже внутренние Clay contracts.

### 2. Provider abstraction layer

Нужен обязательный internal provider abstraction layer.

Это защищает проект от:

- жёсткой привязки к одному provider;
- различий в response schema;
- хаотичного mixing SDK behavior across the codebase.

### 3. Stream normalization

Streaming output от провайдеров должен приводиться к единому internal event format.

UI не должен знать детали OpenAI/Anthropic/Gemini event schema.

### 4. AI is not the only truth source

AI layer не должен быть единственной точкой истины в signal pipeline.

Он должен:

- синтезировать;
- объяснять;
- ранжировать;
- предлагать;

но не заменять market data, risk rules и session discipline.

### 5. Graceful degradation

AI latency и provider availability нестабильны по своей природе.

Поэтому:

- degraded mode обязателен;
- fallback behavior обязателен;
- confidence semantics не могут оставаться прежними в degraded/fallback mode.

## 10. Что специально не выбирается

Для `v1` мы специально не выбираем:

- `Next.js` как обязательный frontend shell;
- `Django` или heavier backend framework;
- `Redis` как обязательную day-one зависимость;
- `Kafka`, `NATS` или другую тяжёлую event infra;
- local heavy LLM runtime как baseline requirement;
- vector stack в day-one foundation.

Причина простая:

- это либо избыточно для `v1`,
- либо не соответствует current product boundaries,
- либо добавляет complexity раньше времени.

## 11. Финальный verdict

Для старта реализации `Clay v1` утверждается такой baseline:

- `React 19 + TypeScript + Vite` на frontend
- `Python 3.14 + FastAPI + Pydantic v2` на backend
- `PostgreSQL + TimescaleDB` на storage layer
- `HTTP/JSON + SSE` как transport default
- provider abstraction and backend-managed AI integration как обязательная архитектурная граница

Итог:

**Стек approved for implementation start.**
