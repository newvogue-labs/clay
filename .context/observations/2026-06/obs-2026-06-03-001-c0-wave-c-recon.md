---
date: 2026-06-03
type: recon
applies-to: [clay, c0, wave-c, hardening, pre-d, surface-mapping]
status: ratified — recon полный, 4 surfaces mapped, 5 open questions resolved by Emma
tags: [recon, c0, wave-c, hardening, db-idempotency, lifespan-httpx, asyncio-to-thread, ops-retention, risk-flags]
---

# obs-2026-06-03-001: C0 — Wave C (hardening) recon

## Scope

Read-only recon для Wave C = pre-D hardening, 4 surface'а. Закрывает HIGH-1 (TOCTOU), HIGH-2 (AsyncClient per call), MED-4 (session thread-safety). Готовит D (real-data rehearsal) без reactive firefighting.

**Baseline:** 249 pytest, 189 pyright (pre-existing test-fake debt), HEAD `0a78966` (post Wave B formally closed, post `0a78966` = .context updates).

## Surface 1 — DB idempotency (UniqueConstraint)

### Models

- `backend/src/clay/db/models_context.py:9-19` (NewsItem) и `:22-31` (SentimentSnapshot) — **схема `context`** (НЕ `ops` как ошибочно предполагалось в подготовке).
- Все 6 dedup-колонок **NOT NULL** (default): `source_name`, `headline`/`symbol`, `published_at`/`captured_at`. UNIQUE будет корректно работать (NULL-семантика не блокирует).
- `__table_args__ = {"schema": "context"}` — без `UniqueConstraint`, без FK.
- Миграция `0001_create_e2_ingestion_baseline.py:65-86` создаёт обе таблицы без constraint'ов. `0002`-`0008` не трогают `context.*`.

### App-level dedup

- `repositories_context.py:11-27` (`store_news_items`) — SELECT-then-skip key = `(source_name, headline, published_at)`.
- `repositories_context.py:29-45` (`store_sentiment_snapshots`) — key = `(source_name, symbol, captured_at)`.
- **Match с proposed UNIQUE keys: Y** — точно совпадают (per `obs-2026-06-02-006:38, :60`).

### Existing duplicates

- Test fixtures: ephemeral SQLite (`tests/conftest.py:14-15`), 1 INSERT per key, dedup-skip path **не покрыт явным тестом** (LOW-2 risk).
- Production: не проверено (read-only access не нужен после Emma Q1 — defensive dedup-cleanup в миграции).

### Hypertable status

- `news_items` / `sentiment_snapshots` — **НЕ hypertables**. Только `market.market_bars` / `orderbook_summaries` в `0002_convert_market_tables_to_hypertables.py:39, :49`.
- UNIQUE design = чистый B-tree, без Timescale partition-column ограничений.

## Surface 2 — lifespan-owned httpx.AsyncClient

### All call-sites

- **1 real construction:** `backend/src/clay/ingestion/market/binance_client.py:36` (else-ветка per call).
- News/sentiment connectors = demo (без httpx).
- `grep "import httpx" backend/src/clay/` = только `binance_client.py:4`.

### Wiring

- `BinanceSpotClient.__init__` (`binance_client.py:14`) — `client: httpx.AsyncClient | None = None` DI-параметр.
- `MarketIngestionService.__init__` (`ingestion/market/service.py:13`) — конструктор принимает `BinanceSpotClient`, не `AsyncClient`.
- `bootstrap.py:176` — `MarketIngestionService(BinanceSpotClient())` без `client=...` → prod-путь = else-ветка (per-call construction).
- `api/lifespan.py:55-64` — импортит singletons, **не создаёт** `AsyncClient`.

### Hot-loop math

- B5 scheduler: 60s interval × 2 symbols × 2 timeframes = **4 fetch_klines/мин = ~5,760 AsyncClient/день**.
- Connection pool churn + TLS handshake × N. **HIGH-2 risk.**

### Client config + lifecycle

