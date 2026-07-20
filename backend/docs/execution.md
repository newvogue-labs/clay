# Execution Layer

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

- No halt/pause mechanism on fatal mismatches

### Reconcile Scheduling (D-12c)

The reconcile service is wired into two call-sites — both dormant by default (opt-in, testnet-only):

1. **Periodic scheduler job** — `OrderReconcileJob` (async, `CLAY_SCHEDULER_RECONCILE_ENABLED=true`). Iterates active projections, reconciles each `(venue, symbol)` pair, emits `reconcile.cycle` audit/bus on state transitions. Fatal mismatches are signalled via `reconcile.fatal_mismatch` audit only — no halt/pause.

2. **Pre-arm reconcile hook** — `OverrideService.set_pre_arm_reconcile()`. Called before `confirm_override` flips `pending → confirmed`. If fatal mismatches are found, the arm is denied (`ExecutionConfigError`). Hook exceptions → fail-closed (deny).

**Env vars:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAY_SCHEDULER_RECONCILE_ENABLED` | `false` | Master gate for job + adapter + pre-arm hook |
| `CLAY_SCHEDULER_RECONCILE_INTERVAL_SECONDS` | `300` | Job tick interval |
| `CLAY_SCHEDULER_RECONCILE_LOOKBACK_SECONDS` | `3600` | `since` window for `reconcile_symbol` |

**Testnet-only constraint:** The adapter is only built when `mode != "live"` and testnet API keys are present. In live mode or without keys, the reconcile job is silently not built.

**Bookmark cursor fix (D-12c):** The bookmark now advances only to the latest *ingested* fill (the one actually written via `record_fills`), not the latest raw fill from the venue. This prevents skipping fills when orphan fills are present ahead of the cursor.

### Fills Reconcile (D-12b-2)

Ingests venue trades via `get_my_trades` cursor (`fromId` + `since`) and writes them to the journal through `record_fills`.

- **Cursor** — `reconcile_bookmark` (migration 0027): `(venue, entity_type, symbol)` → `last_trade_id`, `last_timestamp`. Updated only after successful ingestion.
- **Dedup** — `record_fills` deduplicates on `UNIQUE(venue, trade_id)` before insert; `filled_qty` is recalculated as Decimal sum.
- **Heal** — for `PARTIALLY_FILLED`/`FILLED` targets with available fills → `record_fills` (FSM-legal, CAS-safe). For other states → `apply_transition`.
- **Fail-closed** — if `get_my_trades` throws, bookmark is not advanced; next run re-reads from last cursor.
- **Orphan fills** — fills with `venue_order_id` matching no projection → `LEDGER_ORPHAN` (signal-only, not fatal).

**Not doing:** Bybit execId pagination / scheduler / halt / bootstrap wiring.
