---
id: project-clay-runbooks
name: Clay operational runbooks
description: Runbook-002 alpha operator path + acceptance state map
type: project
tags: [runbook, alpha, operations, mission-control]
created: 2026-06-01
updated: 2026-06-01
---

**Контекст:** В Clay есть `docs/mission-control/runbooks/` — операционные runbook'и.

**Runbook-002 (alpha-operator-path.md):**

Описывает один дисциплинированный **7-шаговый manual alpha operator path**:

1. `GET /alpha/overview` — snapshot
2. `POST /session/start` — session → active_session
3. `POST /demo-trading/log-current` — создаётся demo record
4. `POST /demo-trading/results/ingest` — record resolved
5. `POST /session-review/feedback` — feedback persisted
6. `POST /validation-lab/runs` — replay created
7. `POST /reliability/recheck` — reliability refreshed
8. Финальный `GET /alpha/overview` → `operator_path_ready = true`

**Runbook-002 Appendix (alpha-acceptance-state-map.md):**

Таблица связей: operator action → API contract → required state mutation → next `/alpha/overview` result → covered by test.

**Ключевые инварианты:**
- `operator_path_ready` ≠ release approval ≠ auto-execution approval
- Alpha Operator Console вызывает **существующие API**, не отдельный orchestrator
- Residual warnings остаются видимыми в `gates` и `evidence`
- Recoverable errors: no awaiting result, no reviewable record, validation API error
- Запрещено: hidden orchestrator, локальный advance, скрытие warnings, silent destructive actions

**Следующий engineering step:** real-data rehearsal boundaries (что нужно, чтобы alpha path был полезен на реальных/semi-real данных).

**Источник:** `docs/mission-control/runbooks/runbook-002-alpha-operator-path.md` + `runbook-002-alpha-acceptance-state-map.md`

**Связанные записи:**
- [ADR: alpha operator runbook](../decisions/0004-alpha-operator-runbook.md) (заполним позже)
- [roadmap.md](../roadmap.md)
- [state.md](../state.md)
