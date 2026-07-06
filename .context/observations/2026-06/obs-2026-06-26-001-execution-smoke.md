# Observation: S-EXEC-4 testnet smoke evidence (2026-06-26)

## Context

S-EXEC-4 — live testnet integration smoke for `BinanceTestnetExecutionClient`.
- Branch: `feat/testnet-smoke`
- Adapter: `backend/src/clay/execution/binance_testnet.py` (`BinanceTestnetExecutionClient`)
- Script: `backend/scripts/smoke_testnet_execution.py`
- Env: `CLAY_EXECUTION_MODE=testnet`, `CLAY_BINANCE_TESTNET_API_KEY/SECRET` from `backend/.env` (not tracked)

## Lifecycle (Dedicated S-EXEC-4 run, order 9585437)

| Шаг | Action | Result | Latency |
|-----|--------|--------|---------|
| 1 | `load_markets()` | 2140 markets loaded | ~2950ms |
| 2 | `place_order BTCUSDT buy 0.001 limit 50000.0` | **open** (order 9585437) | 304ms |
| 3 | `get_open_orders` | 4 open orders (incl. our new) | 294ms |
| 4 | `cancel_order 9585437` | **canceled** (transactTime: 1782494874158) | 347ms |
| 5 | `get_open_orders` | 3 open (ours gone) | — |

**Rate-limit weight:** 55/6000/min

## «1 closed» explanation

Первые 3 ордера (9581217, 9581830, 9582048) — из РАННИХ тестовых запусков (`python -c`), не из S-EXEC-4 proper. В dedicated S-EXEC-4 run (order 9585437) **0 fills**, ордер оставался open до cancel. Это confirms non-marketable design: limit $50,000 below BTC market (~$104k), не исполняется.

## Isolation: 0 контаминации калибровки

- Smoke НЕ пишет в `demo_trade_records` (adapter-level only)
- `source="testnet"` не попадает в `DEFAULT_READ_SCOPE = frozenset({"baseline","live"})`
- Калибровка p/b default-scope не тронута (ADR-024 §d инвариант подтверждён)

## What was fixed during smoke

1. **`urls["api"]` override removed** — `set_sandbox_mode(True)` сам ставит правильный dict-структуру URL; hand-rolled override ломал endpoint resolution.
2. **`cancel_order` signature fixed** — ccxt ждёт `id=`, не `order_id=`.
3. **`timeout: 30000` added** к ccxt init options.
4. **Unique `client_order_id`** — `f"smoke-{int(time.time() * 1000)}"` вместо хардкода `"smoke-001"`.

## Regression baseline (2026-06-26)

- pytest: **13 passed, 1 skipped** (smoke test skips без keys)
- ruff: **0** (все checks passed)
- offline-skip: ✅ `test_testnet_execution_smoke` → skip при отсутствии env

## Next

- Merge `feat/testnet-smoke` → main (остановка на ревью)
- S-EXEC-3: RV8 override sequence
