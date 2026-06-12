# Clay Project — Snapshot для Архитектора

> **Временный документ.** Создан 2026-06-01 агентом M3 Free на основе изучения `docs/`, `backend/`, `frontend/`, `git log`.
>
> **Назначение:** дать архитектору точное понимание проекта, включая кодовую базу того, что уже написано. Без чтения всех 1599 Python-файлов и 843 TS/TSX-файлов.
>
> **Когда удалить:** после того как архитектор прочитает и подтвердит, что контекст восстановлен. Этот файл — bridge, не постоянная memory.
>
> **Источник:** `.context/handoffs/to-architect-snapshot-2026-06-01.md`. Документы для углубления — `docs/development/handoff-2026-05-02.md`, `docs/planning/master-planning-review-v1.md`.

---

## 0. TL;DR

**Clay** — локальная web-first панель для **ручной** торговли на Binance Spot. AI-assisted (hybrid alpha), **не auto-trading**, не futures, не multi-user, не cloud-first.

**Где проект (2026-05-31):** Wave 1 (E1-E12) реализован полностью. Alpha Operator Hardening завершён. `GET /alpha/overview` работает через HTTP. Full 7-шаговый alpha path проходит end-to-end. 107 backend + 15 frontend тестов зелёные. CKB 132 backend файла (9 122 LOC) + 105 frontend файлов (13 534 строк).

**Главные открытия при изучении кода (важно для архитектора):**

1. **CLAUDE.md.bak устарел** — упоминает Zustand, react-router, но в коде их **нет**. State = custom hooks поверх `useState`+`useEffect`+`useEffectEvent`. Routing = hash-router в `App.tsx`.
2. **`useEffectEvent`** из React 19 experimental (Canary) используется в `use-alpha-readiness.ts`, `use-control-plane.ts`, `use-*-page` хуках.
3. **In-memory state, теряется при рестарте**: AI assignments, active session, workspace focus, validation `_strategy_mode`, reliability `last_rechecked_at`. Alpha читает это — при рестарте backend увидит `lifecycle=idle` и gate `session-lifecycle` warn.
4. **`scheduler/service.py` — заглушка** (только `WorkWindow` dataclass, никакой логики). `health_monitor.refresh()` определён, но **нигде не вызывается** → `ServiceStatus.STALE` никогда не присваивается.
5. **Validation metrics синтетические**: `ValidationLabService.run_validation` возвращает hard-coded числа (win_rate, net_pnl, max_dd, decision_quality) на основе наличия top signal. Не настоящий бэктест, заглушка для UI.
6. **53 API endpoints, 30 router-файлов, 7 schemas, 7 миграций** (последняя `0007_incident_lifecycle`). Alpha endpoint добавлен без новой миграции — `AlphaReadinessService` read-only поверх существующих данных.
7. **Alpha — read-only композиция** над 6 существующими сервисами: `workspace`, `session_control`, `demo_trading`, `session_review`, `validation_lab`, `reliability`. Один endpoint `GET /alpha/overview`, 8 фиксированных operator steps, 7 gates с `blocks_alpha` флагом.

**Следующий шаг (по handoff):** 3-5 engineering waves до alpha core, **не полировать визуал**. Real-data rehearsal boundaries (что нужно, чтобы alpha path был полезен на реальных/semi-real данных).

---

## 1. Что такое Clay

**Миссия (из `docs/planning/blueprint-v1.md`):** локальная web-first торгово-аналитическая панель, на которой человек сам торгует на Binance Spot. AI помогает с synthesis, объяснениями, conflict detection. **Не автотрейдинг.**

**Базовые принципы v1:**
- **Self-contained** — локальная БД, локальный backend, локальный запуск
- **Manual execution** — человек сам нажимает кнопки на бирже
- **No auto** — никакого auto-trading, auto-routing, silent switching
- **Survives outages** через degraded mode (5 классов incidents A-E, runbook-001)
- **Knowledge base не в hot path** (E10 — advisory only)
- **Explainability & observability first** — audit trail обязателен
- **Hybrid alpha** — cloud LLM providers + local compact forecast fallback
- **5 фаз roadmap:** Core Foundation → Trading Core UX → AI Layer → Session Intelligence → Research/Expansion

**Что Clay НЕ является:**
- Не автотрейдер, не bot, не futures-клиент
- Не multi-user, не SaaS, не облачный сервис
- Не заменяет биржевой интерфейс — только подсказывает

**5 главных экранов (из blueprint):** Trading Screen, Control Center, AI Console, Session Review, Knowledge/Research. В коде развёрнуты в 12 страниц (плюс alpha-operator + settings).

---

## 2. Технологический стек (фактический)

### 2.1 Backend (Python)

| Слой | Технология | Версия |
|---|---|---|
| Runtime | Python | **3.14** (`requires-python = ">=3.14,<3.15"`) |
| Web | FastAPI | 0.115.x |
| ASGI | uvicorn[standard] | 0.30.x |
| ORM | SQLAlchemy | 2.0.x (async-ready, но sync session в коде) |
| DB driver | psycopg[binary] | 3.2.x (PostgreSQL) |
| Migrations | Alembic | 1.14.x |
| Models | Pydantic | 2.8.x |
| Settings | pydantic-settings | 2.4.x |
| HTTP client | httpx | 0.27.x (dev only, но **используется в runtime** в `binance_client.py`) |
| Test | pytest | 8.3.x + pytest-asyncio 0.24.x |
| Build | hatchling | latest |

**Package manager:** `uv` (lockfile = `uv.lock`, 82 KB).

**Нет в runtime deps:** ai-sdk, openai, anthropic, langchain, langgraph, chromadb, redis. Все модели — **абстрактные**, in-memory в `AIControlService`. Это сознательно: Clay хранит только **управление assignment'ами**, реальные вызовы провайдеров будут через `Clay Provider Abstraction Layer` (пока не реализован).

### 2.2 Frontend (TypeScript)

| Слой | Технология | Версия |
|---|---|---|
| Framework | React | **19.2.0** |
| Language | TypeScript | 5.9.3 |
| Build | Vite | 7.1.10 |
| Styling | Tailwind CSS | 4.2.4 (через `@tailwindcss/vite` плагин, **inline в `index.css`**) |
| Animations | motion | 12.38.0 (бывший framer-motion) |
| Icons | lucide-react | 1.8.0 |
| Test | Vitest | 3.2.4 + @testing-library/react 16.3 + jsdom 26.1 |

**Package manager:** pnpm (lockfile = `pnpm-lock.yaml`, 76 KB).

### 2.3 Расхождения с `CLAUDE.md.bak` (intelligence v1)

`CLAUDE.md.bak` (из бэкапа 2026-06-01) говорит:

> Frontend: React 19, TS 5.x, Vite, Tailwind 4, **Zustand**.

**Реальность в коде:** Zustand **отсутствует** (`node_modules/zustand` нет, `import 'zustand'` — 0 совпадений). State management — custom hooks поверх `useState`+`useEffect`+`useEffectEvent`+`startTransition`. Каждая page имеет свой `use-*.ts` хук.

**Возможные причины дрейфа:**
- Решили упростить до delivery v1 (минимум зависимостей)
- Незаконченный рефактор
- Внешнее ограничение (bundle size?)

**Архитектору стоит решить:** это **навсегда** (тогда обновить `CLAUDE.md.bak` → удалить упоминание Zustand) или **откат запланирован** (тогда ничего не менять).

Также `CLAUDE.md.bak` упоминает: `npm run dev` для frontend. **Реальность:** пакетный менеджер pnpm, но `dev` скрипт в `package.json` = `vite` (подходит и для pnpm). Поправить формулировку в intelligence v1.

### 2.4 Базы данных

- **PostgreSQL 16+** + **TimescaleDB 2.x** (production)
- **SQLite** с `SQLITE_SCHEMA_TRANSLATE_MAP` (тесты + dev fallback)
- Alembic миграции запускаются через `uv run alembic upgrade head`
- `pgvector` **отложен до E10** (по `tech-stack-v1.md`)

### 2.5 Transport

