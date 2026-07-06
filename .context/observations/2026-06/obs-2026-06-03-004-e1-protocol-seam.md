---
name: E1 — Protocol-шов для market data (refactor)
description: Извлечение MarketDataClient Protocol из BinanceSpotClient. Нормализация перенесена внутрь адаптера. 0 behavior change.
type: refactor
---

**Проблема/Контекст:**

E0 recon выявил: единственное место, где код знает про "именно Binance" — это `BinanceSpotClient` + внешняя `normalize_kline_payload()`. Пайплайн зависел от конкретного класса, а не от абстракции. Нужно формализовать контракт `MarketDataClient`, чтобы вторая биржа (Bybit, E4) легла под тот же протокол без дифф-рефакторинга пайплайна.

**Решение:**

1. **Новый `ingestion/market/protocol.py`** — `MarketDataClient(Protocol)` с `@runtime_checkable`:
   - `source: str` — атрибут экземпляра (default `"binance_spot"` per Emma)
   - `async fetch_klines(symbol, interval, limit) -> list[NormalizedMarketBar]` — нормализованный возврат
   - `set_http_client(client)` — default no-op (lifespan injection override)

2. **Перенос нормализации ВНУТРЬ адаптера:**
   - `BinanceSpotClient.fetch_klines()` теперь возвращает `list[NormalizedMarketBar]` (а не сырой JSON-массив)
   - Приватный `_fetch_raw()` — HTTP-вызов (старый `fetch_klines`-body)
   - Приватный `_normalize_row()` — обёртка kline-массива в dict + вызов `normalize_kline_payload`
   - `MarketIngestionService._normalize_kline_row()` удалён — pass-through `await self.client.fetch_klines(...)`

3. **`source` как ctor-param:** `BinanceSpotClient(source: str = "binance_spot")`. Канонический source остаётся `"binance_spot"` (Emma поправка) — это 0 behavior change, не "binance".

4. **`normalize_kline_payload(payload, source="binance_spot")`** — функция остаётся публичной (для `test_market_normalizer.py` byte-for-byte), но source параметризован.

5. **Снят Python-side default в ORM:** `MarketBar.source` и `OrderBookSummary.source` — убран `default="binance_spot"`. Это ORM-level default (не server_default), миграция НЕ нужна. Источник значения теперь — `NormalizedMarketBar.source` (явный).

6. **Test fakes обновлены:** все 4 fake-класса (`FakeBinanceClient` ×3 в `test_ingestion_cycle.py`, `_FakeBinanceClient` в `test_ingestion_cycle_service.py` + `test_ingestion_route.py`, `FakeBinanceClient` в `test_ingestion_api.py`) теперь возвращают `NormalizedMarketBar` с правильным `(symbol, timeframe)` per call. Плюс `set_http_client` no-op для Protocol-конформности.

7. **Protocol conformance test** — `test_market_data_client_protocol.py`: structural check `isinstance(client, MarketDataClient)`, плюс проверка `source` override.

**Why / How to apply:**

- **Шов (seam) для Wave E**: протокол + pass-through MarketIngestionService означают, что E4 (Bybit) и E5 (multi-exchange wiring) — это только новый адаптер + 2-3 строки в bootstrap, без дифф-рефакторинга пайплайна
- **Confirm (a) per-symbol failure-isolation:** fetch+normalize в одном `try` внутри `BinanceSpotClient`, exception всё ещё ловится per-symbol в `_collect_market_bars`. Test `test_ingestion_cycle_uses_exception_class_when_message_is_empty` это доказывает (4 passed).
- **Confirm (b) orphan write-path:** grep `MarketBar(**` в `src/` = 1 match (`repositories_market.py:41`) — payload всегда идёт через `NormalizedMarketBar.model_dump()`. Снятие default безопасно.
- **Pyright:** src-errors 35 (baseline 36, −1, 0 new). Все 35 — pre-existing в `signal_engine/service.py` и пр., не в E1-файлах
- **pytest:** 286 passed (baseline 284, +2 net = Protocol conformance tests). 0 regress
- **0 миграций, 0 изменений схемы БД** — server_default никогда не было, только Python-side default
- **Стоимость:** ~6 source-файлов + 5 test-файлов, ~+30/-20 LOC net. Чистый рефактор, поведение идентично

**Carry-forward на E2 (миграция):**
- `MarketBar` / `OrderBookSummary` source-колонка уже готова к `NOT NULL` enforcement (Python-side default убран)
- Расширение UC `(symbol, timeframe, bar_open_time)` → `(source, symbol, timeframe, bar_open_time)` — atomic migration в E2
- `MarketFreshnessStatus` — та же дыра, fix в E2
