# Clay

Your own trading workspace. Signals, review, and control.

## Current Status

This repository is the implementation workspace for `Clay`.

At the moment:

- the architecture and planning phase are complete;
- implementation starts here;
- the first delivery target is `Wave 1`:
- `E1` runtime foundation
- `E2` data ingestion and local historical store
- `E3` trading workspace and live signal surface
- `E4` control center and runtime operations
- `E5` AI roles, orchestration, and model assignment
- `E6` signal lifecycle, ranking, and risk-control

## E1 Progress

The current implementation already includes:

- runtime states and controlled transitions;
- XDG-aware config loading with validation and rollback;
- service registry and safe lifecycle actions;
- preflight checks and audit trail scaffolding;
- backend control API for runtime, services, configs, and health;
- minimal React shell wired to live backend data.

## E2 Progress

The current `E2` backend slice already includes:

- ingestion settings and DB bootstrap contracts;
- ORM schema baseline for `market`, `context`, and `ops`;
- Alembic migration skeleton for the first ingestion baseline;
- market normalization contracts for Binance Spot klines;
- pluggable demo connectors for news and sentiment;
- freshness and retention helpers;
- storage-backed repositories for market/context/ops domains;
- orchestration flow for a full ingest cycle;
- downstream backend routes backed by persisted data instead of demo payloads.

## E4 Progress

The current `E4` slice already includes:

- a backend `Control Center` aggregator over runtime, services, ingest health, incidents, audit, and configs;
- `GET /control-center/overview` for operator snapshots;
- `GET /control-center/stream` for live UI refresh triggers over `SSE`;
- audit and live event publishing for manual ingestion runs;
- a frontend `Control Center` shell with runtime transitions, manual ingest trigger, service actions, incident/audit view, and config restore actions.

## E3 Progress

The current `E3` slice already includes:

- a storage-backed backend workspace service built on top of `E1 + E2 + E4`;
- `GET /workspace/trading` for the main trading workspace snapshot;
- `GET /workspace/trading/focus` and `POST /workspace/trading/focus` for pair and signal focus control;
- `GET /workspace/trading/stream` for live refresh triggers over `SSE`;
- a frontend `Trading Workspace` with focused pair context, active signals, monitoring pool, reasoning, risk, and news/sentiment panels;
- live focus switching between ranked signals and monitoring candidates without direct browser access to provider data.

## E5 Progress

The current `E5` slice already includes:

- a backend `AI Control` registry for roles, model versions, assignments, conflicts, and fallback posture;
- `GET /ai-control/overview` for the current orchestration snapshot;
- `POST /ai-control/assignments/review` and `POST /ai-control/assignments/apply` for operator-reviewed assignment changes;
- `GET /ai-control/stream` for live refresh triggers over `SSE`;
- a frontend `AI Control` surface with assignment review, conflict visibility, fallback status, and explicit apply flow;
- audit/event publication for reviewed model assignment changes instead of silent switching.

## E6 Progress

The current `E6` slice already includes:

- a backend `signal_engine` domain for lifecycle, ranking, confidence penalties, response actions, and strategy-mode proposals;
- `GET /signals/overview` for the current evaluated signal bundle;
- risk triggers for stale data, thin context, AI conflicts, runtime degradation, and expired decision windows;
- `Trading Workspace` wired to signal-engine truth instead of inline heuristic ranking;
- frontend risk/signal panels that now expose confidence penalties, response actions, strategy mode, and visible triggers.

## Repository Layout

- `backend/` — future backend application and runtime services
- `frontend/` — future web UI application
- `docs/planning/` — imported planning source documents needed during implementation
- `scripts/` — helper scripts for local development and repo automation

## Planning Source

The most important planning references live in `docs/planning/`:

- `blueprint-v1.md`
- `tech-stack-v1.md`
- `execution-backlog-v1.md`
- `master-planning-review-v1.md`

Implementation should follow those documents rather than reinvent system boundaries during coding.

## Bootstrap Commands

Backend:

```bash
make backend-install
make backend-test
make backend-run
cd backend && uv run alembic upgrade head
```

Frontend:

```bash
make frontend-install
make frontend-test
make frontend-build
make frontend-run
```

## Local Environment

Copy `.env.example` if you want to override defaults for local development.

- `CLAY_API_HOST` and `CLAY_API_PORT` define the backend bind address.
- `CLAY_DATABASE_URL` defines the PostgreSQL/TimescaleDB connection used by `E2`.
- `VITE_CLAY_API_BASE_URL` defines which backend URL the frontend shell calls.

## E2 Notes

- `E2` expects PostgreSQL with TimescaleDB available before running real migrations.
- test coverage uses SQLite with schema translation, while runtime remains targeted at PostgreSQL/TimescaleDB.
- Current `E2` routes:
  - `GET /ingestion/health`
  - `POST /ingestion/run`
  - `GET /market-data/bars/latest`
  - `GET /context-data/summary`
  - `GET /shortlist/metrics`

## E4 Notes

- `Control Center` is intentionally operator-facing and not a substitute for the future `Trading Workspace`.
- Current `E4` routes:
  - `GET /control-center/overview`
  - `GET /control-center/stream`
- operator commands still flow through the existing runtime, services, configs, and ingestion endpoints.

## E3 Notes

- `Trading Workspace` is the analyst-facing layer and intentionally separate from `Control Center`.
- Current `E3` routes:
  - `GET /workspace/trading`
  - `GET /workspace/trading/focus`
  - `POST /workspace/trading/focus`
  - `GET /workspace/trading/stream`
- current focus logic is derived from persisted `E2` data and current control-plane state; no browser-side market/provider calls are used.

## E5 Notes

- `AI Control` is the operator-facing orchestration layer for roles and model assignments, not a hidden auto-router.
- Current `E5` routes:
  - `GET /ai-control/overview`
  - `POST /ai-control/assignments/review`
  - `POST /ai-control/assignments/apply`
  - `GET /ai-control/stream`
- assignment changes require an explicit review/apply flow; silent switching is intentionally blocked by design.

## E6 Notes

- `signal_engine` is the source of truth for signal state, ranking, and risk semantics.
- Current `E6` routes:
  - `GET /signals/overview`
- `Trading Workspace` consumes evaluated signal truth from the backend instead of inventing ranking/risk behavior in the UI layer.