- `timeout=10.0` per-request (`binance_client.py:30, :40`), нет global timeout, нет `Limits`, нет `headers`, нет `http2`, нет `base_url` на клиенте.
- `client.stream()` = 0 (non-streaming, B4.5 framing сохраняется — body buffer).
- `lifespan.py:96` `scheduler.start()`, `:97` `app.state.scheduler = scheduler`, `:108` `scheduler.shutdown(wait=True)` (в `finally`).
- **Shutdown race (MED-3):** `aclose()` ДО `shutdown(wait=True)` → in-flight `fetch_klines` → exception → noise audit. **Order: aclose() строго после shutdown return.**

## Surface 3 — asyncio.to_thread для sync-DB в job'ах

### Sync-DB call-sites внутри `_do_run_once`

- `MarketRepository.upsert_market_bars` (`repositories_market.py:13-60`) — `session.scalar`, `session.add`, `session.flush`.
- `MarketRepository.upsert_freshness_status` (`repositories_market.py:70-124`) — `session.scalar`, `session.add`, `session.flush` (×2).
- `ContextRepository.store_news_items` / `store_sentiment_snapshots` (`repositories_context.py:11-45`) — SELECT-skip + INSERT + flush.
- `OpsRepository.*` (`repositories_ops.py:15-106`) — `create_ingest_run`, `record_connector_status`, `record_source_health_event`, `finalize_ingest_run`, `resolve_source_health_events` — все sync.
- `session.commit()` — `ingestion/service.py:177` под `asyncio.Lock` (`ingestion/service.py:145`).

### Session lifecycle

- Session создаётся в `IngestionCycleJob.run` (`scheduler/jobs.py:391`) — `with self._session_factory() as session:`.
- `with`-block держит session до `:402-410` (включая `await service.run_once(session, ...)` на `:393`).
- **Session НЕ передаётся между threads** — `to_thread` должен обернуть **весь sync block** (SELECT+INSERT+flush+commit) в одном вызове.
- `asyncio.Lock` scope сохраняется: `to_thread` внутри lock.

### Scope check (C3 релевантность)

- Health-tick (B3b) + reliability-recheck (B4) — sync `_run_safely` → `executor="default"` (ThreadPoolExecutor 4 workers, `scheduler/service.py:144, :217, :272`). **ВНЕ event loop** → `asyncio.to_thread` НЕ применим.
- `asyncio.to_thread` matters **ONLY** для async `ingestion-cycle` job (`scheduler/service.py:343`: `func=self._arun_safely`).

## Surface 4 — ops.* retention/rotation

### ops.* inventory (9 таблиц, `schema="ops"`)

**Growing (append-only):**
1. `ops.ingest_runs` (`models_ops.py:10-20`) — **growing** (per `create_ingest_run`).
2. `ops.connector_status_history` (`models_ops.py:23-32`) — **growing** (per `record_connector_status`).
3. `ops.source_health_events` (`models_ops.py:35-46`) — **growing** (только на errors; UPDATE-in-place при `resolve`).

**Singletons** (`id=1`, `CheckConstraint("id = 1")`):
4. `ops.ai_control_state` (`models_ops.py:72-84`)
5. `ops.session_state` (`models_ops.py:87-104`)
6. `ops.workspace_focus` (`models_ops.py:107-118`)
7. `ops.strategy_state` (`models_ops.py:121-130`)
8. `ops.reliability_state` (`models_ops.py:133-141`)

**Bounded** (PK = `role_id`):
9. `ops.ai_assignments` (`models_ops.py:63-69`) — ~5-10 строк.

### 43k/month — это округлённая цифра

- Реальный rate: `ops.ingest_runs` ~130k/мес (60s × 3 ingest_run/cycle × 1440/день × 30), `ops.connector_status_history` ~86k/мес.
- `ops.source_health_events` — растёт только на errors (steady ≈ 0).

### Audit = FILE, не DB

- `backend/src/clay/audit/writer.py:1-20` — `self.path = state_dir / "audit.jsonl"`.
- `write(...)` (`audit/writer.py:19-20`): `with self.path.open("a", ...): handle.write(json.dumps(event) + "\n")`.
- **Нет `AuditEvent` ORM-модели** (`grep "class AuditEvent"` = 0 matches в `src/clay/`).
- **Rotation:** нет. Append-only без ротации (per `state.md:39` backlog).
- **Implication:** `ops.*` retention (DB prune) ≠ audit rotation (file rotation). **Раздельные backlog items.**

### Hypertable check

