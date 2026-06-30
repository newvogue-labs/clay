# CLAY Mission Control v1 — Canonical Tech Stack

Дата: 2026-03-30
Статус: accepted for planning
Основа:

- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`

> **Актуализация (2026-06-30, DOC-3):** toolchain-канон с тех пор уточнён — Python-typing = `pyright` (не `mypy`), Python runtime = `3.14` (`requires-python >=3.14,<3.15`), forecast — локальный quant (ADR-011). Планировочные таблицы ниже сохранены; точечные факты приведены к текущему канону.

## 1. Назначение документа

Этот документ является каноническим источником истины по технологическому стеку `CLAY Mission Control v1`.

Он фиксирует:

- что выбрано для `v1` окончательно;
- что допускается, но откладывается на более поздние фазы;
- что сознательно не входит в ранний `v1`;
- какие технологические решения должны использоваться при подготовке build-spec, ADR и implementation plans.

Этот документ не описывает поведение экранов и не заменяет blueprint. Его задача — не дать архитектуре начать спорить самой с собой.

## 2. Принципы выбора стека

- стек должен соответствовать `local-first`, `single-user`, `web-first` архитектуре;
- стек не должен перегружать ПК пользователя;
- control plane должен оставаться отделённым от heavy analytics;
- realtime-механизмы должны быть минимально сложными и объяснимыми;
- day-one зависимости должны покрывать только обязательный `v1`, а не весь будущий зоопарк расширений;
- выбор инструментов должен быть предсказуемым, хорошо документируемым и безопасным для локальной разработки.

## 3. Итоговый стек v1

### 3.1 Frontend

| Слой | Выбор для `v1` | Причина |
|---|---|---|
| App shell | `Vite + React 19 + TypeScript 5.x` | Для локальной `web-first` панели не нужен SSR. `Vite` проще, легче и лучше подходит для single-PC сценария |
| Routing | `React Router` | Достаточно для разделения `Trading Workspace`, `Control Center`, `Session Review`, `Knowledge Base` и `AI Console` |
| UI system | `shadcn/ui + Tailwind CSS 4` | Даёт ownership над компонентами, хорошо подходит под кастомный mission-control UI |
| Client state | `Zustand` | Подходит для локального UI state, режимов экрана и оперативных пользовательских состояний |
| Server state | `TanStack Query` | Кэширование, refetch, invalidation, работа с control/API layer |
| Tables | `TanStack Table v8` + `TanStack Virtual` | Подходит для сигналов, audit log, session review и длинных списков |
| Financial charts | `Lightweight Charts` | Лучший fit для OHLCV, volume, markers и intraday screen |
| Analytics charts | `Recharts` | Достаточно для `P&L`, `win rate`, session analytics и post-session review |
| Notifications | `Sonner` | Лёгкий слой для локальных уведомлений и операторских предупреждений |
| AI console UI | `custom chat UI` | Для `v1` предпочтительнее прямой контроль над transport, streaming и режимами подтверждения действий |

### 3.2 Backend / Control API

| Слой | Выбор для `v1` | Причина |
|---|---|---|
| Language runtime | `Python 3.14` | Хорошо подходит для AI integrations, data pipelines и локальной orchestration-логики |
| API framework | `FastAPI` | Async, typed contracts, auto-docs, удобен для control plane |
| Validation | `Pydantic v2` | Явная валидация data contracts и runtime-конфигурации |
| Config system | `pydantic-settings` | Типизированные конфиги, `env`-интеграция и валидация |
| ORM / DB layer | `SQLAlchemy 2.x` + `Alembic` | Контроль схемы, миграции, typed queries, async-friendly подход |
| HTTP client | `httpx` | Работа с Binance, news/sentiment providers и cloud model APIs |
| Scheduling | `APScheduler` | Для `v1` лучше соответствует локальному single-node runtime, чем `Celery + Redis` |

### 3.3 Storage

| Слой | Выбор для `v1` | Статус |
|---|---|---|
| Relational store | `PostgreSQL 16+` | обязательный |
| Time-series extension | `TimescaleDB 2.x` | обязательный |
| Vector extension | `pgvector` | phase-later, обязателен с `E10`, не блокирует ранние эпики |

### 3.4 AI / Model integration

| Слой | Выбор для `v1` | Причина |
|---|---|---|
| Chief/text-heavy models | `pluggable cloud LLM providers` | Сохраняет свободу выбора между бесплатными и платными провайдерами |
| Local fallback | `optional local lightweight model layer` | Только для degraded/fallback сценариев, без тяжёлых локальных LLM |
| Forecast training | `Google Colab` | Базовая training-площадка на старте (forecast-модель = локальный quant, см. ADR-011; Colab/Lightning — только обучение burst-GPU) |
| Extended training option | `Lightning AI` | Запасной вариант, если `Colab` станет узким местом |
| Forecast inference | `local compact inference` | Соответствует железу пользователя и `local-first` архитектуре |

### 3.5 Packaging and runtime environment

| Слой | Выбор для `v1` | Статус |
|---|---|---|
| Primary form factor | `local web app` | обязательный |
| Optional desktop wrapper | `Tauri 2.x` | phase-later |
| Always-on services | `systemd --user` или эквивалентный local service manager | требуется formalize в ADR / runtime docs |
| On-demand orchestration | `control plane runtime-manager` | обязательный через `ADR-001` |

### 3.6 Tooling

| Область | Выбор для `v1` |
|---|---|
| Frontend package manager | `pnpm` |
| Python project / env management | `uv` |
| Python linting | `ruff` |
| Python typing | `pyright` |
| Python testing | `pytest` + `pytest-asyncio` |
| Frontend unit testing | `Vitest` + `Testing Library` |
| Frontend e2e | `Playwright` |

## 4. Transport policy

### 4.1 Каноническое правило

Для `v1` transport layer не должен строиться вокруг одного “магического” realtime-молотка.

Нормой считается:

- `HTTP/JSON` для CRUD, команд управления, config operations и загрузки исторических представлений;
- `SSE` для server-to-client streams:
  - status feed;
  - signal updates;
  - preflight progress;
  - AI text streaming;
  - runtime events;
- `WebSocket` только там, где реально нужна двусторонняя realtime-коммуникация.

### 4.2 Что это значит practically

- Не использовать `socket.io` как обязательную инфраструктуру `v1`.
- Не использовать `WebSocket` по умолчанию для всего подряд.
- Для `AI Console` сначала проектировать streaming через `SSE`, а не через обязательный `WebSocket`.

## 5. Что входит в day-one baseline

Обязательный baseline для `v1 planning`:

- `Vite + React + TypeScript`
- `React Router`
- `shadcn/ui + Tailwind CSS 4`
- `Zustand + TanStack Query`
- `TanStack Table + TanStack Virtual`
- `Lightweight Charts`
- `Recharts`
- `FastAPI`
- `Pydantic v2 + pydantic-settings`
- `SQLAlchemy + Alembic`
- `httpx`
- `APScheduler`
- `PostgreSQL + TimescaleDB`
- `pnpm`
- `uv`
- `ruff`
- `pyright`
- `pytest`
- `Vitest`
- `Playwright`

## 6. Что отложено

### 6.1 Допустимо позже, но не нужно цементировать в раннем `v1`

- `Tauri 2.x`
- `pgvector`
- `react-grid-layout`
- `Vercel AI SDK`
- `Celery + Redis`

### 6.2 Причины отсрочки

- эти решения не являются обязательными для early `v1`;
- они увеличивают сложность, не закрывая главный риск системы;
- их нужно принимать только тогда, когда станет ясно, что простая baseline-схема реально упирается в ограничения.

## 7. Что сознательно не принято для v1 baseline

| Вариант | Почему не выбран |
|---|---|
| `Next.js` | Для локальной панели не даёт критичной пользы, но добавляет SSR/RSC overhead |
| `Electron` | Избыточен для локального single-user сценария, тяжелее `Tauri` |
| `Redux` | Слишком тяжёл для текущего локального UI state |
| `Socket.io` | Не нужен как обязательный слой поверх уже достаточного transport policy |
| `Celery + Redis` | Слишком тяжёлый operational baseline для single-PC `v1` |
| `Tremor` как основной dashboard layer | Избыточен при наличии `shadcn/ui` + `Recharts` |

## 8. Связь с эпиками

### E0

- этот документ становится одним из master-docs проекта.

### E1

- задаёт обязательный baseline для `control-api`, scheduler, config layer и runtime separation.

### E2

- задаёт storage baseline: `PostgreSQL + TimescaleDB`;
- `pgvector` не должен блокировать market ingestion и local historical store.

### E3-E4

- задаёт frontend baseline для `Trading Workspace` и `Control Center`.

### E5-E6

- задаёт model/provider abstraction и transport policy для AI orchestration и signal delivery.

### E10

- включает `pgvector` как обязательный extension, когда knowledge layer становится реальной частью системы.

## 9. Как использовать этот документ

- при споре между build-spec и черновиком tech-stack приоритет у этого документа;
- при крупном изменении стека сначала обновляется этот документ, потом `blueprint`, потом `backlog`, потом связанные ADR;
- если решение влияет на runtime boundary, transport policy, storage baseline или model abstraction, нужно отдельное `ADR`.

## 10. Связанные ADR

Принятые:

- `ADR-002 config validation and rollback policy`
- `ADR-003 transport policy (HTTP / SSE / WebSocket)`
- `ADR-004 storage baseline and phased extensions`
- `ADR-005 model provider abstraction`

Открытые:

- нет

## 11. Источники

- React 19 — https://react.dev/blog/2024/12/05/react-19
- Tailwind CSS v4 — https://tailwindcss.com/blog/tailwindcss-v4
- shadcn/ui Tailwind v4 — https://ui.shadcn.com/docs/tailwind-v4
- TanStack Table virtualization — https://tanstack.com/table/latest/docs/guide/virtualization
- Lightweight Charts — https://github.com/tradingview/lightweight-charts
- FastAPI WebSockets — https://fastapi.tiangolo.com/advanced/websockets/
- APScheduler — https://apscheduler.readthedocs.io/en/master/userguide.html
- Tauri 2 — https://v2.tauri.app/start/
- uv — https://docs.astral.sh/uv/
- AI SDK 6 — https://vercel.com/blog/ai-sdk-6
