# ADR-038: TimescaleDB Continuous Aggregate for market.market_bars (1h→1d)

## Status

Accepted (D-13 slice #4 implementation complete)

## Context

`market.market_bars` stores multiple timeframes (5m, 15m, 1h) in one hypertable. Queries for daily OHLCV currently aggregate raw 1h bars at read-time. A continuous aggregate pre-computes this aggregation.

## Decision

### Continuous aggregate: `market.market_bars_1d`

```sql
CREATE MATERIALIZED VIEW market.market_bars_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', bar_open_time) AS bucket,
    symbol, source,
    first(open, bar_open_time) AS open,
    max(high)                  AS high,
    min(low)                   AS low,
    last(close, bar_open_time) AS close,
    sum(volume)                AS volume,
    sum(quote_volume)          AS quote_volume
FROM market.market_bars
WHERE timeframe = '1h'
GROUP BY bucket, symbol, source
WITH NO DATA;
```

| Setting | Value |
|---------|-------|
| Source | `1h` bars only (daily = exact 24h bucket, no sub-hour ambiguity) |
| Refresh policy | ON (start_offset 3d, end_offset 1h, schedule 1h) |
| `first`/`last` | Core TSDB functions (no toolkit dependency) |

### Why 1h→1d

- Exact daily tiling: 1h bars align perfectly with 24h buckets
- Avoids 5m/15m which would create many more intermediate rows in the aggregate
- `first`/`last` on open/close preserves OHLCV semantics

### Why refresh ON (not default-OFF)

Unlike retention (D-13 #3), this is **non-destructive**:
- Raw data is untouched
- Write-path (`upsert_market_bars`) is untouched
- The CAGG is dormant at the application layer (no code reads it yet)
- Refresh ON means the aggregate is always current when a consumer is added

### Migration `0031_market_bars_cagg`

- **upgrade**: `CREATE MATERIALIZED VIEW WITH (timescaledb.continuous)` + `add_continuous_aggregate_policy`
- **downgrade**: `remove_continuous_aggregate_policy` + `DROP MATERIALIZED VIEW`
- **SQLite guard**: no-op on CI
- **Revision ID** shortened to `0031_market_bars_cagg` (21 chars) to fit 32-char Alembic version table limit

## Consequences

- CAGG view appears in `timescaledb_information.continuous_aggregates`
- Refresh policy is active — background worker updates the aggregate hourly
- Compression (slice #2) and retention (slice #3) coexist: compression applies to the materialization hypertable; retention drop_chunks can target the CAGG if needed in the future
- No application code changes — live path is byte-identical