- `ops.*` — **НЕ hypertables**. Только `market.*` в `0002`.
- `add_retention_policy` / `drop_chunks` неприменим без миграции hypertable-конверсии (отдельный проект).

## 🚩 Risk Flags

### 🔴 HIGH-1 — TOCTOU SELECT-skip ↔ INSERT (no DB-level UniqueConstraint)

- `repositories_context.py:14-23, 32-41` — race possible.
- Mitigated: `asyncio.Lock` (`ingestion/service.py:113, :145`) + single-worker assumption (`scheduler/service.py:43-47`).
- Defense-in-depth отсутствует. **Закрывается C1.**

### 🔴 HIGH-2 — AsyncClient per call в hot loop

- `binance_client.py:36` — new client per `fetch_klines`.
- ~5,760/день в prod. Connection pool churn + TLS handshake × N.
- **Закрывается C2.**

### 🟡 MED-3 — Shutdown race (client.aclose vs in-flight job)

- `aclose()` ДО `scheduler.shutdown(wait=True)` → in-flight job exception → noise audit на shutdown.
- **Order: aclose() строго после shutdown return.** **Закрывается C2.**

### 🟡 MED-4 — Session thread-safety при to_thread

- `to_thread` должен обернуть **весь sync block** в одном вызове (session не thread-safe).
- `asyncio.Lock` scope сохраняется: `to_thread` внутри lock.
- **Закрывается C3.**

### 🟡 MED-5 — Audit rotation ≠ ops.* retention

- File rotation (`audit.jsonl`) — отдельный backlog item (out of Wave C scope).
- C4 retention = DB prune для `ops.ingest_runs` / `connector_status_history` / `source_health_events`.

### 🟢 LOW-1 — No persistent test duplicates (миграция не блокируется)

- Empty CREATE UNIQUE INDEX path verified.
- Production DB — defensive dedup-cleanup идемпотентно (Emma Q1 решение).

### 🟢 LOW-2 — Demo connectors bypass dedup (`published_at = now()`)

- `demo_news.py:27` / `demo_sentiment.py:27` — всегда свежий timestamp.
- SELECT-skip branch не покрыт явным тестом. **C1 acceptance добавит test.**

### 🟢 LOW-3 — 43k/month figure approximate

- Реально ~130k ops.ingest_runs + ~86k connector_status_history в месяц.
- C4 retention design учитывает реальный rate.

## Open questions (resolved by Emma 2026-06-03)

1. **Q1 prod dup-check** → defensive dedup-cleanup в миграции (idempotent).
2. **Q2 `ingest_runs` retention window** → 30d (operational telemetry, not business data).
3. **Q3 httpx DI path** → hybrid (a)+(b): lifespan-owned client + late-binding setter (`service.set_http_client(client)`) ДО `scheduler.start()`, тот же client на `app.state.httpx_client` для route.
4. **Q4 hypertable conversion** → **НЕ в Wave C** (отдельный проект post-MVP).
5. **Q5 CI test path** → (a) APScheduler prune → SQLite `DELETE WHERE`, vendor-neutral, no docker-compose PG.

## Wave C decomposition (final)

| Slice | Что | Закрывает | pytest delta |
|---|---|---|---|
| **C1** | DB `UniqueConstraint` (idempotency) + repo IntegrityError handling | HIGH-1 | +N small (constraint test + dedup-skip test) |
| **C2** | lifespan-owned `httpx.AsyncClient` | HIGH-2 + MED-3 | +N small (lifespan integration test) |
| **C3** | `asyncio.to_thread` для sync-DB в ingestion-job | MED-4 | +N small (race test + budget test) |
| **C4** *(severable tail)* | `ops.*` retention prune | MED-5 partial | +N small (prune test) |

Order: idempotency (low blast) → hot-loop client → to_thread → retention (отрезаемый хвост, можно стартовать D раньше).

## How to apply

- C1 plan: см. `.context/handoffs/current.md` (после Emma approve C1 plan)
- Recon-данные immutable references для всех 4 surface'ов в этом файле
- C4 retention windows: `clay/retention/jobs.py:1-9` (existing constants — sanity-check `ingest_runs` отсутствие)
- Audit rotation = separate slice (out of C scope)
- Все 4 surface'а — defensive, не блокеры, не меняют публичные API
