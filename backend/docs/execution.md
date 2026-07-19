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
