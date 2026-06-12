---
date: 2026-06-02
type: recon
applies-to: [clay, b5, scheduler, ingestion]
status: ratified — [HIGH] flags pending Emma + architect decision
tags: [recon, b5, ingestion-cycle, scheduler, concurrency, emit-gating, side-effects, protocol]
---

# obs-2026-06-02-005: B5 recon — IngestionCycleJob (run_cycle side-effect profile)

## Scope

Read-only recon на 11 файлах в `backend/src/clay/ingestion/`, `backend/src/clay/api/routes/ingestion.py`, `backend/src/clay/bootstrap.py`, `backend/src/clay/settings/scheduler.py`, `backend/src/clay/scheduler/` (A6 invariant check), `backend/src/clay/audit/`, `backend/src/clay/events/`, `backend/src/clay/db/repositories_market.py`, `backend/tests/ingestion/test_ingestion_cycle.py`. Цель — подтвердить 6 пунктов Emma + flag risks ДО B5 plan-фазы.

## 6-point verdict

### П.1 — `run_once()` signature & end-to-end

- **Сигнатура:** `async def run_once(self, session: Session) -> IngestionRunSummary` — `ingestion/service.py:53`
- **Class:** `IngestionCycleService` (`ingestion/service.py:41-51`), DI через `bootstrap.py:181-185`
- **Pipeline (sequential, single event loop):**
  1. `MarketRepository / ContextRepository / OpsRepository(session)` — `service.py:60-62`
  2. `_run_market_ingest()` — `service.py:64-68` (async, см. ниже)
  3. `_run_context_ingest()` — `service.py:69-73` (async, см. ниже)
  4. `session.commit()` — `service.py:76` (**final commit внутри метода**)
  5. `return summary` — `service.py:77`
- **Market sub-pipeline (`_run_market_ingest`, `service.py:79-177`):**
  - Guard: skip если `not self.settings.binance_spot_enabled` — `service.py:86-87`
  - `ops_repo.create_ingest_run(source="binance_spot", source_type="market", status="running", ...)` — `service.py:90-99` → **+1 row в `ops.ingest_run` на каждый вызов**
  - Цикл `for symbol in market_symbols: for timeframe in market_timeframes:` — `service.py:103-104`
  - Внутри цикла (per `(symbol, timeframe)`):
    - `_fetch_market_bars` с retry — `service.py:106-109` + `service.py:257-278` (max `market_fetch_max_attempts=2`, delay `0.5s` — `settings/ingestion.py:21-22`)
    - `market_service.persist_bars(market_repo, bars)` — `service.py:110` (см. П.2)
    - `evaluate_market_freshness(...)` → `upsert_freshness_status(...)` — `service.py:117-129` (см. П.2)
    - `ops_repo.resolve_source_health_events(...)` на success — `service.py:130-134`
  - На exception: `summary.incidents.append(...)` + `record_source_health_event(...)` + `upsert_freshness_status(..., "unknown", is_stale=True)` — `service.py:136-160` (broad `except Exception`, **без re-raise**)
  - `ops_repo.finalize_ingest_run(market_run, status, ...)` — `service.py:169-177` → **+1 row update**
- **Context sub-pipeline (`_run_context_ingest`, `service.py:179-255`):**
  - `await self.context_manager.run_once()` — `service.py:186` (fan-out по всем `ContextConnector`-ам, включая disabled-skip, см. `context/manager.py:26-73`)
  - Per result: `ops_repo.create_ingest_run` + `record_connector_status` + `store_news_items` (если news) / `store_sentiment_snapshots` (если sentiment) + финальный `finalize_ingest_run` + (если error/degraded) `record_source_health_event` — `service.py:188-255`
- **Возвращает:** `IngestionRunSummary` dataclass (`service.py:17-38`) с counters + список incidents + `as_payload()` для audit
- **Side-effects в `run_once`:** DB writes (bars, freshness, ingest_run, source_health, connector_status, news, sentiment) + in-memory mutation `summary`. **Audit/event НЕ пишет** (см. П.3) — это делает route.

