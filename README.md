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
- `E7` session lifecycle, briefing, pause, and pair replacement
- `E8` demo trading integration and result tracking
- `E9` audit trail, feedback, and session review
- `E10` knowledge base and research layer
- `E11` backtesting, replay, and model/strategy activation
- `E12` reliability, degraded mode, and release readiness

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

## E7 Progress

The current `E7` slice already includes:

- a backend `session_control` domain for hard preflight, briefing, lifecycle actions, and pair replacement review;
- `GET /session/overview` plus lifecycle routes for `start`, `pause`, `resume`, and `complete`;
- pair replacement review/apply flow with audit/event publication instead of silent focus switching;
- `GET /session/stream` for live session refresh events over `SSE`;
- a frontend `Session Control` surface with preflight, briefing, lifecycle actions, and pair replacement review/apply.

## E8 Progress

The current `E8` slice already includes:

- a backend `demo_trading` domain for manual demo action logging, result ingest, and readiness evaluation;
- persisted `demo.demo_trade_records` storage with Alembic migration support;
- `GET /demo-trading/overview`, `POST /demo-trading/log-current`, and `POST /demo-trading/results/ingest`;
- `GET /demo-trading/stream` for live refresh events over `SSE`;
- a frontend `Demo Validation` surface with readiness gates, manual action logging, and result tracking;
- explicit outcome classification for `matched`, `missed`, `late_matched`, `mismatched`, and `unresolved`.

## E9 Progress

The current `E9` slice already includes:

- a backend `session_review` domain over audit history, demo outcomes, and operator feedback;
- persisted `review.signal_feedback` storage with Alembic migration support;
- `GET /session-review/overview` and `POST /session-review/feedback`;
- `GET /session-review/stream` for live refresh events over `SSE`;
- a frontend `Session Review` surface with review summary, filters, reviewed signals, feedback capture, and AI-assisted review cards.

## E10 Progress

The current `E10` slice already includes:

- a backend `knowledge` domain for light-mode storage, semantic-ish chunking, and advisory retrieval;
- persisted `knowledge.knowledge_items` and `knowledge.knowledge_chunks` storage with Alembic migration support;
- `GET /knowledge/overview` and `POST /knowledge/items`;
- `GET /knowledge/stream` for live refresh events over `SSE`;
- a frontend `Knowledge Base` surface with quick-ingest, research search, recent items, and retrieval results;
- an explicit policy that knowledge retrieval is advisory only and not part of the realtime signal hot path.

## E11 Progress

The current `E11` slice already includes:

- a backend `validation_lab` domain for replay runs, validation summaries, staged activation review, and explicit apply flow;
- persisted `validation.validation_runs` and `validation.activation_reviews` storage with Alembic migration support;
- `GET /validation-lab/overview`, `POST /validation-lab/runs`, `POST /validation-lab/activation/review`, and `POST /validation-lab/activation/apply`;
- `GET /validation-lab/stream` for live refresh events over `SSE`;
- a frontend `Validation Lab` surface with replay actions, run history, review cards, and operator-confirmed activation apply;
- an explicit policy that strategy/model activation must pass through replay evidence instead of silent switching.

## E12 Progress

The current `E12` slice already includes:

- a backend `reliability` domain that aggregates runtime, ingest, AI fallback, demo readiness, review evidence, and validation posture;
- `GET /reliability/overview` and `POST /reliability/recheck`;
- `GET /reliability/stream` for live refresh events over `SSE`;
- a frontend `Reliability Center` with degraded triggers, fallback posture, readiness checks, release gates, and incident review;
- explicit release-readiness statuses of `blocked`, `needs_attention`, and `ready_for_demo`;
- visible reliability gates instead of silent “looks fine to me” assumptions.

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

## E7 Notes

- `session_control` is the discipline layer for starting, pausing, resuming, reviewing, and completing a session.
- Current `E7` routes:
  - `GET /session/overview`
  - `POST /session/start`
  - `POST /session/pause`
  - `POST /session/resume`
  - `POST /session/complete`
  - `POST /session/replacement/review`
  - `POST /session/replacement/apply`
  - `GET /session/stream`
- session transitions stay explicit and operator-confirmed; pair replacement cannot happen silently.

## E8 Notes

- `Demo Validation` is still manual-first: the operator executes trades externally and `Clay` records the intent/result relationship.
- Current `E8` routes:
  - `GET /demo-trading/overview`
  - `POST /demo-trading/log-current`
  - `POST /demo-trading/results/ingest`
  - `GET /demo-trading/stream`
- the readiness gate stays conservative: fewer than five sessions keeps the stage in `collecting`, while unresolved or mismatched records keep it `at_risk`.

## E9 Notes

- `Session Review` turns demo evidence into an operator-facing review loop instead of leaving it as raw logs.
- Current `E9` routes:
  - `GET /session-review/overview`
  - `POST /session-review/feedback`
  - `GET /session-review/stream`
- AI-assisted review stays advisory only; strategy/model changes still require explicit confirmation.

## E10 Notes

- `Knowledge Base` in `v1` is a light mode for notes, strategy rules, checklists, and observations.
- Current `E10` routes:
  - `GET /knowledge/overview`
  - `POST /knowledge/items`
  - `GET /knowledge/stream`
- retrieval is intentionally advisory and must not block signal ranking, session start, or demo validation flows.

## E11 Notes

- `Validation Lab` is the staged validation layer between observed behavior and any strategy/model activation.
- Current `E11` routes:
  - `GET /validation-lab/overview`
  - `POST /validation-lab/runs`
  - `POST /validation-lab/activation/review`
  - `POST /validation-lab/activation/apply`
  - `GET /validation-lab/stream`
- activation remains explicit and operator-confirmed; replay evidence can return `ready`, `staged`, or `blocked` posture before apply.

## E12 Notes

- `Reliability Center` is the final Wave 1 discipline layer for degraded mode visibility, readiness checks, and release gates.
- Current `E12` routes:
  - `GET /reliability/overview`
  - `POST /reliability/recheck`
  - `GET /reliability/stream`
- release gates remain operator-facing and explicit; a visible warning is better than a silent “probably stable” fairy tale.