- **HTTP/JSON** для commands и CRUD
- **SSE** (Server-Sent Events) для server→client live updates: status, signals, preflight, AI streaming, per-domain refresh triggers
- **WebSocket запрещён policy** (ADR-003, AI Rule #3, `no_websockets` в tech-stack-v1)
- 10 SSE-stream endpoints (по одному на каждый большой домен + 1 общий `/events/stream`)
- SSE queues `maxsize=32` — при переполнении подписчик дисконнектится автоматически

---

## 3. Структура проекта

```
/home/emma/Projects/clay/
├── README.md                       # 316 строк, обзор + E1-E12 progress
├── Makefile                        # backend-{install,test,run}, frontend-{install,test,build,run}
├── .mise.toml                      # 52 байта, tool versions
├── .env.example                    # CLAY_API_HOST/PORT, CLAY_DATABASE_URL, VITE_CLAY_API_BASE_URL
├── .gitignore
├── .codex-screenshots/             # UI screenshots от Codex
├── docs/                           # 82 .md файла
├── backend/                        # 1599 .py файлов
│   ├── pyproject.toml              # 33 строки
│   ├── alembic.ini
│   ├── uv.lock                     # 82 KB
│   ├── alembic/                    # 7 ревизий
│   ├── src/clay/                   # 132 .py, 9 122 LOC
│   │   ├── api/                    # main.py + 30 routes
│   │   ├── alpha/                  # ← Alpha Readiness (NEW)
│   │   ├── ai_control/             # E5 (in-memory registry)
│   │   ├── audit/                  # JSONL writer
│   │   ├── bootstrap.py            # Singleton-граф на импорте
│   │   ├── config/                 # XDG loader + scopes
│   │   ├── control_center/         # E4
│   │   ├── db/                     # 7 schemas + 7 repositories
│   │   ├── demo_trading/           # E8
│   │   ├── events/                 # In-memory bus + SSE
│   │   ├── freshness/              # Evaluator (5m/15m/1h + 8h/4h)
│   │   ├── health/                 # Monitor (НЕ вызывается!)
│   │   ├── ingestion/              # E2
│   │   ├── knowledge/              # E10 (advisory)
│   │   ├── preflight/              # E1
│   │   ├── reliability/            # E12 (агрегатор)
│   │   ├── retention/              # retention windows
│   │   ├── runtime/                # E1 (states, transitions)
│   │   ├── scheduler/              # ⚠ ЗАГЛУШКА
│   │   ├── services/               # E1 (registry, supervisor)
│   │   ├── session_control/        # E7
│   │   ├── session_review/         # E9
│   │   ├── settings/               # IngestionSettings
│   │   ├── shortlist/              # Volume/volatility/liquidity rolling
│   │   ├── signal_engine/          # E6 (lifecycle, ranking)
│   │   ├── validation_lab/         # E11 (synthetic metrics ⚠)
│   │   └── workspace/              # E3
│   ├── tests/                      # 48 test_*.py, 4 866 LOC
│   │   ├── alpha/                  # 1 файл, 6 тестов, 534 строки
│   │   ├── api/                    # 24 файла (per router)
│   │   └── ... (по 1-2 файла на домен)
│   └── .venv/                      # Python venv
└── frontend/                       # 843 TS/TSX
    ├── package.json                # 30 строк
    ├── pnpm-lock.yaml              # 76 KB
    ├── vite.config.ts              # 12 строк
    ├── tsconfig.json               # 20 строк, strict, без paths
    ├── tsconfig.tsbuildinfo        # 4.8 KB
    ├── index.html                  # 12 строк
    ├── node_modules/
    ├── dist/                       # 728 KB (31 мая build)
    │   ├── index.html
    │   ├── assets/index-*.css      # 244 KB (Tailwind 4 inline)
    │   └── assets/index-*.js       # 480 KB (без code-splitting)
    └── src/                        # 105 TS/TSX, 13 534 строк
        ├── main.tsx                # 17 строк
        ├── App.tsx                 # 243 строки (hash-router)
        ├── App.test.tsx            # 1573 строки, 13 тестов
        ├── index.css               # 3566 строк (Tailwind 4)
        ├── api/                    # 10 clients, ~480 строк
        │   ├── client.ts
        │   ├── alpha-client.ts     # ← NEW
        │   └── ... (8 ещё)
        ├── components/             # 3 файла (sidebar, topbar, badge)
        ├── features/               # 15 директорий (12 экранов + alpha + settings + legacy)
        │   ├── alpha/              # ← NEW
        │   ├── overview/
        │   ├── workspace/
        │   ├── control-center/
        │   ├── ai-control/
        │   ├── session-control/
        │   ├── demo-trading/
        │   ├── session-review/
        │   ├── knowledge/
        │   ├── validation-lab/
        │   ├── reliability/
        │   ├── settings/
        │   ├── alerts/             # legacy
        │   ├── runtime/            # legacy
        │   └── services/           # legacy
        ├── hooks/                  # 2 файла
        ├── types/                  # 11 .ts, 940 строк
        └── test/setup.ts
```

**Метрики кода:**
- Backend source: **9 122 LOC** (132 .py)
- Backend tests: **4 866 LOC** (48 .py)
- Frontend: **13 534 строк** (105 .ts/.tsx), из них:
  - `index.css` = 3 566 строк (27%, Tailwind 4 inline-токены)
  - `App.test.tsx` = 1 573 строки (13 тестов, 12% от всего frontend)
  - Pages = ~5 950 строк (44%)

---

## 4. Документация (`docs/`)

### 4.1 Структура

```
docs/
├── README.md                                  # локальный hub (2.1 KB)
├── planning/                                  # SOURCE OF TRUTH для implementation
│   ├── README.md
│   ├── blueprint-v1.md                        # 24.2 KB, 625 строк — ГЛАВНЫЙ
│   ├── tech-stack-v1.md                       # 12.4 KB, 233 строки
│   ├── execution-backlog-v1.md                # 25.9 KB, 667 строк
│   ├── master-planning-review-v1.md           # 15.1 KB, 319 строк — ФИНАЛЬНЫЙ REVIEW
│   ├── approved-stack-v1.md                   # 8.0 KB, 242 строки — НОВЕЕ tech-stack
│   └── skills-strategy-v1.md                  # 9.7 KB, 291 строка
├── mission-control/                           # ПОЛНЫЙ snapshot из Obsidian
│   ├── index.md                               # ⚠ ЧАСТИЧНО УСТАРЕЛ
│   ├── handoff-2026-03-30.md                  # базовый handoff
│   ├── next-chat-prompt.md                    # ⚠ АРХИВНЫЙ
│   ├── project-overview-report-v1.md          # quick orientation
│   ├── session-summary-2026-03-30.md          # pause-point
│   ├── session-summary-2026-03-31.md          # v6 UI baseline
│   ├── session-summary-2026-04-01.md          # v15 UI baseline
│   ├── blueprint-v1.md                        # ДУБЛЬ planning/
│   ├── tech-stack-v1.md                       # ДУБЛЬ
│   ├── execution-backlog-v1.md                # ДУБЛЬ
│   ├── master-planning-review-v1.md           # ДУБЛЬ
│   ├── adrs/                                  # 5 принятых ADR-001..005
│   ├── build_specs/                           # 12 per-epic (16-28 KB)
│   ├── implementation_plans/                  # 12 per-epic (25-38 KB) + README
│   ├── runbooks/                              # 2 runbook'а
│   └── .superpowers/brainstorm/               # пустые подпапки (следы brainstorm)
├── development/
│   ├── README.md                              # указатель на handoff-2026-05-02
│   └── handoff-2026-05-02.md                  # ← ГЛАВНЫЙ RUNTIME HANDOFF (23 KB)
└── ui-references/
    ├── README.md
    └── clay-mission-control-ui-v17/           # Gemini v17 export, visual reference
```

### 4.2 Что устарело

| Документ | Почему | Что использовать вместо |
|---|---|---|
| `mission-control/index.md` | Частично устарел (признаёт сам файл в `project-overview-report-v1.md:240`) | `master-planning-review-v1.md`, `implementation_plans/README.md` |
| `mission-control/next-chat-prompt.md` | Указывает на старый handoff | `handoff-2026-05-02.md` |
| `mission-control/tech-stack-v1.md` | Старее чем `approved-stack-v1.md` (Python 3.12+ vs 3.14, нет 5 AI rules) | `planning/approved-stack-v1.md` |
| UI-references v1-v16 | Deprecated per `session-summary-2026-04-01.md` | v17 (текущий reference) |
| `CLAUDE.md.bak` (бэкап 2026-06-01) | Не соответствует коду (Zustand, react-router не используются) | Этот snapshot |

### 4.3 Документы, на которые архитектор ссылается

- `docs/planning/blueprint-v1.md` — **миссия, ограничения, 5 экранов, 5 слоёв, 4 AI-роли, 5 фаз**
- `docs/planning/execution-backlog-v1.md` — **12 эпиков E0-E12 с задачами и dependencies**
- `docs/planning/master-planning-review-v1.md` — **4 implementation waves, approval conditions, риски**
- `docs/planning/approved-stack-v1.md` — **финальный стек (Python 3.14, 5 AI rules)**
- `docs/development/handoff-2026-05-02.md` — **runtime handoff с актуализациями до 2026-05-31**
- `docs/mission-control/runbooks/runbook-002-alpha-operator-path.md` — **Alpha operator runbook (E7-E12)**

### 4.4 5 принятых ADR (все `accepted`)

| ADR | Суть |
|---|---|
| **ADR-001** Runtime State Model | 6 canonical states; control plane ≠ managed services; всё через runtime-manager |
| **ADR-002** Config Validation & Rollback | 7 scoped config; revision model (active/candidate/last-known-good); XDG layout; fail sanely |
| **ADR-003** Transport Policy | HTTP/JSON + SSE; **WebSocket НЕ baseline** (только при superseding ADR) |
| **ADR-004** Storage Baseline | 1 локальный PG + TimescaleDB; pgvector только с E10; нет отдельных vector DB / TSDB / OLAP |
| **ADR-005** Model Provider Abstraction | Provider abstraction layer обязателен; provider ≠ model version; forecast отдельно; operator-controlled assignment |

**Открытых ADR нет.**

---

## 5. Эпики E1-E12 — пройденные стадии

### 5.1 Сводная таблица

| Эпик | Название | Статус | Backend модуль | Frontend экран | Test count |
|---|---|---|---|---|---|
| **E0** | Product framing & SoT | ✅ done (planning) | — | — | — |
| **E1** | Runtime foundation & local control plane | ✅ done | `runtime/`, `config/`, `services/`, `preflight/`, `health/` | `overview/` | ~7 |
| **E2** | Data ingestion & local historical store | ✅ done | `ingestion/`, `freshness/`, `shortlist/` | (нет отдельного — фрагменты в `alerts/`, `runtime/`, `services/`) | ~12 |
| **E3** | Trading screen & live signal workspace | ✅ done | `workspace/` | `features/workspace/trading-workspace-page.tsx` (558 строк) | 2 |
| **E4** | Control center & runtime operations | ✅ done | `control_center/` | `features/control-center/control-center-page.tsx` (832 строки) | ~5 |
| **E5** | AI roles, orchestration & model assignment | ✅ done (in-memory) | `ai_control/` (492 строки) | `features/ai-control/ai-control-page.tsx` (789 строк) | ~5 |
| **E6** | Signal lifecycle, ranking & risk-control | ✅ done | `signal_engine/service.py` (505 строк) | внутри Trading Workspace | ~8 |
| **E7** | Session lifecycle, briefing, pause | ✅ done (in-memory) | `session_control/` (450 строк) | `features/session-control/session-control-page.tsx` (541 строка) | ~5 |
| **E8** | Demo trading integration & result tracking | ✅ done | `demo_trading/` (289 строк) | `features/demo-trading/demo-validation-page.tsx` (426 строк) | ~4 |
| **E9** | Audit trail, feedback & session review | ✅ done | `session_review/` (384 строки) | `features/session-review/session-review-page.tsx` (447 строк) | ~3 |
| **E10** | Knowledge base & research layer | ✅ done (advisory) | `knowledge/` (253 строки) | `features/knowledge/knowledge-page.tsx` (408 строк) | ~3 |
| **E11** | Backtesting, replay & model/strategy activation | ✅ done (synthetic metrics) | `validation_lab/` (352 строки) | `features/validation-lab/validation-lab-page.tsx` (474 строки) | ~3 |
| **E12** | Reliability, degraded mode & release readiness | ✅ done | `reliability/` (376 строк) | `features/reliability/reliability-page.tsx` (495 строк) | ~3 |
| **α** | Alpha Operator (NEW, поверх E1-E12) | ✅ done (hardening) | `alpha/` (358 строк) | `features/alpha/alpha-operator-page.tsx` (299 строк) | 6 backend + 4 frontend |

### 5.2 Ключевые сущности по эпикам

**E1 — Runtime:**
- 6 states: `background_monitoring`, `pre_session`, `active_session`, `paused`, `review`, `degraded`
- `ALLOWED_TRANSITIONS` dict (e.g. `degraded → pre_session` только через recovery)
- `RuntimeManager.transition_to` проверяет CRITICAL-сервисы
- 2 config scopes: `runtime.toml` (work_window), `risk.toml` (confidence thresholds)
- 3 services зарегистрированы в bootstrap: `control-api` (CRITICAL), `session-scheduler` (IMPORTANT), `pair-scanner` (OPTIONAL)

**E2 — Ingestion:**
- `IngestionCycleService.run_once(session)` — async, market → context
- `BinanceSpotClient.fetch_klines` (httpx → api.binance.com/api/v3/klines)
- 2 demo context connectors (news, sentiment)
- Freshness evaluator: market 5m/15m/1h, news 8h, sentiment 4h
- 3 schemas: `market`, `context`, `ops` (3+2+3 = 8 таблиц)

**E3 — Workspace:**
- `WorkspaceService` строит `WorkspaceSnapshot` (463 строки)
- Top-5 pairs из signal engine + market bars + news/sentiment
- Posture: `normal`/`monitoring_only`/`defensive`/`restricted_by_degraded`
- Focus logic: `_focus_symbol` → `_selected_signal_id` → first active → first

**E4 — Control Center:**
- `ControlCenterService.build_snapshot` (328 строк) — собирает runtime, services, ingest, incidents, audit, configs
- `summary.overall_status` = healthy/degraded
- `actionability` = normal/limited/blocked

**E5 — AI Control:**
- 4 роли зашиты: `chief-agent` (synthesis+explanation owner), `market-scanner`, `news-sentiment-agent`, `forecast-model`
- 5 моделей: `openai-gpt-5.4`, `openai-gpt-5.4-mini`, `anthropic-claude-sonnet-4.5`, `gemini-2.5-flash`, `forecast-lite-v1` (Local fallback)
- Review/Apply flow с audit + event publication
- **In-memory only** для v1 (`del session` явно в коде)

**E6 — Signal Engine (главный бизнес-файл):**
- `SignalEngineService.build_snapshot` (505 строк)
- 5 типов risk triggers: `stale-market-{sym}` (critical), `thin-context-{sym}` (warn), `ai-conflict` (warn), `runtime-degraded` (critical), `expired-window-{sym}` (warn)
- 4 response actions: `switch_to_defensive` > `block_signal` > `lower_confidence` > `warning_only`
- Confidence penalty 0.8 cap, ranking penalty -0.08/-0.2/-0.15
- Signal states: `expired`/`invalidated`/`weakening`/`active` (≥0.72) → 4 состояния
- Strategy modes: `defensive`/`momentum` (≥0.78)/`trend_following`

**E7 — Session Control:**
- 5 states: `idle`/`pre_session`/`active_session`/`paused`/`review`
- 6 preflight checks: data-freshness, api-availability, active-model-loaded, shortlist-confirmed, strategy-confirmed, risk-limits-active
- Briefing: top-3 shortlist + market_context + sentiment_summary + ai_summary
- Pair replacement: review card если `ranking_score > current + 0.08` и state ∈ {active, weakening}
- **In-memory `_active_session`** — упал процесс, потерял сессию

**E8 — Demo Trading:**
- 5 outcome statuses: `matched`/`missed`/`late_matched`/`mismatched`/`unresolved`
- 4 readiness gates: `session_count` (≥5 → pass), `result_resolution`, `signal_alignment`, `pnl_discipline`
- Статусы: `collecting`/`at_risk`/`ready_for_review`

**E9 — Session Review:**
- Filters: pair/strategy/model_version/confidence_band
- Feedback: `useful` (+1.0)/`noise` (-1.0)/`needs_follow_up` (0.0)
- 4 AI review cards: `mismatch-discipline`, `follow-up-needed`, `stable-review`, `clean-audit-window`

**E10 — Knowledge:**
- Категории: `note`/`strategy_rule`/`checklist`/`observation`
- Приоритеты: `low`/`medium`/`high`
- Chunking: paragraph / semantic_window (по 2 предложения)
- `hot_path_dependency: False` — knowledge вне realtime signal path
- Retrieval **advisory only**, не блокирует signals

**E11 — Validation Lab:**
- 3 run_types: `strategy_replay` (3.4% pnl, 1.8% dd), `model_comparison` (2.1%/2.0%), `signal_quality` (1.7%/1.5%)
- 2 target_types: `strategy_mode`/`model_assignment`
- Posture: `blocked` (pnl<0 или dd≥3.5 или quality<0.55), `staged`, `ready`
- **Синтетические метрики** (не настоящий бэктест)

**E12 — Reliability:**
- `ReliabilityService` агрегирует control_center + ai_control + demo + review + validation
- 7 degraded triggers: runtime-degraded, preflight-blocked, market-data-blocked, context-degraded, ai-fallback-gap, fallback-not-complete, critical-incidents
- 7 readiness checks
- Release status: `blocked`/`needs_attention`/`ready_for_demo`

---

## 6. Alpha Operator (главный фокус)

### 6.1 Что это

**AlphaReadinessService** — read-only композиционный агрегатор, который собирает snapshot из 6 существующих сервисов и отвечает на один вопрос: "готов ли Clay пройти manual alpha operator path прямо сейчас?"

**Единственный endpoint:** `GET /alpha/overview`. Prefix `/alpha`, tag `alpha`.

### 6.2 Файлы

**Backend:**
- `src/clay/alpha/service.py` (358 строк) — `AlphaReadinessService`
- `src/clay/alpha/models.py` (55 строк) — 5 Pydantic моделей
- `src/clay/api/routes/alpha.py` (18 строк) — единственный route
- `src/clay/api/dependencies.py` — `get_alpha_readiness_service()` геттер
- `src/clay/bootstrap.py` — добавляет `alpha_readiness_service` последним
- `tests/alpha/test_alpha_readiness_service.py` (534 строки, 6 тестов)

**Frontend:**
- `src/features/alpha/alpha-operator-page.tsx` (299 строк) — UI
- `src/features/alpha/use-alpha-operator-console.ts` (205 строк) — контроллер
- `src/features/alpha/use-alpha-readiness.ts` (59 строк) — лёгкий snapshot loader (с `useEffectEvent`)
- `src/types/alpha.ts` (51 строка) — TS-контракт
- `src/api/alpha-client.ts` (17 строк) — единственный endpoint
- Тесты в `src/App.test.tsx` (4 теста на alpha: happy path + 3 recoverable errors)

### 6.3 Контракт `GET /alpha/overview`

```typescript
{
  summary: {
    readiness_status: 'blocked' | 'needs_attention' | 'operator_path_ready',
    operator_path_ready: boolean,
    blocking_gate_count: number,
    warning_gate_count: number,
    next_action: { step_id, label, target_screen, action_label } | null
  },
  gates: [{
    gate_id: string,           // 'preflight-ready' | 'focused-signal' | 'session-lifecycle' | ...
    label: string,
    status: 'pass' | 'warn' | 'fail',
    blocks_alpha: boolean,
    detail: string
  }],  // 7 gates
  operator_steps: [{
    step_id: string,           // 8 фиксированных шагов
    label: string,
    status: 'pass' | 'pending',
    detail: string,
    target_screen: string,     // 'session-control' | 'demo-validation' | ...
    action_label: string,
    is_next: boolean           // ровно 1 true (или 0 если всё pass)
  }],
  evidence: {
    runtime_state: string,
    preflight_status: string,
    workspace_posture: string,
    focus_symbol: string | null,
    focused_signal_state: string | null,
    session_lifecycle_state: string,
    demo_readiness_status: string,
    demo_record_count: number,
    review_status: string,
    validation_replay_ready: boolean,
    validation_run_count: number,
    release_readiness_status: string
  }
}
```

### 6.4 7 Gates (с `blocks_alpha`)

| Gate | Условие fail/warn | blocks_alpha |
|---|---|---|
| `preflight-ready` | `preflight.status != "pass"` | **YES** (critical) |
| `focused-signal` | нет active_signal_id или state ∉ {active, weakening} | NO (warn) |
| `session-lifecycle` | lifecycle ∈ {idle, pre_session} | NO (warn) |
| `demo-evidence` | `readiness.status != "ready_for_review"` | NO (warn) |
| `review-loop` | `resolved_demo_records == 0` или `review_status == "collecting"` | NO (warn) |
| `validation-replay` | `not replay_ready` | NO (warn) |
| `reliability-posture` | `release_readiness_status == "blocked"` (fail) или нет `last_rechecked_at` (warn) | **YES** (если fail) |

### 6.5 8 Operator Steps (фиксированный порядок)

1. `check_preflight` → screen: session-control
2. `focus_signal` → workspace
3. `start_or_resume_session` → session-control **(runnable)**
4. `log_demo_decision` → demo-validation **(runnable)**
5. `resolve_demo_result` → demo-validation **(runnable)**
6. `review_feedback` → session-review **(runnable)**
7. `run_validation_replay` → validation-lab **(runnable)**
8. `recheck_reliability` → reliability **(runnable)**

**Логика `_mark_next_operator_step`:** первый шаг с `status != "pass"` становится `is_next=True`. Контроллер `useAlphaOperatorConsole` имеет белый список `runnableStepIds` (6 из 8) и для каждого знает API-вызов.

### 6.6 6 Runnable Steps (что делает контроллер)

| Step | API call |
|---|---|
| `start_or_resume_session` | `startSession()` |
| `log_demo_decision` | `logCurrentDemoTrade('entered')` |
| `resolve_demo_result` | `getDemoTradingOverview()` → найти awaiting/unresolved → `ingestDemoResult(..., 1.4, {entryPrice: 100, exitPrice: 101.4})` |
| `review_feedback` | `getSessionReviewOverview()` → найти resolved record → `captureSessionFeedback(..., 'useful', '...')` |
| `run_validation_replay` | `runValidation('strategy_replay', '...')` |
| `recheck_reliability` | `recheckReliability()` |

После успешного действия — `getAlphaOverview()` для обновления snapshot.

### 6.7 Тестовое покрытие alpha

**Backend (`tests/alpha/test_alpha_readiness_service.py`, 6 тестов):**
1. `test_alpha_readiness_blocks_without_fresh_inputs` — пустая БД → blocked, gate `preflight-ready` fail
2. `test_alpha_readiness_opens_operator_path_when_session_can_run` — после seed + start_session → next_step = `log_demo_decision`
3. `test_alpha_readiness_surfaces_evidence_gates` — seed + 5 demo records + validation run → gates pass
4. `test_alpha_happy_path_advances_runbook_across_operator_routes` — полный E2E через прямые вызовы сервисов
5. `test_alpha_operator_path_runs_through_http_api_contracts` — полный E2E через HTTP (`httpx.ASGITransport`, `dependency_overrides`)
6. `test_alpha_overview_route_returns_snapshot_payload` — smoke для роута

**Frontend (`App.test.tsx`, 4 теста на alpha):**
1. `runs the full alpha operator console path` — 6 шагов через Console → "alpha operator path is ready"
2. `keeps alpha operator state visible when a demo result is missing` — recoverable error, кнопка не исчезает
3. `keeps alpha operator state visible when review feedback has no target record` — recoverable error
4. `keeps alpha operator state visible when validation replay fails` — recoverable error

**Это лучшее покрытие в проекте** — happy path + 3 recoverable ошибки.

### 6.8 Recoverable Errors (по runbook-002 §6)

| Сценарий | UI behavior |
|---|---|
| `POST /demo-trading/results/ingest` без awaiting result | Error: "No awaiting demo result is available for alpha resolution." — кнопка остаётся |
| `POST /session-review/feedback` без reviewable record | Error: "No reviewable demo record is available for alpha feedback." — кнопка остаётся |
| `POST /validation-lab/runs` возвращает API error | Показать request error — кнопка остаётся |

**Запрещено (runbook-002 §8):**
- ❌ Добавлять отдельный backend orchestrator для прохождения alpha path
- ❌ Продвигать runbook в UI без успешного ответа domain API
- ❌ Скрывать reliability/demo warnings после финального path complete
- ❌ Считать `operator_path_ready` разрешением на auto-execution
- ❌ Делать destructive runtime action без отдельного operator confirmation

### 6.9 Зависимости alpha в bootstrap

```python
alpha_readiness_service = AlphaReadinessService(
    workspace_service,           # E3
    session_control_service,     # E7
    demo_trading_service,        # E8
    session_review_service,      # E9
    validation_lab_service,      # E11
    reliability_service,         # E12
)
```

**Важно:** в `tests/alpha/test_alpha_readiness_service.py` есть `build_alpha_bundle(tmp_path)` — копия `bootstrap.py` со всеми 6 сервисами. При добавлении нового сервиса в bootstrap нужно **синхронить тестовую bundle**.

---

## 7. Архитектура backend

### 7.1 Слои

```
bootstrap (на импорте, singleton)
    ↓
config_loader, audit_writer, event_bus, registry, supervisor
    ↓
runtime_manager, preflight_service, ingestion_*
    ↓
ai_control ←→ signal_engine → workspace → session_control → demo_trading
                                              ↓
                                      session_review
                                              ↓
                                      validation_lab
                                              ↓
                                      reliability (агрегатор всего)
                                              ↓
                                      alpha (read-only композиция)
```

**Bootstrap на импорте** — `bootstrap.py` исполняется при первом `import clay.api.main`. Удобно для dev/тестов, но **плохо для prod** (нет graceful init/shutdown, нет reload-safety, нет health на init).

### 7.2 `src/clay/api/main.py` (87 строк)

- `create_app()` собирает FastAPI, CORS, 30 router'ов
- CORS allowlist: 4 dev-origins (Vite 5173, Vite preview 4173)
- **Без `lifespan`**, без auth, без rate-limit, без request-id middleware
- **Без global exception handlers** — `ValueError`/`RuntimeError` ловятся per-route, оборачиваются в `HTTPException(400/409)`
- Сервис-логика синхронная (даже `IngestionCycleService.run_once` async, обёрнут в sync route)

### 7.3 Event bus

`src/clay/events/bus.py` — in-memory `asyncio.Queue`-fan-out для SSE:
- 32-slot queue
- auto-evict stale
- 10 SSE-streams подписываются на разные event-типы
- **Нет персистентности событий** — при рестарте всё теряется

**Известные event-типы:** `demo.updated`, `session.updated`, `ai.updated`, `validation.updated`, `reliability.updated`, `ingestion.updated`, `runtime.updated`, `config.updated`, `service.updated`, `workspace.updated`, `knowledge.updated`, `review.updated`, `control.ready`, `control-center.ready/refresh`, `ai-control.ready/refresh`, `session.ready/refresh`, `demo.ready/refresh`, `validation-lab.ready/refresh`, `session-review.ready/refresh`, `knowledge.ready/refresh`, `reliability.ready/refresh`, `workspace.ready/refresh`.

### 7.4 Alpha как композиция

`AlphaReadinessService.build_snapshot(session)`:
1. `_build_gates` — для каждого из 7 gate'ов дёргает соответствующий сервис и проверяет условие
2. `_build_operator_steps` — 8 фиксированных шагов, копирует `target_screen` и `action_label`
3. `_mark_next_operator_step` — первый non-pass становится `is_next=True`
4. `_build_summary` — вычисляет `readiness_status` (blocked/operator_path_ready/needs_attention)
5. `_build_evidence` — собирает 12 полей из 6 сервисов

**Добавление нового gate'а:** добавить поле в `AlphaReadinessGateSnapshot` + условие в `_build_gates`.
**Добавление нового operator-step:** вписать в `_build_operator_steps` (порядок важен — `_mark_next_operator_step` берёт первый non-pass).

### 7.5 Persistence (Alpha)

Alpha **не имеет таблиц** и не требует миграции. `AlphaReadinessService` читает существующие demo/review/validation/reliability/replay данные и собирает snapshot.

---

## 8. Архитектура frontend

### 8.1 Routing

**Самописный hash-router** в `App.tsx` (243 строки):
- `appScreens: AppScreen[]` — 12 экранов
- `resolveScreenFromHash()` читает `window.location.hash`
- `hashchange` listener → `setScreen(...)`
- `history.replaceState` при изменении

**12 экранов:** overview, alpha-operator, workspace, control-center, ai-control, session-control, demo-validation, session-review, knowledge, validation-lab, reliability, settings.

**react-router НЕ установлен.** При росте (deep-link на конкретный alpha-step, query params) — будет узким местом.

### 8.2 State management

**Zustand НЕ используется** (проверено: `node_modules/zustand` отсутствует, `import 'zustand'` — 0 совпадений, `create()` — 0 совпадений).

Вместо этого — **custom hooks поверх `useState` + `useEffect` + `startTransition` + React 19 `useEffectEvent`**. Каждая page имеет свой `use-*.ts`:
```ts
const [state, setState] = useState<State>({...})
const refresh = useEffectEvent(async () => { ... })
useEffect(() => { void refresh(); const sse = new EventSource(...); ...; return () => sse.close() }, [refresh])
```

**Локальный UI-state** (sidebar collapsed, theme, screen, clock) — прямо в `App.tsx`. Theme в `localStorage['clay-theme']`. Никакого глобального стора.

### 8.3 `useEffectEvent` (React 19 experimental)

Используется в `use-control-plane.ts`, `use-alpha-readiness.ts`, `use-*-page` хуках. Стабильно работает в React 19.2, но это **нестабильный API** (Canary). Стоит завернуть в feature-flag или подготовить план отката.

### 8.4 API клиент

**Самописный `fetch`-wrapper.** 10 файлов `*-client.ts` в `src/api/`:
- `client.ts` (базовый) + 9 domain-specific (включая `alpha-client.ts`)
- `getJson<T>(path)`, `postJson<T>(path, body)` — копипаст во всех 10 файлах
- Base URL: `import.meta.env.VITE_CLAY_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'`

**Рефактор opportunity:** вынести `getJson/postJson` в `api/fetcher.ts`. Сейчас копипаст.

### 8.5 SSE (10 streams)

Каждый stream идентичен паттерну:
```ts
const stream = new EventSource(getXxxStreamUrl())
stream.addEventListener('xxx.ready', handleRefresh)
stream.addEventListener('xxx.refresh', handleRefresh)
return () => stream.close()
```

**Список streams и событий:** см. §7.3.

**Для alpha SSE НЕТ** — `alpha-client.ts` возвращает только JSON, `useAlphaOperatorConsole` поллит через `refresh()` после mount и после каждого действия. Это **намеренный выбор** (alpha — дискретный конечный автомат, не live-feed).

**Нет SSE-reconnect** — если backend уронил стрим, UI замолчит до следующего ручного `refresh()`. Возможный future work.

### 8.6 Entry point

- `index.html` (12 строк) — `<div id="root">`
- `src/main.tsx` (17 строк) — `createRoot().render(<StrictMode><App/></StrictMode>)`
- `src/App.tsx` (243 строки) — shell + hash-router + theme/clock/SSE на control-center

**Анимации переходов:** `motion/react` (`AnimatePresence` + `motion.div`) с key=`screen`, fade 0.18s.

### 8.7 Build / dist

- `dist/index.html` (13 строк)
- `dist/assets/index-*.css` (244 KB, Tailwind 4 inline-токены)
- `dist/assets/index-*.js` (480 KB, **без code-splitting**)

**Build скрипт:** `tsc -b && vite build`. Тесты отдельно: `NODE_ENV=test vitest run`.

---

## 9. Тестирование

### 9.1 Backend (pytest)

- **48 test-файлов, 4 866 LOC**
- pytest 8.3 + pytest-asyncio 0.24
- `pythonpath = ["src"]`, `testpaths = ["tests"]`
- SQLite test storage через `SQLITE_SCHEMA_TRANSLATE_MAP` (схемы `market/context/ops/demo/review/knowledge/validation` → `main`)
- `conftest.py` (49 строк): fixtures `sqlite_settings`, `sqlite_engine`, `sqlite_session_factory`, `db_session`, `app_with_sqlite`

**Покрытие по доменам (примерное):**
- `alpha/` — 1 файл, 6 тестов, 534 строки
- `api/` — 24 файла (по одному на роутер)
- Домены: `ai_control/`, `config/`, `db/`, `demo_trading/`, `events/`, `freshness/`, `ingestion/`, `knowledge/`, `preflight/`, `reliability/`, `retention/`, `runtime/`, `services/`, `session_control/`, `session_review/`, `signal_engine/`, `validation_lab/`, `workspace/`

**`# pragma: no cover`** — 2 места (defensive runtime branches):
- `ingestion/service.py:136` (network exception)
- `ingestion/context/manager.py:61` (connector error)

**`TODO`/`FIXME`/`XXX`/`HACK`** в src/ — **0**.

**`NotImplementedError`** — 3, все в `ingestion/context/contracts.py` (ABC `ContextConnector`, ожидаемо).

### 9.2 Frontend (vitest)

- **15 тестовых файлов, ~1 741 строк**
- vitest 3.2 + @testing-library/react 16.3 + jsdom 26.1
- `setupFiles: './src/test/setup.ts'` → `@testing-library/jest-dom`

**`App.test.tsx` (13 тестов, 1 573 строки):**
1. `renders the runtime foundation shell with live overview data`
2. `switches between workspace and control center screens`
3. `runs the full alpha operator console path` ← **alpha happy path**
4. `keeps alpha operator state visible when a demo result is missing` ← **alpha recoverable**
5. `keeps alpha operator state visible when review feedback has no target record` ← **alpha recoverable**
6. `keeps alpha operator state visible when validation replay fails` ← **alpha recoverable**
7. `renders ai control and applies a reviewed assignment`
8. `runs the session lifecycle and pair replacement flow`
9. `tracks demo validation actions and result ingest`
10. `renders session review, filters by pair, and captures feedback`
11. `renders knowledge base, ingests a sample, and searches knowledge`
12. `renders validation lab, runs replay, and applies activation review`
13. `renders reliability center and rechecks release gates`

**`trading-workspace-page.test.tsx` (2 теста, 168 строк):**
1. `renders active signals and monitoring pool regions`
2. `switches the focused pair when a monitoring item is selected`

**Моки:** `vi.stubGlobal('fetch', ...)` + `class EventSourceMock` + `vi.stubGlobal('EventSource', ...)` + `Object.defineProperty(globalThis, 'EventSource', ...)` + `Object.defineProperty(window, 'EventSource', ...)` — тройная защита от нативного SSE.

**После теста:** `vi.unstubAllGlobals()` в `afterEach`.

**Coverage:** в `package.json` нет скрипта coverage. Vitest поддерживает c8/v8, но не настроено.

### 9.3 Что НЕ покрыто тестами

- Alembic upgrade (есть только `test_migration_contracts.py` — контракты моделей, не upgrade path)
- SSE reconnect logic (её просто нет)
- `useEffectEvent` откат при не-Canary React
- `scheduler/service.py` — потому что это заглушка
- `health/monitor.py` — `refresh()` нигде не вызывается

---

## 10. Известные долги и риски

### 10.1 In-memory state (теряется при рестарте backend)

| Сервис | Что теряется | Impact на alpha |
|---|---|---|
| `AIControlService` | `assignments`, `_pending_review`, `_last_reviewed_at` | gate `reliability-posture` warn |
| `SessionControlService` | `_active_session`, `_pending_replacement` | gate `session-lifecycle` warn, step `start_or_resume_session` остаётся next |
| `WorkspaceService` | `_focus_symbol`, `_focus_source`, `_selected_signal_id` | gate `focused-signal` warn |
| `ValidationLabService` | `_strategy_mode` (default "momentum") | `apply_activation` мутирует, но нет persistence |
| `ReliabilityService` | `_last_rechecked_at` | gate `reliability-posture` warn |

**Возможный future work для v2:** persist в БД (например `ops.session_state`, `ops.ai_assignments`, `ops.model_registry`).

### 10.2 Заглушки и missing pieces

- **`scheduler/service.py`** — только `WorkWindow(start, end)` dataclass, **никакой логики**. Когда понадобится cron для ingestion/health-monitor/reliability-recheck — это место.
- **`health/monitor.py`** — `refresh()` определён, но **нигде не вызывается** → `ServiceStatus.STALE` никогда не присваивается автоматически.
- **`validation_lab/run_validation`** — синтетические метрики (hard-coded 3.4%/1.8% и т.д.). Не настоящий бэктест.
- **`audit/writer.py`** — JSONL append-only, **нет ротации**. Может расти бесконечно (`~/.local/state/clay/audit.jsonl`).
- **`bootstrap.py`** — singleton на импорте. Нет graceful init/shutdown, нет reload-safety.

### 10.3 Irreversible migration

- **`0002_e2_hypertables.downgrade()` = `pass`** — TimescaleDB downgrade невозможен, нужно сначала `SELECT create_hypertable` обратно (manual).

### 10.4 Hardcoded config

- **CORS allowlist** в `api/main.py` — только 4 dev-origins (Vite 5173, preview 4173). Для prod-деплоя нужно править.
- **API base URL** в `api/alpha-client.ts` и др. — fallback `'http://127.0.0.1:8000'`. Если `.env` не подгрузился — фронт уйдёт на localhost (CORS-ловушка).
- **Timeframes** в тестах — BTC/ETH + 5m/15m (hardcoded в conftest).

### 10.5 Frontend долги

- **Нет code-splitting** — 480 KB единым bundle. Для `features/alpha` и второстепенных экранов нужен `lazy()` + `Suspense`.
- **Нет eslint/prettier/tsc-noEmit в CI** — только `vitest`. Build = `tsc -b && vite build`, тесты отдельно.
- **tsconfig без `paths`** — везде относительные `../../types/alpha`. При масштабировании громоздко.
- **API fetcher копипаст** в 10 `*-client.ts`. Очевидный refactor.
- **SSE-reconnect** — нигде нет `stream.onerror` → переподключения.
- **`use-alpha-readiness.ts` экспортируется, но не используется** (грепом не нашёл импорта). Возможно, заготовка.

### 10.6 Дрейф стека (CLAUDE.md.bak vs реальность)

| В CLAUDE.md.bak | В коде | Действие |
|---|---|---|
| Zustand | custom hooks | Решить: навсегда или откат? Обновить intelligence. |
| `npm run dev` (без уточнения PM) | pnpm + `vite` (подходит) | Уточнить формулировку. |
| React Router | hash-router | То же. |
| (нет упоминания motion) | motion 12.38.0 | Добавить в tech-stack. |
| (нет упоминания lucide-react) | lucide-react 1.8.0 | Добавить. |

### 10.7 Документы, требующие осторожности

- `mission-control/index.md` — частично устарел
- `mission-control/next-chat-prompt.md` — архивный
- `ui-references/clay-mission-control-ui-v17/` — Gemini export с mock data, **не копировать в live**

---

## 11. Место остановки (детально)

### 11.1 Из `docs/development/handoff-2026-05-02.md` (актуализации)

| Дата | Событие |
|---|---|
| **2026-05-02** | Базовое состояние: branch=main, tracking origin/main, backend 101 passed, frontend 11 passed |
| **2026-05-23** | Backend модуль `clay.alpha`, сервис `AlphaReadinessService`, endpoint `GET /alpha/overview` |
| **2026-05-25** | Frontend `AlphaReadinessSnapshot`, hook `useAlphaReadiness`, Overview показывает Alpha Readiness panel; `is_next` в operator step, кнопка `Continue` |
| **2026-05-25** | E2E: backend integration test полного alpha path; фикс runbook contract (`log_demo_decision` не проходит только по доступности) |
| **2026-05-31** | Alpha Operator Console: экран `alpha-operator`, sidebar, hash `#alpha-operator`; hook `useAlphaOperatorConsole()`; **production code не добавлял backend orchestration** |
| **2026-05-31** | Full Path: frontend integration test покрыл полный operator path |
| **2026-05-31** | Runtime Acceptance: backend HTTP/API-level acceptance test через `httpx.ASGITransport`; фикс contract: `readiness_status = operator_path_ready` когда нет blocking gates и не осталось next step |
| **2026-05-31** | Hardening: failure-mode coverage для Console (No Awaiting Demo Result, No Reviewable Demo Record, Validation Replay API Error) |
| **2026-05-31** | Runbook docs: `runbook-002-alpha-operator-path.md` создан |

### 11.2 Текущий checkpoint

**2026-05-31 — Alpha Operator Hardening Checkpoint** + **Alpha Acceptance Runbook Docs Checkpoint** (runbook-002 создан). Перед `Knowledge / Research` checkpoint.

**Git state (на 2026-06-01):**
- Branch: `main`, tracking `origin/main`
- Последние 20 коммитов — вокруг alpha operator (runbook, console, acceptance, readiness overview)
- Untracked: `CLAUDE.md.bak` (бэкап intelligence v1)
- Все тесты зелёные

### 11.3 Что точно работает

✅ 12 экранов (overview, alpha-operator, workspace, control-center, ai-control, session-control, demo-validation, session-review, knowledge, validation-lab, reliability, settings)
✅ 53 API endpoint'а
✅ 7 schemas + 7 миграций
✅ Alpha: 7 gates, 8 operator steps, 6 runnable, full happy path через HTTP
✅ SSE live updates для 10 доменов
✅ Audit JSONL для всех важных мутаций
✅ In-memory assignments/reviews/strategy_mode (с потерей при рестарте)
✅ Manual-first для alpha, нет auto-execution

### 11.4 Что не работает / не реализовано

❌ Persistence для AI assignments, session state, workspace focus, validation strategy_mode
❌ Scheduler (заглушка) — никакого cron для ingestion/reliability-recheck
❌ Health monitor auto-refresh (определён, не вызывается)
❌ SSE reconnect logic
❌ Real-data rehearsal (alpha path работает на seeded/test data)
❌ Настоящий бэктест (validation metrics синтетические)
❌ Alembic upgrade integration test
❌ Auto-execution (запрещён policy)
❌ `use-alpha-readiness.ts` экспортируется, но не используется
❌ `del session` в `ai_control/service.py:90` (явный in-memory)
❌ Audit log rotation

---

## 12. Варианты следующих шагов

### 12.1 Согласно handoff-2026-05-02

> 3-5 крупных engineering waves до alpha core, не полировать визуал.

Перед Knowledge / Research checkpoint. Сосредоточиться на backend contracts, data flow, один стабильный operator path.

### 12.2 Согласно runbook-002 §9

> Следующий engineering step — перейти к **real-data rehearsal boundaries**:
> - какие реальные/semi-real market/context inputs нужны
> - какие seeded/test shortcuts больше нельзя считать достаточными
> - какие operator actions остаются manual-only
> - какие критерии отличают alpha-core skeleton от alpha rehearsal

### 12.3 Кандидаты на следующие engineering waves

| Wave | Что | Приоритет | Зависит от |
|---|---|---|---|
| **A. Persistence** | AI assignments, session state, workspace focus, strategy_mode → БД | high | Решение архитектора о schema (вероятно новые таблицы в `ops`) |
| **B. Scheduler + health-monitor** | Реальный cron для ingestion/heartbeat/reliability-recheck | high | A (нужна персистенция для scheduled state) |
| **C. SSE reconnect + error UX** | `stream.onerror` → переподключение, UI-тосты | medium | Не зависит |
| **D. Real-data rehearsal** | Убрать demo context connectors, подключить реальные | high | C (для стабильности live) |
| **E. Code-splitting + bundle** | `lazy()` для `features/alpha` и др. | low | Не зависит |
| **F. `api/fetcher.ts` refactor** | Убрать копипаст в 10 клиентах | low | Не зависит |
| **G. Alembic upgrade integration test** | Реальный upgrade в CI | medium | Не зависит |
| **H. Audit log rotation** | Ротация `~/.local/state/clay/audit.jsonl` | low | Не зависит |
| **I. Knowledge / Research checkpoint** | Вернуться к E10 backlog | low | A, B |
| **J. Hardcoded config → env** | CORS allowlist, API base URL, timeframes | low | Не зависит |

**Из runbook-002 + handoff-2026-05-02** следует: **A → B → D** (3 waves до alpha core).

---

## 13. Вопросы к архитектору

### Q1. State management: Zustand или custom hooks навсегда?

В `CLAUDE.md.bak` указан Zustand, в коде — custom hooks. Это сознательное упрощение или незаконченный рефактор? Если сознательное — обновить `CLAUDE.md.bak` / создать `memory/project/tech-stack.md` v2. Если откат запланирован — зафиксировать в roadmap.

### Q2. Routing: hash-router когда заменим на react-router?

12 экранов работают на hash-router, но при росте (deep-link на конкретный alpha-step, query params для фильтров, nested routes) — будет узким местом. Когда менять? Что триггерит?

### Q3. Persistence: какие таблицы добавляем?

Сейчас 7 schemas (market, context, ops, demo, review, knowledge, validation). Нужно ли добавить таблицы для in-memory state (AI assignments, session state, workspace focus, validation strategy_mode)?

Если да:
- В существующую `ops` или новую schema?
- `ops.ai_assignments` + `ops.ai_model_registry`?
- `ops.session_state` (1 row) или `demo.active_session`?
- Какой retention/cleanup для assignment history?

### Q4. Scheduler: что первое?

`scheduler/service.py` — заглушка. Из кандидатов (ingestion cron, health-monitor heartbeat, reliability-recheck, validation cleanup):
- Что первое в работу?
- APScheduler из `tech-stack-v1.md` или другое?
- Внутри backend-процесса или отдельный worker?

### Q5. Real-data rehearsal: какие boundaries?

По runbook-002 §9 — нужен чёткий список:
- Какие real/semi-real market/context inputs заменяют demo connectors?
- Какие seeded/test shortcuts остаются (например, для unit-тестов)?
- Какие operator actions manual-only навсегда?
- Критерии отличия alpha-core skeleton от alpha rehearsal?

### Q6. Synthetic validation metrics: когда настоящий бэктест?

`ValidationLabService.run_validation` возвращает hard-coded числа. Когда начинаем реальный backtest? Нужна ли отдельная v2 для validation_lab (например, `validation_lab_v2` с реальной логикой)?

### Q7. `useEffectEvent`: feature-flag или production?

Используется в нескольких хуках. React 19.2 стабилен, но API помечено experimental. Нужен ли feature-flag? Или завернуть в shared hook `useSafeEffectEvent` с fallback на `useCallback`?

### Q8. Code-splitting: приоритет?

480 KB единым bundle. `lazy()` + `Suspense` для второстепенных экранов (knowledge, validation-lab, reliability) — снизит initial load на 30-40%. Когда?

### Q9. Health monitor auto-refresh: обязательно?

`HealthMonitor.refresh()` определён, не вызывается. Если не вызывать — `ServiceStatus.STALE` никогда не присваивается, и reliability gates могут показывать wrong state. Стоит ли включать в Wave B (scheduler) или это отдельная задача?

### Q10. Mission-control vs planning: устранять дубль?

`docs/planning/` и `docs/mission-control/` содержат **идентичные копии** 4 master-файлов. By design (planning/README.md объясняет), но требует discipline. Можно ли симлинком заменить? Или оставить явные копии?

### Q11. ADR-006 нужен?

Изменения с момента принятия ADR-001..005 (март 2026):
- Утверждён `approved-stack-v1.md` (Python 3.14, 5 AI rules) — не оформлен как ADR
- Принят runbook-002 (alpha operator) — не оформлен как ADR
- Приняты in-memory choices (E5, E7, E11) — не оформлены как ADR

Стоит ли оформить эти решения как ADR-006, ADR-007? Или "не ADR-решения, а operational choices"?

### Q12. CLAUDE.md.bak: обновить или удалить?

В бэкапе intelligence v1 (Zustand, react-router), но они не используются. Стоит:
- (a) Обновить intelligence v2 с фактическим стеком
- (b) Удалить intelligence вообще (она дублирует `memory/project/tech-stack.md` и `memory/project/ai-rules.md` в `.context/`)
- (c) Оставить как есть (архив)

### Q13. Outbound/Inbound для архитектора: что на вход?

Сейчас `.context/handoffs/current.md` пуст. Архитектор пишет task-packets. Следующий task-packet — это какой эпик? Wave A (persistence)? Или сразу Wave D (real-data rehearsal)?

### Q14. CI/CD: где?

В коде нет CI config (`.github/workflows/`, `.gitlab-ci.yml`). Где запускаются тесты в pipeline? Стоит ли добавить (pytest + vitest + build) в GitHub Actions?

### Q15. Анализ UI polish: насколько глубоко?

Per handoff: "не полировать визуал". Но некоторые вопросы остались:
- v17 reference vs live — расхождение заметно?
- Settings (light/dark theme) — насколько покрыт?
- Скриншоты в `.codex-screenshots/` — актуальны?

---

## 14. Что нужно от архитектора (asks)

### A. Task-packet на следующий engineering wave

Из §12: рекомендация A → B → D (persistence → scheduler → real-data). Ждём task-packet с конкретными задачами для агента (по формату из `docs/development/handoff-2026-05-02.md`).

### B. Ответы на Q1-Q15

Особенно приоритетны:
- **Q3 (persistence schema)** — блокирует Wave A
- **Q4 (scheduler)** — блокирует Wave B
- **Q5 (real-data boundaries)** — определяет следующие 3-5 waves
- **Q1 (Zustand или нет)** — мелкое, но блокирует обновление intelligence

### C. Новые ADR (если Q11 = да)

Решения по in-memory choices и runbook-002 могут быть оформлены как ADR-006, ADR-007.

### D. Обновление `docs/planning/`

Возможно нужно:
- `approved-stack-v2.md` (с учётом фактического стека, без Zustand/react-router)
- Новый `execution-backlog-v2.md` (с волнами A-J из §12.3)
- Актуализация `master-planning-review-v1.md` с текущим checkpoint

### E. Обновление `docs/development/handoff-2026-06-XX.md`

Текущий handoff = `2026-05-02`. Новый handoff после следующего wave'а будет содержать:
- Статус Wave A/B/C (что сделано, что осталось)
- Решения по Q1-Q15
- Следующий checkpoint
- Известные риски/долги (обновление §10)

### F. Возможные дополнительные snapshot-документы

Если этот snapshot помог, можно делать:
- Snapshot по конкретному эпику (например "E6 Signal Engine deep-dive" — 505 строк `signal_engine/service.py` + все модели + тесты)
- Snapshot по конкретному риску (например "Persistence: что именно теряется, как чинить, какие таблицы")
- Snapshot под конкретный task-packet ("Перед Wave A: что нужно знать агенту о текущем state, чтобы начать persistence")

---

## Приложение А: полная карта файлов (для быстрого поиска)

### A.1 Alpha-related

**Backend:**
- `src/clay/alpha/service.py` (358)
- `src/clay/alpha/models.py` (55)
- `src/clay/api/routes/alpha.py` (18)
- `src/clay/api/dependencies.py` (get_alpha_readiness_service)
- `src/clay/bootstrap.py` (alpha_readiness_service в графе)
- `tests/alpha/test_alpha_readiness_service.py` (534)

**Frontend:**
- `src/features/alpha/alpha-operator-page.tsx` (299)
- `src/features/alpha/use-alpha-operator-console.ts` (205)
- `src/features/alpha/use-alpha-readiness.ts` (59)
- `src/types/alpha.ts` (51)
- `src/api/alpha-client.ts` (17)

### A.2 E1-E12 ключевые сервисы

| E | Backend | Frontend |
|---|---|---|
| E1 | `src/clay/runtime/{states,transitions,manager}.py`, `services/`, `config/`, `preflight/` | `features/overview/overview-page.tsx` |
| E2 | `src/clay/ingestion/`, `freshness/`, `shortlist/` | (legacy) |
| E3 | `src/clay/workspace/service.py` (463) | `features/workspace/trading-workspace-page.tsx` (558) |
| E4 | `src/clay/control_center/service.py` (328) | `features/control-center/control-center-page.tsx` (832) |
| E5 | `src/clay/ai_control/service.py` (492) | `features/ai-control/ai-control-page.tsx` (789) |
| E6 | `src/clay/signal_engine/service.py` (505) | внутри Trading Workspace |
| E7 | `src/clay/session_control/service.py` (450) | `features/session-control/session-control-page.tsx` (541) |
| E8 | `src/clay/demo_trading/service.py` (289) | `features/demo-trading/demo-validation-page.tsx` (426) |
| E9 | `src/clay/session_review/service.py` (384) | `features/session-review/session-review-page.tsx` (447) |
| E10 | `src/clay/knowledge/service.py` (253) | `features/knowledge/knowledge-page.tsx` (408) |
| E11 | `src/clay/validation_lab/service.py` (352) | `features/validation-lab/validation-lab-page.tsx` (474) |
| E12 | `src/clay/reliability/service.py` (376) | `features/reliability/reliability-page.tsx` (495) |

### A.3 Routes (53 эндпоинта, 30 router-файлов)

`/health`, `/runtime/{state,transition}`, `/services`, `/configs`, `/preflight`, `/events/stream`, `/ingestion/{health,run}`, `/market-data/bars/latest`, `/context-data/summary`, `/shortlist/metrics`, `/signals/overview`, `/workspace/trading/{,focus,stream}`, `/control-center/{overview,stream}`, `/ai-control/{overview,assignments/{review,apply},stream}`, `/session/{overview,start,pause,resume,complete,replacement/{review,apply},stream}`, `/demo-trading/{overview,log-current,results/ingest,stream}`, `/session-review/{overview,feedback,stream}`, `/knowledge/{overview,items,stream}`, `/validation-lab/{overview,runs,activation/{review,apply},stream}`, `/reliability/{overview,recheck,stream}`, `/alpha/overview`.

### A.4 Миграции (7 ревизий)

`0001_e2_baseline` → `0002_e2_hypertables` (irreversible) → `0003_e8_demo_tracking` → `0004_e9_review_feedback` → `0005_e10_knowledge` → `0006_e11_validation` → `0007_incident_lifecycle`.

### A.5 Schemas (7)

`market` (3 tables), `context` (2), `ops` (3), `demo` (1), `review` (1), `knowledge` (2), `validation` (2). Alpha — нет.

---

## Приложение Б: команды для быстрого старта

```bash
# Backend
cd /home/emma/Projects/clay/backend
uv sync
uv run alembic upgrade head
make backend-test       # pytest
make backend-run        # uvicorn

# Frontend
cd /home/emma/Projects/clay/frontend
pnpm install
pnpm dev                # vite
pnpm test               # vitest
pnpm build              # tsc -b && vite build

# Default URLs
# Frontend: http://127.0.0.1:5173
# Backend:  http://127.0.0.1:8000
# Health:   http://127.0.0.1:8000/health
# Alpha:    http://127.0.0.1:8000/alpha/overview
```

---

## Приложение В: что я НЕ проверил

Честное признание границ этого snapshot:

1. **Не прочитал все 12 `build_specs/e1..e12.md`** (16-28 KB каждый) — только заголовки и общее описание
2. **Не прочитал все 12 `implementation_plans/e1..e12.md`** (25-38 KB каждый) — только заголовки
3. **Не читал 5 ADR целиком** — только резюме из `planning/`
4. **Не запускал `make backend-test` / `pnpm test`** — полагался на handoff (107/15 passed)
5. **Не делал runtime smoke test** (не поднимал backend, не дёргал `/alpha/overview`)
6. **Не изучал `docs/mission-control/.superpowers/brainstorm/`** — пустые подпапки, не копал
7. **Не изучал `claude-mem` интеграцию** (MCP, упомянуто в глобальной памяти) — не критично для проекта
8. **Не читал `frontend/src/types/*` файлы** (11 файлов, 940 строк) — только упомянул наличие

Если архитектору нужно глубже в любую из этих областей — могу сделать отдельный snapshot.

---

**Конец snapshot-документа.**

Автор: агент M3 Free (OpenCode)
Дата: 2026-06-01
Путь: `/home/emma/Projects/clay/.context/handoffs/to-architect-snapshot-2026-06-01.md`
Версия: 1.0
Статус: **временный** (удалить после прочтения архитектором)
