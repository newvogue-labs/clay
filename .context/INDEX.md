# Context Index

**Дата обновления:** 2026-06-01
**Размер папки:** ~5 KB (после начальной инициализации)
**Всего файлов:** 7 (будет расти)

## 🔥 Горячее (прочитать первым)

- [state.md](state.md) — текущее состояние (Wave 1 done, alpha runbook done, **A1 persistence DDL done**, ждём A2)
- [handoffs/current.md](handoffs/current.md) — последнее задание (пока пусто — A1 выполнен, ждём A2)
- [reports/last.md](reports/last.md) — последний отчёт (**A1: 6 таблиц + 5 CHECK + 107 passed**)

## 📚 Долгосрочная память

### memory/user/
- (пока пусто — заполним на шаге 3)

### memory/project/
- (пока пусто — заполним на шаге 3)

### memory/feedback/
- (пока пусто)

### memory/reference/
- (пока пусто)

## 📜 Решения (ADR)

- (пока пусто — заполним на шаге 4)

## 🔍 Наблюдения (последние 10)

- [2026-06/obs-2026-06-01-002-a1-sqlite-vs-pg.md](observations/2026-06/obs-2026-06-01-002-a1-sqlite-vs-pg.md) — **alembic chain Clay не идёт на SQLite** (`0001` содержит `CREATE SCHEMA` + `timescaledb`); для A1 использован PG
- [2026-06/obs-2026-06-01-001](observations/2026-06/) — настройка `.context/` (от прошлой сессии)

## 🏗 Архитектура

- [architecture.md](architecture.md) — общая схема (Backend / Frontend / Storage / AI)

## 🗺 Roadmap

- [roadmap.md](roadmap.md) — E1-E12 done, alpha runbook done, real-data rehearsal next

## 📥 Входящие / 📤 Исходящие

- [handoffs/current.md](handoffs/current.md) — задание от архитектора (пока пусто, **ждём A2**)
- [handoffs/to-architect-snapshot-2026-06-01.md](handoffs/to-architect-snapshot-2026-06-01.md) — **snapshot проекта для архитектора** (1133 строки, 72K, **временный**)
- [handoffs/to-architect-cover-letter-2026-06-01.md](handoffs/to-architect-cover-letter-2026-06-01.md) — cover letter для архитектора (схема ролей, механика)
- [handoffs/recon-a0-2026-06-01.md](handoffs/recon-a0-2026-06-01.md) — **отчёт A0 recon** (8 секций, in-memory state снят, baseline 107 passed)
- [reports/last.md](reports/last.md) — **отчёт A1** (6 таблиц + 5 CHECK + 107 passed, 5 вопросов к архитектору)
- [handoffs/archive/](handoffs/archive/) — выполненные задания
- [reports/archive/](reports/archive/) — архив отчётов

## 🔄 Session Handoff

- [AGENTS.md](AGENTS.md) — правила для агента (включая Session Handoff Protocol)
- [handoff-template.md](handoff-template.md) — шаблон промпта для перехода между сессиями
