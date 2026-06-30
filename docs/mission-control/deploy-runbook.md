# Clay — Deploy Runbook

> Status: MVP-ready (MVP-polish closed 2026-06-04). Companion to ADR-007
> (scheduler lifecycle) and ADR-009 (retention policy).

## 1. Architecture constraints (read first)

- **Single-worker only** (ADR-007). The APScheduler `AsyncIOScheduler` runs
  in-process inside the FastAPI `lifespan`. Multiple workers would spawn
  duplicate schedulers → duplicate ingestion/retention jobs. The prod
  entrypoint enforces `workers=1`; never override it.
- **No `--reload` in prod** (reload spawns a reloader subprocess → second
  scheduler).
- **Egress requires the v2rayN TUN egress node.** Direct egress from RU fails;
  exchange traffic must route through the TUN tunnel (see §6).

## 2. Prerequisites

- Python (project venv, `uv sync`).
- PostgreSQL reachable via `CLAY_DATABASE_URL`.
- v2rayN TUN egress node up (for live ingestion).

## 3. Launch

```bash
# Production (single-worker, no reload):
python -m clay
# → uvicorn.run("clay.api.main:app",
#       host=CLAY_SERVER_HOST, port=CLAY_SERVER_PORT,
#       workers=1, reload=False)

# Equivalent explicit form:
uvicorn clay.api.main:app --host 0.0.0.0 --port 8000 --workers 1

# Development (auto-reload, loopback):
make backend-run   # uvicorn --reload on 127.0.0.1:8000
```

Defaults: `CLAY_SERVER_HOST=127.0.0.1`, `CLAY_SERVER_PORT=8000`.

## 4. Database migration

```bash
alembic upgrade head   # current head: 0021
```

Canonical DB = TimescaleDB on `:5433` (dev `clay`); alembic head **`0021`**. The
`:5432` instance is a **broken spare — not** the source of truth (do not migrate
against it). Earlier `0011` added the retention time-indexes
(`ingest_runs.started_at`, `connector_status_history.observed_at`,
`source_health_events.recorded_at`); the chain has since advanced to `0021`.
Migrations run on PostgreSQL (the full alembic chain is not SQLite-compatible —
`0001` uses `CREATE SCHEMA` + timescaledb extension).

## 5. Environment matrix (`CLAY_*`)

| Variable | Purpose | Default |
|---|---|---|
| `CLAY_DATABASE_URL` | Postgres DSN | — (required) |
| `CLAY_BINANCE_BASE_URL` | Binance base URL (route via TUN egress node; testnet: `https://testnet.binance.vision`) | `https://api.binance.com` |
| `CLAY_EXECUTION_MODE` | Execution gate mode (`dry_run` / `testnet` / `live`). Env alone does **not** arm live — confirm-override + Q5 still required (D2 / ADR-025). | `dry_run` |
| `CLAY_SERVER_HOST` | Bind host | `127.0.0.1` |
| `CLAY_SERVER_PORT` | Bind port | `8000` |
| `CLAY_SCHEDULER_ENABLED` | Master scheduler gate | `true` |
| `CLAY_SCHEDULER_RELIABILITY_ENABLED` | Reliability recheck job | `true` |
| `CLAY_SCHEDULER_INGESTION_ENABLED` | Ingestion cycle job | `true` |
| `CLAY_SCHEDULER_OPS_RETENTION_ENABLED` | Ops retention prune job | `true` |
| `CLAY_SCHEDULER_AI_AGENT_ENABLED` | AI-agent cycle job (opt-in) | `false` |
| `CLAY_SCHEDULER_PROVIDER_POOL_RECONCILE_ENABLED` | Provider-pool reconcile job (opt-in) | `false` |
| `CLAY_SCHEDULER_HEALTH_TICK_INTERVAL_SECONDS` | Health heartbeat | `30` |
| `CLAY_SCHEDULER_HEALTH_STALE_AFTER_SECONDS` | Health stale threshold | `60` |
| `CLAY_SCHEDULER_RELIABILITY_RECHECK_INTERVAL_SECONDS` | Reliability cadence | `300` |
| `CLAY_SCHEDULER_INGESTION_CYCLE_INTERVAL_SECONDS` | Ingestion cadence | `60` |
| `CLAY_SCHEDULER_OPS_RETENTION_INTERVAL_SECONDS` | Retention cadence | `86400` |
| `CLAY_SCHEDULER_READINESS_STALE_THRESHOLD_SECONDS` | Readiness ingest-freshness gate | `120` |
| `CLAY_MARKET_FETCH_LIMIT` | klines limit per request | `200` |
| `CLAY_MARKET_FETCH_TIMEOUT` | httpx timeout | `10.0` |
| `CLAY_MARKET_LIMITS_MAX_CONNECTIONS` | httpx pool max connections | `20` |
| `CLAY_MARKET_LIMITS_MAX_KEEPALIVE` | httpx pool max keepalive | `10` |
| `CLAY_MARKET_FRESHNESS_5M_MINUTES` | 5m bar freshness threshold | `10` |
| `CLAY_MARKET_FRESHNESS_15M_MINUTES` | 15m bar freshness threshold | `25` |
| `CLAY_MARKET_FRESHNESS_1H_MINUTES` | 1h bar freshness threshold | `80` |
| `CLAY_CONTEXT_FRESHNESS_NEWS_HOURS` | News freshness threshold | `8` |
| `CLAY_CONTEXT_FRESHNESS_SENTIMENT_HOURS` | Sentiment freshness threshold | `4` |

