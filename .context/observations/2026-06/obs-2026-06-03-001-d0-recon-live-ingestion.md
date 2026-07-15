---
name: D0 recon — live-ingestion path
description: Полный recon live-пути: env-флаги, demo-vs-live разводка, Binance endpoints, rate-limit, error handling, C2/C3/C1 verify, safety, observability, UI-snapshot, bounded smoke harness
type: research
---

**Context:** Wave C 3/4 done (C1 C2 C3). C4 retention deferred. Wave D = первый live-contact с реальным Binance Spot API. Market-data только; news/sentiment остаются synthetic (Q5).

**Findings:**

- **Rate-limit budget:** 0.75% (9 weight/min из 1200). 3 symbols × 3 timeframes × 1 call/cycle × 1 weight. `limit=200` избыточен для 5m таймфрейма (16.6 часов истории) при 60s цикле.
- **Testnet:** `base_url = "https://api.binance.com"` жёстко зашит в `binance_client.py:12`. Нет env/config. Первый live-прогон — против prod API.
- **Retry-After парсинг:** отсутствует. `_fetch_market_bars` retry с жёстким `0.5s` delay × 2 попытки. На 429 с `Retry-After: 60` — 2 быстрых ретрая + пропуск цикла. Не блокер (C3 per-symbol isolation), но до live стоит починить.
- **C2 client wiring:** lifespan-owned `httpx.AsyncClient` инжектирован ДО `scheduler.start()` (`lifespan.py:101→108→110-119`). Live klines идут через shared client, не через fallback. ✅
- **C3 to_thread:** persist в worker-потоке. 9 batches × 200 bar ∼ 1800 строк/цикл. SQLite ~50ms, PG ~10ms. ✅
- **C1 dedup:** UPSERT по PK `(symbol, timeframe, bar_open_time)`. Реальные свечи — UPDATE существующих + 1-2 INSERT новых. ✅
- **Safety:** `BinanceSpotClient` — только `GET /api/v3/klines` (read-only, без API key). 0 ордеров/trade/withdraw. ✅
- **News/sentiment:** `_build_default_context_connectors()` хардкодит `DemoNewsConnector` + `DemoSentimentConnector`. Q5 соблюдён. ✅
- **Observability:** `clay.*` логгеры созданы, `basicConfig` не вызван (B1 backlog). `GET /ingestion/health` показывает freshness + incidents. `POST /ingestion/run` возвращает полный summary. SSE-события при transition.
- **Bounded smoke harness:** manual `POST /ingestion/run` — безопасный первый контакт (9 klines calls, 0.75% rate limit).
- **limit=200 wasteful fetch** — 200 баров на 5m = 16.6ч истории при 60s цикле. Pre-existing debt (#14 в deaddrop).

**Рекомендация:** Start Wave D with manual `POST /ingestion/run` (option A). No testnet, no scheduler needed for first contact. `base_url` config + Retry-After = optional improvement, not blocker.

**Why/how to apply:** При старте Wave D использовать `CLAY_BINANCE_SPOT_ENABLED=true` (default) + manual route. Наблюдать через `GET /ingestion/health` и логи. Добавить `CLAY_BINANCE_BASE_URL` env если testnet нужен для повторяемых тестов.