### П.2 — Idempotency

- **`upsert_market_bars` — idempotent (yes, app-level + DB safety net):** `repositories_market.py:13-48`
  - Логика: `SELECT existing by (symbol, timeframe, bar_open_time)` → если None → INSERT, иначе UPDATE existing в `service.py:33-44`
  - **DB safety-net:** `UniqueConstraint("symbol", "timeframe", "bar_open_time", name="uq_market_bar")` в `db/models_market.py:12` — спасает от race-duplicates
  - **Но** `written += 1` ВСЕГДА, и на INSERT, и на UPDATE (`repositories_market.py:30` и `repositories_market.py:45`) → `summary.market_records_written` **лжёт на повторе**: пишет `4` даже когда все 4 строки уже были и просто обновились. Не блокер, но **важно для П.3 (emit-gating)** — поле `market_records_written` не различает "новое" и "обновлённое"
- **`upsert_freshness_status` — idempotent (yes, app-level):** `repositories_market.py:58-91`
  - Логика: SELECT by `(symbol, timeframe)` → None → INSERT, иначе UPDATE полей
  - **DB safety-net:** `UniqueConstraint("symbol", "timeframe", name="uq_market_freshness_status")` в `db/models_market.py:55` — спасает от race
- **`store_news_items` / `store_sentiment_snapshots` — НЕ проверял глубоко** (в `repositories_context`), но контекст-fetch через `ContextConnector.fetch()` возвращает **fresh payloads каждый раз** (нет unique-constraint в моделях видимо). Это [HIGH] — потенциальный duplicate news/sentiment при повторе. **Требует pre-flight recon `repositories_context.py` ДО B5 plan-фазы**, не блокер B5 plan-формы, но флагуй.
- **Поведение при повторе `run_once()` с теми же данными (тик 2, 3, 4...):**
  - **DB дубликатов не будет** (unique constraints + app-level upsert)
  - **`ops.ingest_run` будет расти** на 1+1+1+... строк каждый тик (нет de-dup) → **150+ rows в час при 60s interval**
  - **`ops.connector_status` будет расти** аналогично (нет de-dup)
  - **`summary.market_records_written` будет `4` каждый раз** (UPDATE counts как write) → нельзя использовать как "is there new data" signal
  - **Network:** Binance `fetch_klines` будет вызван с `limit=200` каждый тик → 4 (symbols) × 4 (timeframes) = 16 HTTP-запросов каждые 60s, даже если новых баров 1-2

### П.3 — Side-effects / audit / event per call

- **Audit verbs per call: ZERO в `run_once`.** Audit пишется **только вручную** в route `routes/ingestion.py:129`:
  - `audit_writer.write("ingestion.run", payload)` — ровно **1 verb на ручной вызов**
  - **Scheduler-driven `run_once()` ничего не audit'ит сам по себе** → job ОБЯЗАН сам вызвать `audit_writer.write` после `run_once()`
- **EventBus events per call: ZERO в `run_once`.** Event публикуется **только вручную** в route `routes/ingestion.py:130`:
  - `event_bus.publish("ingestion.updated", payload)` — ровно **1 event на ручной вызов**
  - **Scheduler-driven `run_once()` ничего не публикует** → job ОБЯЗАН сам вызвать `event_bus.publish` после `run_once()`
- **Применимость B4 Option B (`emit: bool` flag):**
  - **B4 pattern (anti-flood, transition-only):** ⛔ **НЕ применим как есть**. У `ReliabilityRecheckJob` (`scheduler/jobs.py:149-243`) anti-flood осмысленный потому что `release_readiness_status` редко меняется. У `IngestionCycleJob` каждый тик = новая попытка fetch + новые DB writes → emit-on-every-run **легитимен по природе домена**
  - **B4 signature refactor (refactor `run_once(session, *, emit: bool = True)` + public `emit_cycle_events(summary)`):** ✅ **применим** — и это правильный подход, но с **другой семантикой**
