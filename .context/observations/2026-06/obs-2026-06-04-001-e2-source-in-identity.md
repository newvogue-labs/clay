---
name: E2 — source становится частью identity (ломающая миграция)
description: UC расширены source на market_bars + freshness_status. server_default снят (multi-exchange hazard). 0 behaviour change для Binance-only.
type: migration
---

**Проблема/Контекст:**

Для multi-exchange (E4, Bybit) source должен быть частью уникальной identity. Старый UC `(symbol, timeframe, bar_open_time)` не различал биржи → Bybit мог затереть Binance. MarketFreshnessStatus вообще не имел колонки source. server_default='binance_spot' на market_bars.source был latent-hazard: забытый source от Bybit молча записался бы как Binance.

**Решение:**

1. **Миграция 0010 (PG-only, raw SQL)**:
   - market_bars: DROP old UC → ADD `UNIQUE (source, symbol, timeframe, bar_open_time)` → `DROP DEFAULT`
   - market_freshness_status: `ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'binance_spot'` (backfill) → `DROP DEFAULT` → DROP old UC → ADD `UNIQUE (source, symbol, timeframe)`

2. **ORM models**: FreshnessStatus +source; UC расширены; 0 default на source (NOT NULL обязателен)

3. **Repository**: `upsert_freshness_status(..., source)`; SELECT-WHERE += source (bars + freshness)

4. **Service**: success-path `source=latest_bar.source`; failure-path `source=self.market_service.client.source` (Protocol attr, не литерал)

**Ключевое решение Emma (Q2 reframe):** server_default снимаем, а не добавляем. Забытый source должен падать громко (NOT NULL violation), не тихо mislabel'ить чужую биржу. `ADD COLUMN ... NOT NULL DEFAULT 'binance_spot'` — backfill одной командой; `DROP DEFAULT` сразу следом.

**Why / How to apply:**

- E3: read-side source-фильтрация + list_latest_bars dedup фикс
- E4: Bybit адаптер source="bybit_spot" получит изоляцию на UC уровне
- server_default removed on both tables: любой новый adapter обязан явно указать source

**pytest:** 288 passed (+2), pyright src 35 (0 new), 0 regress. Миграция up/down/up на PG.
