---
id: obs-2026-06-02-001
date: 2026-06-02
tags: [b3b, anti-flood, scheduler, jobs, pattern, recovery]
type: pattern-finding
---

# Pre-tick status capture для anti-flood в exception-safe wrapper

## Контекст

B3b: `_run_safely` — exception-safe wrapper для scheduled jobs в `ClayScheduler`. Цель: на exception поставить `session-scheduler` в `ERROR` + audit `service.status_changed` (только на ВХОДЕ в ERROR, anti-flood) + log + **не** re-raise (чтобы APScheduler не паузил job-slot).

В первой итерации (наивная): `prev = registry.get(...).status` **в except-блоке**, потом `update_status(ERROR)`, audit если `prev != ERROR`. Это работает для простых wrapper'ов.

**Но** в сочетании с `HealthTickJob.run()` step 3 (recovery: `update_status(HEALTHY)` ДО `refresh()`) — **ломается**:

1. pre-tick статус: `ERROR` (предыдущий tick упал)
2. `tick.run()`: `before=ERROR` → `heartbeat()` → `update_status(HEALTHY)` (recovery) → `refresh()` raises
3. except-блок: `prev = registry.get(...).status` → **HEALTHY** (post-recovery, не pre-tick)
4. `update_status(ERROR)` → `prev=HEALTHY != ERROR` → **audit пишется**
5. На 2-м подряд провале: то же самое, ещё 1 audit → **anti-flood сломан**, audit.log заливается

## Решение

Захват `pre_status = registry.get(...).status` **ДО** `job_callable()`, не в except-блоке. Anti-flood основан на pre-tick статусе.

```python
def _run_safely(self, job_callable: Callable[[], None]) -> None:
    pre_status = self._registry.get(self._SERVICE_ID).status  # ← pre-tick
    try:
        job_callable()
    except Exception as exc:
        self._registry.update_status(_, ERROR, error=str(exc))
        if pre_status != ERROR:  # ← pre-tick в audit
            self._audit_writer.write("service.status_changed", {
                "from": pre_status.value, "to": "error", "error": str(exc),
            })
        logger.exception(...)
```

## Why / How to apply

- **Любой future job с exception-safe wrapper** ОБЯЗАН брать pre-tick snapshot ДО вызова, не в except-блоке, если job сам может менять статус (recovery, reconcile, transition).
- **Apply rule:** "If the job can mutate the service status during `run()`, the wrapper must capture status **before** invocation, not **after** the exception."
- **Carry-forward на B4 (`ReliabilityRecheckJob`), B5 (`IngestionCycleJob`), и любые future jobs.**
- B4: `ReliabilityRecheckJob.run()` может флипать `reliability` service status (per recon — уточним). Pre-tick capture обязателен.
- B5: `IngestionCycleJob` (заменяет `POST /ingestion/run`) — может мутировать `ingestion` service. Pre-tick capture обязателен.

## Тонкость в спецификации

Emma's B3b spec: "Фикс в `_run_safely`: захвати `prev = registry.get('session-scheduler').status` **до** установки ERROR". Это **двусмысленно**:
- "до `update_status(ERROR)`" в except-блоке → **наивная** реализация (сломана с recovery)
- "pre-tick, до `job_callable()`" → **правильная** реализация

При code review: всегда уточнять "pre-tick vs post-ERROR-update" если спека говорит "захвати prev до установки X".

## Тестовое покрытие

- `test_exception_marks_scheduler_error_no_audit_on_repeat` — 2 подряд провала = 1 audit (anti-flood verified)
- `test_recovery_error_to_healthy` — successful tick после ERROR = 1 audit (recovery verified)
- Оба теста в `tests/scheduler/test_health_tick_job.py`

## Lessons learned

- Recovery-семантика + exception-path = subtle bug. Всегда: "если job может менять статус, pre-tick > post-exception capture"
- Двусмысленность в спецификации Emma ("prev до установки ERROR") поймана только в review — уточнять на этапе плана

## Связанные

- [B3b отчёт](../reports/last.md) §2.2 — финальная реализация
- B3b acceptance — `last_error → None` при recovery (допустимо, причина durable в audit.jsonl)
- B3a handoff [obs-2026-06-01-003](../observations/2026-06/obs-2026-06-01-003-a6-bootstrap-double-init.md) — A6 single-factory lesson
