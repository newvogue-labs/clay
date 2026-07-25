# Execution Layer

## Venue Selection (D-venue)

The execution layer supports multiple exchanges via `CLAY_EXECUTION_VENUE`:

| Venue | Adapter | Supported Modes |
|-------|---------|-----------------|
| `binance` (default) | `BinanceExecutionAdapter` | testnet |
| `bybit` | `BybitExecutionAdapter` | testnet, demo |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAY_EXECUTION_VENUE` | `binance` | Exchange selector: `binance` or `bybit` |
| `CLAY_EXECUTION_MODE` | `dry_run` | Execution mode: `dry_run`, `testnet`, or `demo` |

### Credential Resolution

API keys are resolved by `(venue, mode)` pair:

| (venue, mode) | Key Env Var | Secret Env Var |
|---------------|-------------|----------------|
| (binance, testnet) | `CLAY_BINANCE_TESTNET_API_KEY` | `CLAY_BINANCE_TESTNET_API_SECRET` |
| (bybit, testnet) | `CLAY_BYBIT_TESTNET_API_KEY` | `CLAY_BYBIT_TESTNET_API_SECRET` |
| (bybit, demo) | `CLAY_BYBIT_DEMO_API_KEY` | `CLAY_BYBIT_DEMO_API_SECRET` |
| (binance, demo) | *not supported* | *not supported* |

Unknown venue values revert to `binance` with a warning. Unknown mode values revert to `dry_run` with a warning. When credentials are empty, no adapter is built (fail-closed).

### Market Rules — Upper-Bound Sentinel (D-23)

`MarketRules.max_amount` and `MarketRules.max_price` are `Decimal | None`:

- **`None`** — venue does not publish this limit. Invariants that use the field (`QTY_ABOVE_MAX`, `PRICE_ABOVE_MAX`) are **not applicable** and pass by definition.
- **`Decimal("0")`** — a genuine zero, never a placeholder for absence.

The helper `_dec_upper_bound()` in `ccxt_base.py` parses ccxt market data: `None`/missing → `None`, zero/negative → `None` + WARNING (observed via logging), positive → `Decimal`. The existing `_dec()` helper (used for min bounds and steps) is unchanged.

### Read-Mapping None-Safety (D-24)

All `.get()` calls in the read-mapping layer (`_ack_from_response`, `_snapshot_from_response`, `_fills_from_trades`, `_fill_from_my_trade`, `get_balances`) are guarded against `None` values from venue responses.

**Root cause:** `dict.get("key", default)` returns `default` only when the key is absent. When the key exists with value `None`, `.get()` returns `None`, not the default. Three consecutive incidents: `side=None` (D-20), `max_price=None` (D-23), `timestamp=None` (D-24).

**Fix pattern:** All `.get("key", "default")` replaced with `.get("key") or "default"`. This guarantees `None` → default, regardless of key presence.

**Status handling:** `_status_from_response()` distinguishes "key absent" (= `"open"`, current behavior) from "key present, value None/empty" (= `""` → `UNKNOWN` via `_map_state`). Does not change backward compatibility.

**Taxonomy — "order placed, response not parsed":** `place_order` wraps `_ack_from_response` in try/except → `AmbiguousExecutionError` with `client_order_id` and response key/type dump in the log. The existing `ResilientExecutionAdapter` automatically reconcile-by-cid, so the orphan order is resolved without re-placement.

### Bootstrap Flow

`_build_execution_client()` in `bootstrap.py`:
1. Resolves `Environment` from mode (`testnet` → `TESTNET`, `demo` → `DEMO`, else → `None`)
2. Returns `None` if env is `None` or credentials are empty
3. Instantiates the venue-specific adapter
4. Wraps in `ResilientExecutionAdapter` → `ExecutionProofGate`

## Order Ledger — Trade-Fill Recording

The order ledger records trade-level fills with dedup and automatic recalculation of the `filled` quantity on the projection.

### Overview

- **Dormant by default** — `order_ledger_enabled` is `False`; no production call-sites exist yet.
- **Dedup key** — `UNIQUE(venue, trade_id)` on `OrderFillRecord`. Duplicate trade IDs are silently skipped.
- **Filled recalculation** — after each batch insert, `filled_qty` is recomputed as the sum of all `quantity` values (Decimal in Python, not server-side SUM on Text).
- **Terminal state is caller-controlled** — `record_fills` accepts a `to_state` parameter and enforces FSM legality, but never independently transitions to `FILLED`.

### API

```python
controller.record_fills(
    client_order_id: str,     # order identifier
    fills: list[Fill],        # incoming trade fills
    to_state: LedgerState,    # target state (e.g. PARTIALLY_FILLED)
    expected_version: int,    # optimistic lock version
) -> OrderCurrentState
```

### Atomicity (7 steps)

1. Load projection by `client_order_id` → `OrderNotInLedgerError` if missing.
2. Extract `venue` from projection.
3. Dedup: filter out fills whose `(venue, trade_id)` already exist.
4. Batch-insert remaining `OrderFillRecord` rows.
5. Recalculate `filled` = sum of all `quantity` for the order (Decimal).
6. Append lifecycle event to `order_events`.
7. CAS-update projection with FSM + version check.

### Idempotency

- If dedup removes all incoming fills **and** `to_state` equals the current state → **no-op**: no inserts, no event, no version bump.
- If new fills exist → event is always written, including self-transitions (`PARTIALLY_FILLED → PARTIALLY_FILLED`).

### Error Cases

| Error | Condition |
|-------|-----------|
| `OrderNotInLedgerError` | No projection for `client_order_id` |
| `IllegalTransitionError` | FSM does not allow `current → to_state` |
| `ConcurrencyConflictError` | `expected_version` does not match projection |

## Order Reconcile Service — Venue-State Reconciliation

Standalone service that compares exchange order states with ledger projections and heals FSM-legal drifts.

### Overview

- **Dormant by default** — no config flag, no bootstrap wiring, no production call-sites.
- **Read-only adapter calls** — `reconcile_orders` + `get_open_orders` for order-state truth; `get_my_trades` for fills ingestion.
- **FSM-legal healing** — state drifts are healed via `controller.apply_transition` (order-states) or `controller.record_fills` (fill-bearing states). Illegal transitions are classified, not forced.
- **Durable cursor** — `reconcile_bookmark` table tracks last processed trade_id per `(venue, entity_type, symbol)` for incremental replay.

### Mismatch Kinds

| Kind | Fatal | Description |
|------|-------|-------------|
| `STATE_DRIFT` | no | Venue state differs from ledger; healed via FSM-legal transition |
| `ILLEGAL_DRIFT` | yes | Venue state would require illegal FSM transition (e.g. INTENT→FILLED) |
| `VENUE_ORPHAN` | yes | Venue order exists with no matching ledger projection |
| `LEDGER_ORPHAN` | no | Active ledger projection has no matching venue order |

### State Mapping

| Venue `OrderState` | Ledger `LedgerState` |
|--------------------|-----------------------|
| `new` | `ACKNOWLEDGED` |
| `partially_filled` | `PARTIALLY_FILLED` |
| `filled` | `FILLED` |
| `canceled` | `CANCELED` |
| `rejected` | `REJECTED` |
| `expired` | `EXPIRED` |

### What This Service Does NOT Do

- ~~No halt/pause mechanism on fatal mismatches~~ — **Wired in D-15** (`CLAY_PROOF_ENFORCE_HALT_LATCH=true`). Fatal mismatches now engage the durable halt-latch via `FatalHaltWiring`, halting execution globally.

### Reconcile Scheduling (D-12c)

The reconcile service is wired into two call-sites — both dormant by default (opt-in, testnet-only):

1. **Periodic scheduler job** — `OrderReconcileJob` (async, `CLAY_SCHEDULER_RECONCILE_ENABLED=true`). Iterates active projections, reconciles each `(venue, symbol)` pair, emits `reconcile.cycle` audit/bus on state transitions. Fatal mismatches engage the durable halt-latch via `fatal_halt_wiring` when bound (D-15).

2. **Pre-arm reconcile hook** — `OverrideService.set_pre_arm_reconcile()`. Called before `confirm_override` flips `pending → confirmed`. If fatal mismatches are found, the arm is denied (`ExecutionConfigError`). Hook exceptions → fail-closed (deny).

**Env vars:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAY_SCHEDULER_RECONCILE_ENABLED` | `false` | Master gate for job + adapter + pre-arm hook |
| `CLAY_SCHEDULER_RECONCILE_INTERVAL_SECONDS` | `300` | Job tick interval |
| `CLAY_SCHEDULER_RECONCILE_LOOKBACK_SECONDS` | `3600` | `since` window for `reconcile_symbol` |

