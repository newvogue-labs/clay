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
- **Read-only adapter calls** — `reconcile_orders` + `get_open_orders` for venue truth.
- **FSM-legal healing** — state drifts are healed via `controller.apply_transition`; illegal transitions are classified, not forced.
- **No fills ingestion** — only order states are reconciled; fills, bookmarks, and scheduler are out of scope.

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

- No fills ingestion (D-12a-3 covers that)
- No cursor/bookmark tracking for incremental reconcile
- No halt/pause mechanism on fatal mismatches
- No bootstrap/startup/scheduler wiring — dormant only
