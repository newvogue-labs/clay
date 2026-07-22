# ADR-036: TimescaleDB Compression for market.market_bars

## Status

Accepted (D-13 slice #2 implementation complete)

## Context

`market.market_bars` is the only monotonically growing production hypertable (8+ chunks). Slice #1 (D-13) added advisory DB-size monitoring; this slice adds the first storage optimization: native TimescaleDB compression.

## Decision

### Native compression policy

Enable TimescaleDB native compression on `market.market_bars` with:

| Setting | Value |
|---------|-------|
| `compress` | `true` |
| `compress_segmentby` | `symbol, timeframe` |
| `compress_orderby` | `bar_open_time DESC` |
| `compress_after` | 7 days |

### Migration `0029_market_bars_compression`

- **upgrade**: `ALTER TABLE SET` + `add_compression_policy(if_not_exists)`
- **downgrade**: `remove_compression_policy` + decompress compressed chunks + `ALTER TABLE SET (compress=false)`
- **SQLite guard**: `if bind.dialect.name == "sqlite": return` — both directions are no-ops on SQLite (CI safety)
- **Idempotent**: `if_not_exists` on policy; `SET` is safe to repeat

### What this does NOT do

- No DELETE / drop_chunks / retention (future D-13 slice #3)
- No changes to `MarketBar` model, upsert path, or indexes
- No changes to execution / signal / reliability / scheduler code
- Live path is byte-identical (compression is transparent to reads)

## Consequences

- Old chunks (>7 days) are automatically compressed by the TSDB background worker
- Compression is transparent: reads work unchanged, upserts write to the newest uncompressed chunk
- Downgrade fully reverses: policy removed, compressed chunks decompressed, flag disabled
- The `uq_market_bar` unique constraint and `upsert_market_bars` path are unaffected (TSDB 2.27 supports DML on compressed hypertables via the uncompressed chunk window)
