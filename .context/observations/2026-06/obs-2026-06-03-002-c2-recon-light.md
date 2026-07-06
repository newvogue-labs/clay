# C2 recon-light — итог

Все 5 пунктов подтверждены, **флаги отсутствуют** (🟢). Один важный structural observation меняет план в сторону упрощения.

## Подтверждения по пунктам

**1. Точка инжекта** (`binance_client.py:10-44`):
- `BinanceSpotClient.__init__` (`:10-18`) уже принимает `client: httpx.AsyncClient | None = None`, поле `self._client = client`.
- Injected-branch (`:26-34`) — production path. Else-branch (`:36-44`) — per-call fallback.
- **`set_http_client()` НЕ существует** — нужно создать. Либо использовать только конструктор (не вариант: import-time singleton не имеет client).

**2. Wiring** (`bootstrap.py:176, 335` + `api/dependencies.py:55-56`):
- `market_ingestion_service = MarketIngestionService(BinanceSpotClient())` на import-time (`:176`).
- Экспортируется как module-level singleton на `:335`.
- `get_market_ingestion_service()` (`:55-56`) возвращает тот же singleton.
- **Late-binding setter обязателен** — на import-time client ещё не существует (event loop не запущен).

**3. Lifespan ordering** (`lifespan.py:96-110`):
- `scheduler.start()` на `:96` ДО `app.state.scheduler = scheduler` (`:97`) — confirmed B6 invariant 2a.
- `scheduler.shutdown(wait=True)` на `:108` в `finally` блоке, перед `app.state.scheduler = None` на `:110`.
- **Client creation slot:** ДО `scheduler.start()` (перед строкой 86 или до `if scheduler_settings.enabled:`).
- **Client aclose() slot:** строго ПОСЛЕ `scheduler.shutdown(wait=True)` (`:108`), ПЕРЕД `app.state.scheduler = None` (`:110`).

**4. Route-path** (`api/routes/ingestion.py:7, 121-142` + `api/dependencies.py:55-56, 63-65`):
- Route `POST /ingestion/run` (`:121-142`) берёт `service: IngestionCycleService` через `Depends(get_ingestion_cycle_service)`.
- `IngestionCycleService` уже держит `market_service: MarketIngestionService` (см. `bootstrap.py:181-187`).
- `market_service` = singleton = тот же объект, что и в `bootstrap.py:335`.
- **Ключевое:** route-path и scheduler-path **оба** идут через **один и тот же** `MarketIngestionService` → `BinanceSpotClient` singleton. Один `set_http_client()` покрывает оба потребителя. **`app.state.httpx_client` НЕ нужен** — лишний coupling.

**5. Fallback contract** (`binance_client.py:36-44` + `tests/ingestion/market/test_binance_client.py:21-46`):
- B4.5 test покрывает injected-branch (через `client=mock_client` в конструкторе).
- Else-ветка (per-call construction) — НЕ покрыта тестом (только code-read).
- C2 acceptance добавит unit-тест на else-ветку: `BinanceSpotClient()` без injected client → `httpx.AsyncClient()` создаётся внутри `fetch_klines` → `MockTransport` happy-path.

## Structural observation (упрощение vs. Q3-план)

Emma Q3 рассматривал три пути DI: `app.state` / `build_services(client=...)` / module-singleton. Все три отклонены (variant (c) — не на event loop; (a) — scheduler-job не видит; (b) — нужен late-binding).

**Hybrid (a)+(b)** из Q3 сводится к **одному чистому варианту** благодаря recon: **late-binding setter на `BinanceSpotClient`**, без `app.state`, без module-singleton. Сейчас объясню почему.

- `MarketIngestionService` — import-time singleton (`bootstrap.py:176`).
- `IngestionCycleService` хранит `market_service: MarketIngestionService` (B5 constructor contract).
- `IngestionCycleJob` (scheduler-job) берёт `ingestion_cycle_service` через `lifespan.py:59` module-import → `run_once` → `market_service.fetch_and_normalize` → `binance_client.fetch_klines` → инжектнутый client (если есть) ИЛИ per-call fallback.
- `POST /ingestion/run` route берёт `ingestion_cycle_service` через `get_ingestion_cycle_service()` → тот же путь.

**Один setter `binance_client.set_http_client(client)` покрывает оба потребителя через существующий DI-граф. `app.state.httpx_client` не нужен** — `app.state` остаётся для app-lifetime state (`scheduler`, `started_at`), httpx client живёт на singleton, не на app.state.

**Implication для плана:** убираем `app.state.httpx_client` из Q3 (это лишний coupling). Lifespan в startup вызывает `binance_client.set_http_client(client)` на module-singleton, в shutdown вызывает `await client.aclose()` ПОСЛЕ scheduler shutdown.

План ниже.
