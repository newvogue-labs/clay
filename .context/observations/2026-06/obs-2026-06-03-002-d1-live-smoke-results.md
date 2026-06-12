---
name: D1 — первый bounded live-smoke (real Binance klines)
description: Первый успешный парсинг живого klines-ответа. 9/9 batches, 0 incidents, 1800 bars inserted, ~5.5s latency.
type: research
---

**Context:** D1 live-smoke после D0 recon. Первый контакт с реальным Binance Spot API (GET /api/v3/klines, read-only, без auth). 3 symbols (BTCUSDT/ETHUSDT/SOLUSDT) × 3 timeframes (5m/15m/1h).

**Results:**

- **POST /ingestion/run:** 200 OK. `started_at: 2026-06-03T14:58:45`, `finished_at: 2026-06-03T14:58:50` (~5.5s)
- **market_records_inserted: 1800** (9 batches × 200 bars), **updated: 0** (first run)
- **freshness_updates: 9** (one per symbol/timeframe), **transitions: 0** (all inserts)
- **incidents: 0**, **connector_statuses: 2** (demo-news healthy, demo-sentiment healthy)
- **news: 1**, **sentiment: 1** (synthetic connectors)
- **health:** all 9 items `"status": "fresh"`, delta range 3–59 min. Context fresh.
- **Spot-check DB:** real OHLCV values (BTC ~$66,881, ETH ~$1,857, SOL ~$74.4), bar_open_time = live recent candles
- **Uvicorn log:** 0 warnings, 0 errors, 0 tracebacks

**Validation checklist all green:**
- [x] klines распарсился — нет JSONDecodeError, OHLCV вменяемые
- [x] 9/9 batches success, 0 incidents
- [x] бары записаны с верными symbol/timeframe/open_time
- [x] freshness: все FRESH (посчитан корректно)
- [x] latency ~5.5s (отлично для первого контакта + SQLite-fallback отсутствует — PG)

**🔴 Флаг-условия:** НЕ сработали. Нет 451/403, parsing-error, 4xx/5xx.

**Solution:** D1 passed. Live klines парсятся корректно. Никаких блокеров для Wave D.

**Why / How to apply:** D1 confirms the ingestion pipeline works end-to-end against real Binance. Path is clear for D2 (hardening: base_url config, Retry-After parsing) and D3 (basicConfig/logging).
