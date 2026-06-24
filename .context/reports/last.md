# Отчёт: сессия 2026-06-24 — S-KELLY-2-R (EV-gate block proof + known gap)

## Что сделано

### S-KELLY-2-R — Risk-control gate proof (tests + evidence doc)
- **ШАГ 1:** 4 scenario-теста для 4 EV-полос через `_apply_kelly_sizing → _build_execution_notes`:
  - a) EV≤0 → f=0, gate triggered, note "negative edge"
  - b) 0<EV≤min_ev → f=0, gate triggered, note "below min, signal still visible"
  - c) EV>min_ev → f>0 (capped), gate open, note "Advisory size: X%"
  - d) degraded → f=None, gate not triggered, note "System degraded"
- **ШАГ 2:** 4 regression-теста hard-block (stale-market / expired-window → block_signal):
  - `_resolve_response_action` → "block_signal"
  - `_build_execution_notes` → "Do not execute"
  - `_resolve_signal_state` → "invalidated" / "expired"
- **ШАГ 3:** Recon `session_control/service.py:522`:
  - `risk-limits-active` = hardcoded `status="ok"`, `blocks_start=False`
  - **Known gap:** session-level capital/position limits NOT enforced
- **ШАГ 4:** Evidence-doc `docs/mission-control/ev-gate-proof.md`:
  - Таблица 4 сценариев с привязкой к тестам
  - Golden на Ring 1 данных (p=0.433, b=1.761, EV=0.195R → gate PASS, f=0.02)
  - Scope & limits: EV-gate блокирует РАЗМЕР, session-level — заглушка
  - Ссылка на ADR-020
- **604 passed (+11), ruff 58 (без изменений)**

## Коммит

Прямой в main (test+docs-only, green-guard):
```
test+docs: S-KELLY-2-R — EV-gate block proof + known-gap (session risk-limits stub)
```
