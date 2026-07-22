# ADR-035: Advisory DB-Size Monitor (D-13 Slice #1)

## Status

Accepted (D-13 slice #1 implementation complete)

## Context

Market data tables (`market.market_bars`, hypertable) grow monotonically. There is no storage monitoring or retention policy. Unbounded growth risks disk exhaustion and operational surprise.

This slice adds **advisory monitoring only** — visibility into DB size with two severity bands. Retention, compression, and continuous aggregates are future D-13 slices (out of scope).

## Decision

### Two-band advisory monitor

| Band | Threshold (default) | Severity | Effect |
|------|---------------------|----------|--------|
| Warning | 5 GiB | `warning` | Overview-only; no audit emission |
| Critical | 10 GiB | `critical` | Flips `overall_status` → `degraded`; audit emitted on first transition |

### Default-OFF flag gate

`CLAY_DB_SIZE_MONITOR_ENABLED` (default `False`). When OFF:
- `pg_database_size()` is **never called**
- Reliability snapshot is **byte-identical** to pre-D-13
- No new audit events

### Configuration (env)

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAY_DB_SIZE_MONITOR_ENABLED` | `False` | Enable the monitor |
| `CLAY_DB_SIZE_WARNING_BYTES` | `5368709120` (5 GiB) | Warning threshold |
| `CLAY_DB_SIZE_CRITICAL_BYTES` | `10737418240` (10 GiB) | Critical threshold |

Validator: `critical_bytes > warning_bytes > 0`.

### Implementation

- **Settings:** `clay/settings/db_size.py` — `DbSizeMonitorSettings(BaseSettings)`, A6 DI pattern
- **Service:** `ReliabilityService._query_db_size(session)` — `SELECT pg_database_size(current_database())`
- **Trigger:** max 1 db-size trigger in `_build_degraded_triggers`; critical overrides warning
- **Recheck job:** 4th cache-tuple element `db_size_critical: bool` — detects healthy→degraded transition
- **Migrations:** None. Data untouched.

## Consequences

- Warning band is **overview-only**: visible in `/reliability/overview` but does NOT emit audit or flip `overall_status`. Documented as a slice limitation.
- Critical band emits `reliability.rechecked` audit **once per transition** (healthy→degraded or degraded→healthy). Steady-state emits nothing (B3b anti-flood).
- `pg_database_size` is PostgreSQL-only; SQLite tests mock `_query_db_size`.
- Future slices (D-13 #2+) will add retention/compression/continuous-aggregates and may add disk-free monitoring.
