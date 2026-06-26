# Отчёт: сессия 2026-06-26 — S-EXEC-4 merged, review passed

## Что сделано

### S-EXEC-4 — MERGED — Testnet live smoke + adapter fixes

Merge commit `b23ef5d...` (no-ff) в `main`. Branch `feat/testnet-smoke` удалена.

#### Регресс-база (Emma checkpoint§)

**Full offline-suite (без ключей):**
- `pytest -q -m "not slow"` → **682 passed, 2 deselected (slow), 86.75s**
- `test_testnet_execution_smoke` → **skipped** (нет ключей), main зелёный
- ruff → **0** (все checks passed)

#### S-EXEC-4 smoke evidence (dedicated run, order 9585437)

| Шаг | Action | Result | Latency |
|-----|--------|--------|---------|
| 1 | `load_markets()` | 2140 markets | ~2950ms |
| 2 | `place_order BTCUSDT 0.001 @ $50k` | **open** (9585437) | 304ms |
| 3 | `get_open_orders` | 4 open | 294ms |
| 4 | `cancel_order 9585437` | **canceled** | 347ms |
| 5 | `get_open_orders` | 3 open | — |

- **Rate-limit:** 55/6000/min
- **Fills:** 0 (limit $50k при BTC ~$104k → non-marketable)
- **Контаминация demo_trade_records:** 0 (adapter-level only, `source="testnet"`)
- **Isolation (ADR-024 §d):** `DEFAULT_READ_SCOPE = {baseline, live}` не тронут, testnet исключён

#### Адаптерные фиксы (merged order-path не тронут)

1. **`urls["api"]` override removed** — `set_sandbox_mode(True)` сам ставит правильный dict-структуру URL
2. **`cancel_order` signature** — `id=order_id` (было `order_id=`)
3. **`timeout: 30000`** — добавлен в ccxt init options
4. **Unique `client_order_id`** — `f"smoke-{timestamp_ms}"` (фикс в скрипте, не в адаптере)

**Claim подтверждён на main:** `binance_testnet.py` корректно пробрасывает `client_order_id` → `newClientOrderId`. Адаптер правке не нужен, слайс чисто аддитивный.

#### Files added

| Файл | Описание |
|------|----------|
| `backend/scripts/smoke_testnet_execution.py` | Live smoke script (manual/gated) |
| `backend/tests/execution/test_testnet_smoke.py` | pytest wrapper, `@slow`, skips без keys |
| `.context/observations/2026-06/obs-2026-06-26-001-execution-smoke.md` | Evidence-отчёт |

## Итог

**HEAD `b23ef5d` (S-EXEC-4 merge).** 
682 passed excl slow, 2 deselected slow, 1 skipped smoke. ruff 0.

**Next: S-EXEC-3** (RV8 override sequence + LiveExecutionClient stub) — самый высокорисковый шаг к live.
