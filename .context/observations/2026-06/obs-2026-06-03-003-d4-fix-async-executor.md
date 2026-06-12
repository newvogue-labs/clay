---
name: D4-FIX — AsyncIOExecutor для async ingestion job
description: Scheduler-driven ingestion цикл никогда не исполнялся — async `_arun_safely` попадал в sync ThreadPoolExecutor. Фикс: аддитивный AsyncIOExecutor.
type: fix
---

**Проблема/Контекст:**

D4 sustained rehearsal выявил латентный баг: `AsyncIOScheduler` constructor в `scheduler/service.py:143-146` заменял `"default"` executor на `ThreadPoolExecutor(max_workers=4)` (B0 mitigation для sync health/reliability job'ов). `add_ingestion_cycle_job()` не указывал executor → APScheduler брал `"default"` = `ThreadPoolExecutor` → async `_arun_safely` исполнялся как sync-функция → возвращал coroutine → `coroutine never awaited`. Ingestion-цикл НЕ ИСПОЛНЯЛСЯ через планировщик.

D1-успех был только ручной `POST /ingestion/run` (крутится на event loop запроса). Путь «планировщик сам запускает цикл» оставался непроверенным до D4.

**Решение:**
- `"async": AsyncIOExecutor()` — аддитивный executor в executors dict
- `executor="async"` в `add_ingestion_cycle_job()`
- Sync job'ы не тронуты (явно `executor="default"`)
- T2 test доказывает: `run_once` реально вызывается через scheduler
- T1 test пин: executor mapping правильный

**Why / How to apply:**
- D4-FIX закрывает дыру в покрытии: scheduler-driven path теперь проверен
- T2 regression test падал бы на старом коде — гарантия, что баг не вернётся
- Sync executor деградации нет — health/reliability job'ы не тронуты
