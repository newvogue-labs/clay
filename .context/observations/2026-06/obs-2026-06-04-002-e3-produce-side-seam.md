---
name: E3 — multi-exchange produce-side seam
description: ExchangeConfig + factory + per-exchange ingest loop. Read-side вырезан в pre-E5.
type: migration
---

**Проблема/Контекст:**

Для multi-exchange (E4, Bybit) ingestion-пайп должен уметь итерировать несколько бирж. До E3 был ровно один клиент `BinanceSpotClient` в `MarketIngestionService.client`, и `_collect_market_bars` шёл по flat `market_symbols`/`market_timeframes` минуя понятие биржи.

**Решение:**

1. **`ExchangeConfig` (frozen dataclass)** — `exchange_id`, `source`, `enabled`, `base_url`, `symbols`, `timeframes`. Никаких новых ENV — сборка из существующих `CLAY_BINANCE_*`/`CLAY_MARKET_*`.

2. **`build_market_client(cfg)`** — dispatch по exchange_id. Только `"binance_spot"` → `BinanceSpotClient`. Неизвестный id → `ValueError` (fail-fast).

3. **`build_exchanges_map(settings)`** — сборка dict из flat settings → одна запись `"binance_spot"`.

4. **`MarketIngestionService(exchange_clients: dict)`** — принимает dict `exchange_id → (client, config)`. `set_http_client()` итерирует все.

5. **`_collect_market_bars`** — внешний цикл по биржам (`for _id, (client, config) in exchange_clients.items()`), внутренний — существующий per-symbol/tf.

6. **`_MarketBatch.source`** — source из exchange config, не из client. Per-exchange ingest runs в `_persist_market_bars`.

**Ключевое решение Emma:** read-side (source-фильтрация + dedup) вырезан в отдельный decision-gated слайс перед E5, т.к. не может быть провалидирован без 2-й биржи в проде и требует продуктового решения (primary-source preference).

**Why / How to apply:**
- E4: Bybit-адаптер как второй entry в `exchanges_map` + второй `(client, config)` tuple
- Pre-E5: read-side source-фильтр с product decision (i) primary-source preference
- E5: live-вайринг Bybit

**pytest:** 293 passed (+5), pyright src 35 (0 new), 0 regress.
