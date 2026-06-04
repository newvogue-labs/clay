# Текущее Состояние

**Дата:** 2026-06-04
**MVP-polish FORMALLY CLOSED ✅**
**Где остановились:** **MP2 (deploy capstone) ratified** — 373 passed (+16, 0 regress).
**Следующий шаг:** Нет. **MVP-ready.** Ждём новой волны от архитектора / Emma.

## 🛑 Точка остановки (session handoff)

**Сессия 2026-06-04 (финал MVP-polish).** C3 → MP1 → MP4 → MP3 → MP2.

**Wave E composition (historical, previous sessions):**
| Слайс | Статус |
|---|---|
| E1–E6b | FORMALLY CLOSED |

**MVP-polish composition (эта сессия):**
| Слайс | Статус |
|---|---|
| MP0 (recon) | ✅ FORMALLY CLOSED |
| MP1 (ops retention + 0011) | ✅ FORMALLY CLOSED |
| MP4 (loud-failure) | ✅ FORMALLY CLOSED |
| MP3 (config-driven) | ✅ FORMALLY CLOSED |
| MP2 (deploy capstone) | ✅ FORMALLY CLOSED |

**Итоговый pytest:** 357 → **373 passed** (+16, 0 regress).

## Ключевые решения сессии (MP2)

- **Поправка 1 (scheduler-signal):** `ClayScheduler.is_running` — НЕ registry-heartbeat-статус, а `_running` флаг (т.к. apscheduler `state` не сбрасывается после `shutdown()`)
- **Поправка 2 (ingest-freshness):** tiered readiness: DB-ping (HARD), scheduler (flag-aware), ingest (flag-aware + startup-grace). `/health/ready` отдаёт по-секционный диагноз
- **host/port:** НЕ в `SchedulerSettings`, а env напрямую в `__main__.py` (`CLAY_SERVER_HOST`/`CLAY_SERVER_PORT`)
- **Entrypoint:** один app-инстанс через `uvicorn.run("clay.api.main:app", ...)`, prod host=`0.0.0.0`, workers=1, reload=False
- **Runbook:** Emma пишет `docs/mission-control/deploy-runbook.md`

## Блокеры
— нет (MVP-ready)

## Ключевые файлы (MP2)
- `src/clay/scheduler/service.py` — `is_running` property
- `src/clay/settings/scheduler.py` — `readiness_stale_threshold_seconds: int = 120`
- `src/clay/db/repositories_ops.py` — `latest_ingest_run()`
- `src/clay/api/routes/health.py` — `/health/ready` endpoint
- `src/clay/__main__.py` — prod entrypoint
- `tests/api/test_health_ready.py` — 8 тестов readiness
- `tests/scheduler/test_scheduler_is_running.py` — 3 теста is_running
- `tests/api/test_entrypoint.py` — 5 тестов entrypoint

## Маршруты и AI Rules
- без изменений.
