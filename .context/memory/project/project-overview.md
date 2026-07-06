---
id: project-clay-overview
name: Clay — trading workspace
description: Trading workspace: signals, review, control. Wave 1 done, alpha hardening done.
type: project
tags: [trading, signals, ai, workspace]
created: 2026-06-01
updated: 2026-06-01
---

**Что это:** Clay — собственный trading workspace. Signals, review, control.

**Текущее состояние (2026-06-01):**
- Wave 1 (E1-E12) реализован полностью
- Alpha operator runbook (Runbook-002) добавлен и активен
- Следующий шаг: real-data rehearsal boundaries

**Архитектурные слои:**
- Frontend: React 19 + TS + Vite + Tailwind 4 + Zustand
- Backend: Python 3.14 + FastAPI + SQLAlchemy 2.0 (Async)
- Storage: PostgreSQL 16+ + TimescaleDB
- Transport: HTTP/JSON + SSE (НЕ WebSocket)

**Ключевые принципы:**
- AI = synthesis layer, Market Data и Risk Rules = ground truth
- Manual-first для alpha, auto-execution запрещён
- Все изменения — через review/apply flow, без silent switching

**Источник правды:** см. `README.md` в корне + `docs/planning/{blueprint,tech-stack,execution-backlog,master-planning-review}-v1.md`

**Связанные записи:**
- [tech-stack](tech-stack.md)
- [ai-rules](ai-rules.md)
- [runbooks](runbooks.md)
- [architecture.md](../architecture.md)
- [roadmap.md](../roadmap.md)