- **Verdict: B4 Option B по сигнатуре, с другой семантикой `emit`.**
  - Refactor: `run_once(session, *, emit: bool = True) -> IngestionRunSummary`
  - При `emit=True` (manual route) → пишем `ingestion.run` audit + `ingestion.updated` event (текущее поведение, не регрессия)
  - При `emit=False` (scheduler job) → **всё равно пишем DB** (дюрабельность данных — это и есть смысл ingestion), **но skip audit + event** (это per-tick шум, оператору не нужны 1440 "ingestion ran" записей в день)
  - Public `emit_cycle_events(summary)` — single source of payload, anti-drift (manual route и job используют одну форму)
  - **Семантическое отличие от B4:** там `emit=False` skip'ал всё (snapshot был in-memory). Здесь `emit=False` skip'ит **только observability**, DB writes обязательны
- **Why:** ingestion по природе шумный (каждые 60s — это 1440/день). Operator-override через `POST /ingestion/run` — редкое событие, должно быть видно. Scheduler-driven periodic — routine, audit-flood антипаттерн. Manual = "emit by default" (ничего не меняется), scheduler = "muted by default" (новое поведение).
- **Альтернатива (отвергнута):** "emit-on-every-run легитимен" — да, но **на manual 1440 audit/день** это `audit.jsonl` ~5-10MB/день, и **все 1440 в SSE-стриме** — фронт захлёбывается. Не приемлемо.

### П.4 — Concurrency

- **Текущий lock/guard в `POST /ingestion/run`? — НЕТ.** `routes/ingestion.py:122-131` — голый вызов `await service.run_once(session)` без какой-либо защиты. **Не нашёл ни `asyncio.Lock`, ни `threading.Lock`, ни in-memory flag** ни в `routes/ingestion.py`, ни в `ingestion/service.py`, ни в `bootstrap.py`.
- **Где должна жить guard в B5:** **service-level, в `IngestionCycleService`** (как `asyncio.Lock` в `__init__`). Причины:
  - **Route-level lock** — не работает: scheduler вызывает `service.run_once` напрямую, минуя route
  - **Job-level lock** — плохая инкапсуляция: manual route должен разделять lock с job
  - **Service-level lock** — single source of truth, оба пути (manual + scheduler) проходят через один метод
- **Проблема с `asyncio.Lock`:** scheduler job выполняется в `ThreadPoolExecutor` (B3a mitigation, per deaddrop §"B0 ThreadPoolExecutor mitigation"). `asyncio.Lock` **не работает между event loop и thread** — `asyncio.Lock` блокирует только coroutine в том же loop.
- **Решение (v1, B5-acceptable):**
  - **`threading.Lock` + `is_running: bool` property** в `IngestionCycleService.__init__`
  - Manual route (`await service.run_once(session)`): `if service.is_running: return 409` (или skip с log); иначе `with service._lock: ...`
  - Scheduler job: перед `run()` проверить `service.is_running`; если True → `logger.info("ingestion cycle already running, skip tick")` + return (anti-flood). Иначе `with service._lock: service.is_running = True; ...; service.is_running = False`
  - **Caveat:** sync `threading.Lock` в async context = потенциально блокирует event loop. Решение — вынести блокировку через `asyncio.to_thread(...)` или использовать `asyncio.Lock` для route + `threading.Lock` для job'а (но это два lock'а, race возможен)
  - **Чище:** `asyncio.Lock` + scheduler job делает `asyncio.run(service.run_once_async_with_lock(session))` через event-loop-aware wrapper. Это **требует job'у быть async**, а B3b/B4 sync. **Расхождение с B0/B3b паттерном** (sync callable в ThreadPoolExecutor)
  - **Прагматичный v1:** `threading.Lock` + обернуть в `try/finally`. Документировать: "blocks event loop briefly, acceptable для 60s interval + sub-second ingestion duration"
