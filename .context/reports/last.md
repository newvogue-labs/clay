# Отчёт: сессия 2026-06-24 — S-KELLY-2-R + S-RISKLIMITS-1/1b

## Что сделано

### S-KELLY-2-R — Risk-control gate proof (tests + evidence doc)
- **ШАГ 1:** 4 scenario-теста EV-gate (EV≤0 / below-min / above-min / degraded)
- **ШАГ 2:** 4 regression-теста hard-block (stale-market / expired-window → block_signal)
- **ШАГ 3:** Known gap confirmed: `risk-limits-active` = hardcoded `"ok"`, `blocks_start=False`
- **ШАГ 4:** Evidence-doc `docs/mission-control/ev-gate-proof.md`
- **604 passed (+11), ruff 58**
- Коммит `3311130` в main

### S-RISKLIMITS-1 / ADR-021 — дизайн session-level risk limits
- Recon: session_control путь, доступные данные (demo_trade_records, session_state), конфиг (TOML), граница с EV-gate (нулевое пересечение)
- ADR-021 draft в чат → ревью Emma → 12 правок (RV1-RV12)

### S-RISKLIMITS-1b — ADR-021 v2 записан
- 5 лимитов L1-L5 с fail-safe split (DB error → hard_fail, empty → pass)
- RV1 (критично): разведены query-exception и empty-result
- RV2: L1 со скользящим окном drawdown_window_hours=24
- RV3: L2 cooldown из таймстемпов (без новых столбцов)
- RV4-RV6: L3 defense-in-depth, L4 warn (placeholder), L5 warn manual-only
- RV7: degraded НЕ меняет L1-L5
- RV8: pre-money без override
- RV9: implementation-note (remove `del session`, inject repo)
- RV10-RV12: конфиг, пороги, Open Qs resolved/future
- Коммит `5ded307` в main (docs-only, green-guard)
- **604 passed (без регресса)**

## Коммиты

| SHA | Сообщение |
|-----|-----------|
| `3311130` | test+docs: S-KELLY-2-R — EV-gate block proof + known-gap |
| `5ded307` | docs: ADR-021 — session-level risk limits (admission gate, 12 RV) |
