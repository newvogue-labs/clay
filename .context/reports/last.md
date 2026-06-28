# Отчёт: сессия 2026-06-28 — S-LINT-1c (src/ pyright 338→0)

## Что сделано

### S-LINT-1c / src/ pyright 0 — COMPLETED ✅

pyright `src/` очищен с 338 до 0 за 4 sub-slices, 5 коммитов в `main`:

| Sub-slice | Описание | Коммит | Pyr ↓ |
|-----------|----------|--------|-------|
| 1c-a-1 | `binance_testnet.py` — ccxt-граница + bugfix (UnboundLocalError, fetch_order kwarg) | `226b989` | 52→0 |
| 1c-a-2 | `signal_engine/service.py` — `list[MarketBar]`, RiskConfig/KellyConfig direct access | `59ce86c` | 48→30 |
| 1c-a-3a | `repositories_*.py` + `ai_control/` — dict[str,object], tuples, CursorResult cast | `d51742b` | 30→18 |
| 1c-b | pre-commit + CI workflow + Makefile aggregates | `8112ffb`~`b533c5d` | — |
| 1c-c | Literal boundary casts в `demo_trading/service.py` + `reliability/service.py` | `351d4ee` | 18→13 |
| 1c-d | Optional narrowing (override, replay, session_control) + protocol conformance (SOURCE→source, CancelResult) | `18af555`~`4b01961` | 13→0 |

#### Ключевые архитектурные решения:

- **ccxt-граница:** `_ccxt_dict`/`_ccxt_list` boundary helpers, не сыпем `# pyright: ignore` на каждую строку
- **Literal-границы:** чиним producer'а (`_resolve_release_status → ReleaseReadinessStatus`), не cast'им на consumer'е
- **Optional-инварианты:** честный `assert` там, где guard гарантирует non-None (не «затычка»). Никаких рантайм-изменений.
- **Протокол ExecutionClient:** `SOURCE`→`source` (lowercase), `cancel_order` → `CancelResult`, LiveExecutionClient — полный набор stub-методов. `@runtime_checkable`.
- **Inline cast** `cast(RiskConfig, load_scope("risk"))` на call site (тип возврата — `RuntimeConfig | RiskConfig`, но scope="risk" всегда RiskConfig).

#### Регресс-база

- **Full suite:** **736 passed / 2 deselected /ruff 0** (+2 теста vs baseline: 734→736 за счёт регрессии binance_testnet bugfix)
- **Pyright (src/):** **0 errors, 0 warnings, 0 informations**

## Итог

**HEAD `4b01961`.** 736 passed, 2 deselected, ruff 0, pyright src/ 0.

**S-LINT-1c полностью закрыт.** Took 1 session, ~6h wall-clock, 5 commits to main.

**Дрейф завершён:** 338 pyright errors → 0.

## Next

**S-LINT-2** — pyright на app/, hooks/, tests/ (в разы легче — ~20-30 ошибок, много из 1c уже не cascade'ит). Или донор-слайс по выбору Emma.