- **Где состояние "цикл идёт":** in-memory `threading.Lock` + `is_running: bool` flag, instance-level на singleton `ingestion_cycle_service` (`bootstrap.py:330`). **Shared между всеми вызовами в одном процессе** (single-worker assumption из B0).
- **Multi-worker race:** задокументировано как out-of-scope v1 (deaddrop §"B0 single-worker assumption") — multi-worker = leader-election, не блокер.
- **DB-level race mitigation (если lock пробит):** unique constraints на `MarketBar` и `MarketFreshnessStatus` спасают от дубликатов строк. **Но `ops.ingest_run` / `ops.connector_status` / `store_news_items` / `store_sentiment_snapshots` могут получить duplicate rows** (нет unique constraint видимо). При реальном race одна из сессий упадёт в `IntegrityError` → broad except в `_run_market_ingest:136` → **фейковый incident в `summary.incidents`**.

### П.5 — DI availability

- **Что нужно job'у (per B4 pattern, scheduler-friendly):**
  - `ingestion_cycle_service: IngestionCycleService` (аналог `reliability_service` в B4)
  - `session_factory: sessionmaker` (для transient Session per tick, как в `ReliabilityRecheckJob.run()`)
  - `audit_writer: AuditWriter` (для `reliability.recheck_failed`-style verb на fail)
  - `event_bus: EventBus` (reserved, для v2)
  - `ingestion_settings: IngestionSettings` (опционально — для guard `binance_spot_enabled`, но это уже внутри `service.run_once`)
- **Доступно через `build_services` граф:**
  - `ingestion_cycle_service` — ✅ `bootstrap.py:292` (return dict) + `bootstrap.py:330` (module-level export)
  - `session_factory` — ✅ `bootstrap.py:289` + `bootstrap.py:340`
  - `audit_writer` — ✅ `bootstrap.py:284` + `bootstrap.py:323`
  - `event_bus` — ✅ `bootstrap.py:285` + `bootstrap.py:328`
  - `ingestion_settings` — ✅ `bootstrap.py:288` + `bootstrap.py:331`
  - **Всё в наличии, никаких новых сервисов не требуется**
- **A6 invariant check:**
  - `grep -rn "import clay.bootstrap\|from clay.bootstrap" backend/src/clay/scheduler/` = **0 files found** ✅
  - **Подтверждено:** scheduler/jobs/ не зависит от `clay.bootstrap` (A6 single-factory contract соблюдён, как в B3b/B4)
- **Что нужно в `lifespan.py` (per B4 lesson — pass deps through):**
  - В `ClayScheduler.add_ingestion_cycle_job()` прокинуть `ingestion_cycle_service` + `session_factory` + `audit_writer` + `event_bus` (по тому же паттерну, что `add_reliability_recheck_job`)
  - Production `api/lifespan.py` (B4 modified) — обновить call site
- **Протокол vs Protocol:** `IngestionCycleService` конкретный класс. B4 ввёл `_ReliabilityRecheckable` Protocol для test fake'а. **B5-рекомендация:** ввести `_IngestionCycleRunnable` Protocol (метод `run_once(session, *, emit: bool)`, опционально `emit_cycle_events(summary)`) — для симметрии с B4 и удобства тестовых fake'ов. Production `IngestionCycleService` duck-typed.

### П.6 — Auto-trigger

