# Архитектура

## Frontend Layer

- **Framework:** React 19 + TypeScript 5.x
- **Build:** Vite
- **Styling:** Tailwind 4
- **State:** Zustand
- **Transport:** HTTP/JSON для queries/mutations + **SSE для live updates** (НЕ WebSocket)
- **Test:** vitest
- **Dev URL:** http://127.0.0.1:5173

### Frontend Domains (pages/shells)
- `Control Center` (E4) — operator-facing runtime/services/ingest/incidents
- `Trading Workspace` (E3) — analyst-facing, signal/monitoring/risk
- `AI Control` (E5) — assignment review/apply, fallback posture
- `Session Control` (E7) — preflight, briefing, lifecycle, pair replacement
- `Demo Validation` (E8) — readiness gates, manual action logging
- `Session Review` (E9) — review loop, AI-assisted feedback
- `Knowledge Base` (E10) — quick-ingest, research search
- `Validation Lab` (E11) — replay runs, activation apply
- `Reliability Center` (E12) — degraded mode, release gates
- **Alpha Operator Console** — frontend shell для 7-шагового manual alpha path (Runbook-002)

## Backend Layer

- **Runtime:** Python 3.14
- **API:** FastAPI (ASGI)
- **ORM:** SQLAlchemy 2.0 (Async)
- **Package manager:** `uv` (`uv sync`, `uv run fastapi dev main.py`, `uv run alembic upgrade head`)
- **Test:** pytest
- **Dev URL:** http://127.0.0.1:8000 (health: `/health`)

### Backend Domains
- `runtime` (E1) — states, transitions, XDG config, service registry, audit
- `ingestion` (E2) — Binance Spot klines normalization, retention helpers
- `workspace` (E3) — focus control, snapshot aggregation
- `control_center` (E4) — overview aggregator
- `ai_control` (E5) — roles, model versions, assignments, conflicts
- `signal_engine` (E6) — lifecycle, ranking, confidence penalties, strategy mode
- `session_control` (E7) — hard preflight, briefing, lifecycle, pair replacement
- `demo_trading` (E8) — manual logging, result ingest, readiness
- `session_review` (E9) — audit history, demo outcomes, feedback
- `knowledge` (E10) — light-mode storage, semantic-ish chunking, advisory retrieval
- `validation_lab` (E11) — replay runs, activation review/apply
- `reliability` (E12) — degraded mode, release gates
- **alpha** (Runbook-002) — `GET /alpha/overview` aggregate readiness snapshot

### Clay Provider Abstraction Layer
- **AI calls only via backend** (AI Rule #1)
- Единая точка интеграции с AI-провайдерами
- Stream normalization в internal SSE event format (AI Rule #2)

## Data Layer

- **Primary DB:** PostgreSQL 16+ with **TimescaleDB**
- **Connection:** `CLAY_DATABASE_URL` env var
- **Migrations:** Alembic (per-domain baseline)
- **Test storage:** SQLite with schema translation (для тестов), runtime — PostgreSQL/TimescaleDB

### Schema Domains
- `market` (E2) — klines, normalized bars
- `context` (E2) — news/sentiment aggregations
- `ops` (E2) — audit, incidents, runtime events
- `demo` (E8) — `demo.demo_trade_records`
- `review` (E9) — `review.signal_feedback`
- `knowledge` (E10) — `knowledge.knowledge_items`, `knowledge.knowledge_chunks`
- `validation` (E11) — `validation.validation_runs`, `validation.activation_reviews`

## External Integrations

- **Binance Spot klines** (E2) — market data source
- **News & sentiment** (E2) — pluggable demo connectors
- **AI providers** — через Clay Provider Abstraction Layer (backend only)

## Observability

- **Logs:** стандартный Python logging
- **Audit:** `ops` schema + audit/event publication (при manual changes)
- **Health:** `GET /health` + per-domain health endpoints (`/ingestion/health`)
- **SSE streams:** per-domain `/stream` endpoints для live UI refresh triggers

## Transport (AI Rule #3)

- **HTTP/JSON** — queries, mutations
- **SSE** — live updates, signals, focus changes, alpha readiness
- **WebSocket — НЕ используется** (запрещён policy)

## Runtime States

| State | Trigger | Allowed actions |
|---|---|---|
| `idle` | startup | read-only |
| `active_run` | user_start | all |
| `paused` | user_pause | read-only |
| `degraded` | health_check_fail | safe subset |
| `error_recovery` | exception | recovery only |
| `operator_path_ready` (alpha) | successful Runbook-002 completion | manual-only (НЕ auto-execution) |

## AI Provider Abstraction Layer

```
Frontend  ──HTTP/JSON──▶  Backend (FastAPI)
                              │
                              ├──▶ Clay Provider Abstraction
                              │      │
                              │      ├──▶ Provider A (OpenAI / Anthropic / ... )
                              │      ├──▶ Provider B
                              │      └──▶ Local fallback
                              │
                              └──▶ SSE stream (normalized events)
                                       │
                                       └──▶ Frontend
```

**Граница:**
- Frontend НЕ вызывает AI-провайдеров напрямую (AI Rule #1)
- Все стримы нормализованы в internal SSE event format (AI Rule #2)
- AI = synthesis layer, **Market Data и Risk Rules = ground truth** (AI Rule #4)