**Testnet-only constraint:** The adapter is only built when `mode != "live"` and testnet API keys are present. In live mode or without keys, the reconcile job is silently not built.

**Bookmark cursor fix (D-12c):** The bookmark now advances only to the latest *ingested* fill (the one actually written via `record_fills`), not the latest raw fill from the venue. This prevents skipping fills when orphan fills are present ahead of the cursor.

### Halt-Latch Enforcement (D-15)

The FATAL→halt enforcement loop is now wired (D-12d signal-only → D-15 enforced). Requires two flags:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAY_PROOF_ENFORCE_SESSION` | `false` | Master gate for all session-mode probes |
| `CLAY_PROOF_ENFORCE_HALT_LATCH` | `false` | Enable halt-latch mode probe + fatal_halt_wiring |

**Wiring sites:**
- **bootstrap.py** — late-binds `halt_probe` into `ExecutionProofGate.session_mode_probe` when both flags ON. Default OFF → `SessionMode.NORMAL` → live path byte-identical.
- **reconcile_job.py** — `fatal_halt_wiring` param → `on_fatal_report` per-pair when `report.has_fatal`.
- **startup_reconciliation.py** — `fatal_halt_wiring` param → `on_fatal_report` + `on_escalated_fatal`.
- **lifespan.py** — builds `FatalHaltWiring` when `proof_enforce_halt_latch` is ON.

**Not doing:** Narrow per-symbol halt (future slice).

### Fills Reconcile (D-12b-2)

Ingests venue trades via `get_my_trades` cursor (`fromId` + `since`) and writes them to the journal through `record_fills`.

- **Cursor** — `reconcile_bookmark` (migration 0027): `(venue, entity_type, symbol)` → `last_trade_id`, `last_timestamp`. Updated only after successful ingestion.
- **Dedup** — `record_fills` deduplicates on `UNIQUE(venue, trade_id)` before insert; `filled_qty` is recalculated as Decimal sum.
- **Heal** — for `PARTIALLY_FILLED`/`FILLED` targets with available fills → `record_fills` (FSM-legal, CAS-safe). For other states → `apply_transition`.
- **Fail-closed** — if `get_my_trades` throws, bookmark is not advanced; next run re-reads from last cursor.
- **Orphan fills** — fills with `venue_order_id` matching no projection → `LEDGER_ORPHAN` (signal-only, not fatal).

**Not doing:** Bybit execId pagination / scheduler / halt / bootstrap wiring.