> Note: scheduler-cadence env names follow the codebase prefix `CLAY_SCHEDULER_*`;
> confirm exact suffixes against `settings/scheduler.py` before templating.

> Scheduler registers **4 jobs by default** (health-tick · reliability · ingestion ·
> ops-retention) and **0 trade-executing jobs**. Two further jobs are **opt-in** and
> silently skipped unless enabled: ai-agent cycle (`CLAY_SCHEDULER_AI_AGENT_ENABLED`)
> and provider-pool reconcile (`CLAY_SCHEDULER_PROVIDER_POOL_RECONCILE_ENABLED`).

## 6. Health & readiness probes

- **`GET /health`** — liveness. Always `{"status":"ok"}` (stateless, byte-identical
  to pre-MP2). Use for "is the process up" / restart decisions.
- **`GET /health/ready`** — readiness. Body:
  `{"status":"healthy"|"degraded","checks":{...}}`. Tiered, flag-aware,
  startup-grace:

  | Signal | 200 | 503 | Notes |
  |---|---|---|---|
  | DB-ping | `"ok"` | `"down"` | HARD gate — always 503 on failure |
  | Scheduler | `"running"` / `"disabled"` | `"stopped"` | flag-aware: disabled-by-flag ≠ failure |
  | Ingest freshness | `"ok"` / `"warming_up"` / `"disabled"` | `"stale"` | grace on fresh boot; only stale-while-enabled 503s |

  **Probe wiring:** point your orchestrator's *liveness* probe at `/health`
  and its *readiness* probe at `/health/ready`. Readiness performs no network
  egress (DB ping + in-memory scheduler state + one indexed SELECT).

## 7. Egress caveat 🔴

`CLAY_BINANCE_BASE_URL` (and the second exchange) must route through the v2rayN
TUN egress node. When the TUN is down, httpx raises
`ConnectError` / `TimeoutError`. This is **expected, loud, logged behavior**, not
a bug: per-attempt `logger.warning`, final `logger.error` after retry exhaustion
(MP4 logging). There is no silent fallback by design. Symptom in `/health/ready`:
ingest freshness goes `stale` (503) once the threshold passes while ingestion is
enabled.

> **Egress IP/region is point-in-time** and rotates with operator config (observed:
> DE `45.157.232.164`, later Paris `83.136.209.168`). The authoritative current
> egress node lives in `runbooks/runbook-003` (kill-switch / egress) — **do not
> hard-code an IP here**.

## 8. Operational notes

- Manual ingestion override: `POST /ingestion/run` (409 if a cycle is already
  running). Scheduler-driven cycles skip+log on overlap.
- Retention prunes 3 ops tables (`ingest_runs` 30d, `connector_status_history`
  180d, `source_health_events` 180d). `market_bars` / `context.*` are out of
  scope (separate product decision). `audit.jsonl` rotation is not handled
  (backlog).

## 9. Out of scope / backlog

- Dockerfile / docker-compose (containerization) — backlog, not an MVP blocker.
- Multi-worker / leader-election — out of scope (single-worker by design).
- `audit.jsonl` file rotation — backlog.
