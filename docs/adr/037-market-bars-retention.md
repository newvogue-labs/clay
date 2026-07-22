# ADR-037: TimescaleDB Retention Policy for market.market_bars (Default-OFF)

## Status

Accepted (D-13 slice #3 implementation complete)

## Context

`market.market_bars` grows monotonically. Slice #1 added advisory DB-size monitoring; slice #2 added compression (7-day `compress_after`). This slice adds the retention mechanism — the ability to drop old chunks — but in a **disabled** state by default.

## Decision

### Native retention policy (disabled)

```sql
SELECT add_retention_policy(
  'market.market_bars',
  drop_after => INTERVAL '730 days',
  if_not_exists => TRUE
);
-- Immediately disable:
SELECT alter_job(job_id, scheduled => false)
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_retention'
  AND hypertable_name = 'market_bars';
```

| Setting | Value |
|---------|-------|
| `drop_after` | 730 days (2 years) |
| `scheduled` | `false` (disabled by default) |
| `if_not_exists` | `TRUE` (idempotent) |

### Why default-OFF

This is a **destructive** operation — chunks older than 730 days are permanently deleted. The operator must explicitly enable it:

```sql
SELECT alter_job(job_id, scheduled => true)
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_retention';
```

### Migration `0030_market_bars_retention`

- **upgrade**: `add_retention_policy` + `alter_job(scheduled => false)`
- **downgrade**: `remove_retention_policy(if_exists => TRUE)`
- **SQLite guard**: no-op on CI

### Interaction with compression (slice #2)

Retention drops old chunks including already-compressed ones. No conflict — TSDB handles this natively.

## Consequences

- Zero chunks are dropped until the operator enables the policy
- Live path is byte-identical (no app code changes)
- Future: operator enables via `alter_job(scheduled => true)` when ready
