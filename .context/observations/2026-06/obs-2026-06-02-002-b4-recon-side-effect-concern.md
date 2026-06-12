---
id: obs-2026-06-02-002
date: 2026-06-02
tags: [b4, recon, side-effect, adr-007, reliability, scheduler, refactor]
type: critical-finding
---

# B4 recon: `reliability_service.recheck` NOT side-effect-free per ADR-007

## Контекст

B4 recon (через explore-субагента, read-only) вскрыл: текущая реализация `ReliabilityService.recheck()` (`reliability/service.py:126-152`) на **каждый** вызов пишет:

1. **1 audit event** — `audit_writer.write("reliability.rechecked", {release_readiness_status, blocking_gate_count, warning_gate_count})` (line 137-144)
2. **1 bus event** — `event_bus.publish("reliability.updated", {event_type, release_readiness_status})` (line 145-151)
3. **1 DB write** — `ReliabilityStateRepository.save(last_rechecked_at=...)` (line 132-135)

Без transition-guard. На интервале `CLAY_SCHEDULER_RELIABILITY_RECHECK_INTERVAL_SECONDS=300` (5 min) это **288 записей каждого типа в день**, вне зависимости от того, изменился ли snapshot.

**External side-effects:** NONE. `build_snapshot()` — read-only aggregation через 5 под-сервисов (control_center, ai_control, demo_trading, session_review, validation_lab). Не мутирует session/strategy/workspace/AI/runtime_manager.

**Last write site:** `last_rechecked_at` пишет сам `recheck` (in-memory line 127 + DB line 132). Не job, не supervisor.

## Проблема для B4

ADR-007: scheduler-driven recheck допускается **только** если side-effect-free. Текущая реализация нарушает B3b-паттерн "audit-only-on-transition" и при scheduler-интервале создаст audit/bus flood (288/день).

**Conflict matrix:**

| Источник | Side-effect per call | B3b pattern (transition-only) | ADR-007 (no side-effect per tick) |
|---|---|---|---|
| `HealthTickJob.run()` | 0 audit + 1 bus (`health.tick`) per tick | ✅ (audit only on transition) | ✅ (bus-only, no audit per tick) |
| `ReliabilityRecheckJob.run()` (proposed) | 0 audit + 0 bus (job level) | ✅ | ✅ |
| `reliability_service.recheck()` (current) | 1 audit + 1 bus per call | ❌ (no transition guard) | ❌ (writes per call) |

**Conflict:** если B4 job просто вызывает `reliability_service.recheck(session)`, наследует все 3 side-effects → флуд. Если job применяет B3b transition-only и одновременно блокирует recheck's emissions → нужна recheck-рефакторинг.

## Решение (предложено — Option B)

**B4 ALLOWED с условием:**
1. Refactor recheck: добавить `emit: bool = True` parameter; при `emit=False` пропускает `audit_writer.write` и `event_bus.publish` (но DB write `last_rechecked_at` остаётся — это нужно для persistence).
2. B4 job вызывает `reliability_service.recheck(session, emit=False)` + сам применяет B3b transition-only (pre-tick capture 3 полей, post-recheck diff, audit + bus on transition only).
3. Manual `POST /reliability/recheck` route продолжает работать как раньше (default `emit=True`).

**Manual route impact:** zero — backward-compat (default `emit=True`).

**Scheduler DI для job:**
```python
class ReliabilityRecheckJob:
    def __init__(
        self,
        reliability_service: ReliabilityService,
        session_factory: sessionmaker,  # scheduler-owned
        audit_writer: AuditWriter,      # для transition-only audit (B3b pattern)
        event_bus: EventBus,            # для transition-only bus (B3b pattern)
    ) -> None:
        ...
```

**Diff targets (3 поля):** `release_readiness_status`, `blocking_gate_count`, `warning_gate_count`.

**Verb reuse:** `reliability.rechecked` (A6 verb, exists) для transition audit.

**Bus event reuse:** `reliability.updated` (already in SSE `RELEVANT_EVENTS`).

## Why / How to apply

- **Любой future job, вызывающий service-метод с side-effects**, должен проверять recheck/refactor этого метода ПЕРЕД scheduler registration, не после.
- **Recon-фаза (gated) оправдана:** pre-B4 мы НЕ знали, что recheck шумит. Recon поймал до написания кода — saved ~2h refactoring + code review.
- **B5 (IngestionCycleJob) → то же самое:** manual `POST /ingestion/run` уже есть, нужно проверить side-effects ingestion cycle ПЕРЕД scheduler registration.
- **Apply rule:** "Before scheduling any service method, verify it's side-effect-free. If not, refactor with an `emit` flag or pure-compute split, then schedule."

## Связанные

- B3b отчёт `../reports/last.md` §2.2 — pre-tick `pre_status` capture (anti-flood)
- B3a отчёт — `SchedulerSettings` reserved fields (`reliability_recheck_interval_seconds` = 300)
- A5 (persistence) — `ReliabilityState` model + repo
- ADR-007 (in `decisions/`) — scheduler-driven recheck side-effect constraint
- Recon-отчёт subagent'а — в [handoffs/current.md](../handoffs/current.md) §"Фаза 1 — recon"

## Lessons learned

- **Recon-фаза gated = HIGH value, low cost** (read-only, ~30 сек subagent, сэкономили бы ~2h refactoring + code review)
- **Side-effect audit must be FIRST recon question**, не afterthought
- **Manual trigger OK ≠ scheduler trigger OK** (rate amplification: 1x/day manual vs 288x/day scheduler)
- **Service-level audit-on-every-call — footgun для scheduler integration** (B3b pattern можно применить только на job-уровне, не на service-уровне без refactor)

## Pending

- **Выбор Option A vs B от Emma/архитектора** (см. [handoffs/current.md](../handoffs/current.md) §"Два пути forward")
- **Если Option B — окей на `emit: bool` flag refactor recheck?**
- **После решения — план B4 → ратификация → код**