- **Сейчас ingestion запускается ТОЛЬКО manual:** единственная точка входа — `POST /ingestion/run` (`routes/ingestion.py:122-131`).
- **Нет фонового/periodic запуска** — `grep "apscheduler\|AsyncIOScheduler\|interval\|cron"` по `ingestion/` = пусто (`ingestion/service.py:1-284` не содержит scheduler-импортов; `ingestion/__init__.py:1` — пустой docstring; `ingestion/market/__init__.py:1-4` — только models re-exports).
- **Что B5 замещает/дополняет:**
  - **Дополняет** manual `POST /ingestion/run` — route **остаётся** (operator-override use case, по явному требованию задания)
  - **Добавляет** scheduler-driven periodic через `IngestionCycleJob` (60s interval, flag-gated `SchedulerSettings.ingestion_cycle_interval_seconds` — **уже зарезервировано** в `settings/scheduler.py:32, 59` для B5 ✅)
  - **Concurrency-guard** — **новое**, должен предотвращать параллельный manual+scheduler
- **B4 lesson carry-forward (Emma's framing):** "Before scheduling any service method, verify it's side-effect-free. If not, refactor with an `emit` flag or pure-compute split, then schedule."
  - **`run_once` НЕ side-effect-free** — он пишет в DB (mandatory для смысла ingestion). Это **принципиальное отличие от B4** (recheck можно разделить, ingestion — нет, его смысл и есть side-effects)
  - **Refactor с `emit: bool` флагом** — применим (см. П.3 verdict). Сематически отличается: `emit=False` skip'ит observability (audit+event), но не DB writes
  - **Pure-compute split** — **НЕ применим** для ingestion (нет смысла "вычислить ingestion без side-effects")
  - **B4 lesson честно:** side-effect-free precondition не выполняется → refactor с `emit` flag (Option B по сигнатуре, не по семантике)

---

## 🚩 Risk flags

### [HIGH] — блокеры, флагуй ДО плана

- **[HIGH-1] `store_news_items` / `store_sentiment_snapshots` — возможны duplicates при повторе.**
  - Не в скоупе recon-файлов, **требует pre-flight recon `repositories_context.py` ДО B5 plan-фазы**. Если unique constraint отсутствует — scheduler-driven periodic будет дублировать news/sentiment items в БД каждый тик (60s) → БД распухает, sentiment-аналитика polluted. Возможные фиксы: (a) ON CONFLICT DO NOTHING в SQL, (b) dedup-by-(source_name, external_id) в repository, (c) `if not exists` SELECT-then-INSERT. **Не известно, насколько это серьёзно, пока не прочитан `repositories_context.py`**

- **[HIGH-2] `route POST /ingestion/run` — НЕ имеет lock'а → manual может идти параллельно с scheduler.**
  - Race conditions на `ops.ingest_run`, `ops.connector_status`, `store_news_items`, `store_sentiment_snapshots` (нет unique constraint). `MarketBar` / `MarketFreshnessStatus` спасены unique constraints, но broad-except в `_run_market_ingest:136` ловит `IntegrityError` → фейковый incident в `summary.incidents` (нотификация оператору о несуществующей проблеме). **Concurrency-guard ОБЯЗАТЕЛЬНА в B5**, не optional.

### [MED] — важно для plan

- **[MED-1] `summary.market_records_written` лжёт на повторе** (`repositories_market.py:30, 45` — `written += 1` на INSERT и UPDATE). Нельзя использовать как "есть новые данные" signal. B5 plan должен или (a) разделить counter на `inserted` / `updated`, или (b) использовать `rows_written_total` с explicit `INSERT` / `UPDATE` подсчётом, или (c) принять "фейковое" значение как informational (и документировать). **Рекомендация:** разделить counters — 2 поля вместо 1, low-cost, повышает observability.

- **[MED-2] `asyncio.Lock` vs `threading.Lock` dilemma** (П.4). Scheduler job — sync callable в ThreadPoolExecutor. Manual route — async в event loop. Один lock работает только в одном контексте. **Pragmatic v1:** `threading.Lock` + документировать "blocks event loop briefly". Чистое решение: `asyncio.Lock` + job становится async (отход от B3b/B4 sync pattern). **Это архитектурный trade-off, требует явного решения в plan.**

- **[MED-3] `_next_sqlite_market_bar_id` — глобальный `MAX(id)` + инкремент** (`repositories_market.py:50-56`). При concurrent INSERT двух SQLite-сессий (parallel manual+scheduler) → обе увидят одно значение → второй INSERT получит уже занятый id → `IntegrityError` → broad except ловит → фейковый incident. **Pre-existing race bug, не введён B5, но усиливается B5.** Fix — использовать identity column (PG) или sequence (SQLite) вместо ручного MAX. **Out of scope B5, флагнуть в backlog.**

- **[MED-4] `MarketRepository.upsert_market_bars` — TOCTOU race (SELECT-then-INSERT) даже с unique constraint.** Обе сессии делают `existing = ... is None` → обе INSERT → одна падает на constraint. **Pre-existing**, не введён B5, флагнуть. **B5 concurrency guard снижает вероятность, но не устраняет TOCTOU** (lock на стороне Python, не на стороне DB).

- **[MED-5] `ops.ingest_run` / `ops.connector_status` — нет de-dup, растут на каждый вызов.** 60s interval = 1440 rows/день в `ingest_run` (минимум 1+2=3 на тик). **За месяц = ~43k rows** (маленькая таблица, не блокер, но eventual retention needed). Рекомендация: документировать, в roadmap — TTL/rotation для `ops.*` (уже в деaddrop как долг).

### [LOW] — косметика / future

- **[LOW-1] `market_fetch_max_attempts=2, retry_delay=0.5s`** (`settings/ingestion.py:21-22`). При scheduler-60s interval и 16 (symbol, timeframe) pairs → 16 fetches × 2 attempts × ~500ms = потенциально 16s worst case, дольше interval. **Pre-existing, не блокер B5**, но если ingestion перестанет успевать — нужна настройка. Документировать.

- **[LOW-2] `limit=200` на `fetch_klines`** (`market/service.py:20`). Binance возвращает 200 последних баров на запрос. На 5m timeframe это 200 × 5min = ~16.7 часов истории, на 1d = 200 дней. На 60s interval — **95% баров уже в БД**, UPDATE'ятся каждый тик. Wasteful, но не блокер. **Pre-existing, eventual optimization** (e.g., fetch только `bar_open_time > last_known`).

- **[LOW-3] `ingestion_cycle_interval_seconds=60` default** (`settings/scheduler.py:59`). Агрессивно для prod (1440 cycles/день, ~150k Binance API calls/день). Оператор может override через `CLAY_SCHEDULER_INGESTION_CYCLE_INTERVAL_SECONDS`. Документировать рекомендации.

---

## Recommendation

**`PROCEED to plan`** — с оговорками:

1. **Обязательный pre-flight recon** `db/repositories_context.py:store_news_items` и `store_sentiment_snapshots` (есть ли unique constraint / dedup logic) — **ДО старта B5 plan-фазы**. Это [HIGH-1] блокер. Если дубликаты возможны — plan должен включать dedup-fix (или `ON CONFLICT DO NOTHING` через constraint, или `if not exists` SELECT-then-INSERT, или window-de-dup в connector).

2. **Применить B4 Option B сигнатуру, с другой семантикой `emit`:**
   - `run_once(session, *, emit: bool = True) -> IngestionRunSummary`
   - Public `emit_cycle_events(summary: IngestionRunSummary) -> None` — single source of payload
   - Manual route: `emit=True` (default, ничего не меняется)
   - Scheduler job: `emit=False` + ручной вызов `emit_cycle_events(summary)` **ТОЛЬКО на transition** (по B3b anti-flood pattern: fresh-data-detected vs no-new-data). **Критично:** "transition" для ingestion = (a) `incidents` non-empty (были ошибки), (b) `summary.market_records_written > 0 AND все — INSERTs` (новые бары), (c) `connector_statuses` change. **Steady state (UPDATE-only, no incidents) → no emit.** Это уменьшает audit-flood с 1440/день до ~10-50/день (только meaningful events).

3. **Concurrency-guard — service-level:**
   - `IngestionCycleService.__init__` добавляет `threading.Lock` + `is_running: bool`
   - Manual route: `if service.is_running: raise HTTPException(409, "ingestion cycle in progress")` ИЛИ просто skip + log (зависит от UX, рекомендация — 409 для явности)
   - Scheduler job: перед `run()` проверить `is_running` → skip с `logger.info(...)` если True
   - **Caveat:** `threading.Lock` в async route блокирует event loop — задокументировать trade-off, eventual v2 = `asyncio.Lock` + job становится async

4. **A6 invariant — соблюсти:** scheduler/jobs.py **НЕ** импортирует `clay.bootstrap` (✅ уже подтверждено grep'ом). Job принимает `IngestionCycleService`-compatible объект через DI в `ClayScheduler.add_ingestion_cycle_job()`. Production wiring в `api/lifespan.py` обновляется по B4 образцу (deps pass-through).

5. **Optional, рекомендуется:** ввести `_IngestionCycleRunnable` Protocol (симметрия с B4 `_ReliabilityRecheckable`). Упрощает test fakes.

6. **Out of scope B5 (флагуй в B5.5 или отдельный slice):**
   - `_next_sqlite_market_bar_id` race fix (pre-existing, MED-3)
   - `MarketRepository.upsert_market_bars` TOCTOU fix (pre-existing, MED-4)
   - `ops.*` retention/rotation (deaddrop долг, MED-5)
   - `limit=200` wasteful fetch (eventual optimization, LOW-2)
   - `summary.market_records_written` counter split на inserted/updated (LOW-MED, nice-to-have, см. MED-1)

7. **Architect decision points (требуют явного "ок" от архитектора):**
   - **Sync vs async scheduler job** — текущий B3b/B4 pattern = sync в ThreadPoolExecutor. B5 emit-gating с `asyncio.Lock` требует async. Либо отход от pattern (async job), либо `threading.Lock` (с document block-on-loop trade-off). **Architect input обязателен.**
   - **`emit=False` skip-уровень** — только audit+event, не DB. Подтвердить (моё чтение B4 lesson: side-effect-free precondition не выполнен → emit-gating refactor легитимен, но DB writes = mandatory).
   - **Counter split на `inserted` / `updated`** — или оставить `market_records_written` как "строк обработано" (loose, но исторически)?

8. **Estimated test count:** **+5-8 net tests** (B0 estimate "B5: +2-3" — нижняя граница, нереалистична для B5). Реально: 1 protocol-shape test, 1-2 transition-only-emit tests, 1 concurrency-guard test, 1 manual route regression test, 1 scheduler-flag-gate test, 1-2 error-policy tests, 1 dep-missing loud-warning test. Цель: **221-224 passed** (текущие 216 + 5-8 net B5). Точная цифра — в plan-фазе.

## Plan-фаза может стартовать после:

- (a) прочтения `repositories_context.py` (pre-flight recon [HIGH-1])
- (b) явного "ок" от Emma на эту recon-вердикт
- (c) architect input по 3 decision points ([MED-1], [MED-2])

## How to apply

- B5 plan-фаза не стартует пока Emma не примет [HIGH] flags и не даст direction
- Pre-flight recon `repositories_context.py` — **отдельный шаг** (микро-recon через grep + read, 5 мин)
- Если [HIGH-1] найдёт duplicates — plan расширяется на dedup-fix slice (может стать B5.5)

## Carry-forward

- B4 lesson "side-effect-free precondition" + "emit-flag refactor" применим с **другой семантикой** (DB writes mandatory, observability muted)
- B3b anti-flood pattern ("transition-only emit") применим к ingestion: "transition" = (incidents OR new INSERTs OR connector change)
- A6 invariant (no `import bootstrap` в scheduler) — keep
- Service-level `threading.Lock` — pragmatic v1, eventual v2 = `asyncio.Lock` + async job (если станет async)
