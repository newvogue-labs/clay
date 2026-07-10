---
tags:
  - ops
---

# ADR-023: ops.ai_agent_runs — Indexes + Retention Policy

- **Status:** Accepted
- **Date:** 2026-06-24
- **Replaces:** —
- **Driver:** Ф1b

## Context

`ops.ai_agent_runs` stores one row per `AgentRunner.run_agent` turn (~4 roles × 300s interval → ~1 150 rows/day projected). The table has:

- **No indexes** beyond PK on `id`.
- **No retention** → unbounded linear growth (~600 MB/year).
- **Two hot query patterns** that scan the full table without index support:
  1. RPD budget check: `WHERE model_id = ? AND created_at >= today` (called before every session start).
  2. Latest run per role + per-role error stats: `WHERE role_id IN (?) ... ORDER BY created_at DESC`.

Neither pattern is IO-critical at current volume (223 rows, 328 kB), but latency will degrade as the table grows.

## Decision

### Indexes (migration 0019)

Two targeted btree indexes, no over-indexing:

| ID | Columns | Purpose |
|----|---------|---------|
| I1 | `(role_id, created_at DESC)` | Latest-run fetch (pat. 2), per-role error stats (pat. 3) |
| I2 | `(model_id, created_at DESC)` | RPD budget hot-path (pat. 1) |

Plain `CREATE INDEX IF NOT EXISTS` — the table has 223 rows, no lock concern.

### Retention

- **Horizon:** 180 days (consistent with `connector_status_history` / `source_health_events`).
- **Mechanism:** DELETE job in existing `OpsRetentionJob` (scheduler/jobs.py), which already handles 3 sibling tables.
- **Config key:** `"ai_agent_runs": 180` in `RETENTION_WINDOWS_DAYS`.
- **Not hypertable** → `drop_chunks` unavailable. DELETE is adequate at this volume.

## Consequences

- ✅ I1 covers latest-run and per-role stats without sequential scan.
- ✅ I2 makes RPD budget check a single index-only scan per model.
- ✅ Retention keeps annual storage under ~300 MB.
- ⚠️ **Retention is an operational audit buffer, NOT a release-gate dependency.** No release gate (`review-evidence`, `validation-gate`, `demo-discipline`) reads `ai_agent_runs`. Losing old rows affects debugging/historical analysis only.
- ⚠️ 180-day DELETE is irreversible. Historical data beyond the horizon is permanently lost.
- ⚠️ Delete job runs in-band with `OpsRetentionJob` on scheduler tick. Workload is negligible (< 1 150 rows/tick).
