---
id: project-clay-tech-stack
name: Clay tech stack (intelligence v1)
description: React 19 / FastAPI / PostgreSQL+TimescaleDB / uv. Восстановлено из CLAUDE.md.bak
type: project
tags: [stack, frontend, backend, storage, dev]
created: 2026-06-01
updated: 2026-06-01
---

**Контекст:** Intelligence v1, восстановлено из `~/Projects-Backups/clay-2026-06-01-pre-context/hot/CLAUDE.md.bak`.

**Frontend:**
- React 19
- TypeScript 5.x
- Vite
- Tailwind 4
- Zustand

**Backend:**
- Python 3.14
- FastAPI
- SQLAlchemy 2.0 (Async)
- `uv` (package manager)

**Storage:**
- PostgreSQL 16+ с **TimescaleDB**
- Alembic migrations
- Test storage: SQLite with schema translation

**Transport:**
- HTTP/JSON
- **SSE** (live updates, signals, alpha readiness)
- WebSocket — **запрещён**

**Dev commands:**
- `uv sync` — install deps
- `uv run fastapi dev main.py` — run backend
- `uv run alembic upgrade head` — migrations
- `npm run dev` — run frontend
- `pytest` — backend tests
- `vitest` — frontend tests
- `make backend-{install,test,run}` / `make frontend-{install,test,build,run}` — через Makefile

**Why:** Оптимизация под async + time-series data (TimescaleDB), минимум boilerplate (uv вместо pip+venv), vendor-agnostic streaming (SSE).

**How to apply:** Не вводить новые runtime зависимости без обоснования в ADR.
