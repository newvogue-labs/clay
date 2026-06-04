# Session Report — 2026-06-04 (MP2)

## Что сделано

### MP2 (deploy capstone) — FORMALLY CLOSED ✅

**8 файлов** (4 modified + 4 new):

| # | Часть | Файл | LOC |
|---|-------|------|:---:|
| 1 | `ClayScheduler.is_running` property | `scheduler/service.py` | +5 |
| 2 | `readiness_stale_threshold_seconds=120` | `settings/scheduler.py` | +5 |
| 3 | `OpsRepository.latest_ingest_run()` | `repositories_ops.py` | +6 |
| 4 | `/health/ready` — tiered, flag-aware, startup-grace | `routes/health.py` | +86 |
| 5 | `clay/__main__.py` — single-worker entrypoint | `clay/__main__.py` | +17 |
| 6 | 16 тестов (readiness/is_running/entrypoint) | 3 test-файла | +213 |

### Ключевые решения

- **Поправка 1:** `is_running` через `_running` флаг (не apscheduler `state`, не registry heartbeat)
- **Поправка 2:** tiered readiness-матрица (DB-ping HARD, scheduler flag-aware, ingest flag-aware + startup-grace)
- **Миноры:** host/port из env (не settings), один app-инстанс, prod `0.0.0.0`, workers=1, reload=False

### Регрессия

- **pytest:** 373 passed (+16 net, 0 regress)
- **pyright:** offline (not run — baseline src=35, pre-existing test-fake debt)
- **AST:** все src-файлы чисты

## Что не сделано

- Контейнеризация (Dockerfile/compose) — backlog
- Multi-worker — out of scope (ADR-007)
- `audit.jsonl` ротация — backlog
- pyright online-прогон — не подтверждён (offline)
