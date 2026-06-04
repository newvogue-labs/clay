# Текущее Состояние

**Дата:** 2026-06-04
**Где остановились:** **E3 закоммичен.** `pytest -q` → **293 passed** (+5 net, 0 regress). Pyright src 35 (baseline 35).
**Следующий шаг:** жду E4 recon (Bybit-адаптер, изолированно).

## 🛑 Точка остановки (session handoff)

**Сессия 2026-06-04.** Wave E: E1 + E2 + E3 полностью.

**Что сделано:**
1. **E0 recon** — 7-пунктовая карта Binance-coupling. Seam подтверждён.
2. **E1 (Protocol-шов) — закоммичен** — `MarketDataClient(Protocol)`, Commit `6d6953f`.
3. **E2 (source в identity) — закоммичен** — миграция 0010. Commit `d94e893`.
4. **E3 (produce-side seam) — закоммичен** — `ExchangeConfig` + factory + per-exchange ingest loop. Commit готов.

**Открытые вопросы:**
- Продуктовый для read-side: (i) primary-source preference — склон к этому, финал к pre-E5

## Блокеры
- Нет

## Ключевые файлы
- `docs/mission-control/adrs/adr-008-exchange-abstraction-and-multi-exchange-portability.md`
- `src/clay/ingestion/market/exchange_config.py`
- `src/clay/ingestion/market/factory.py`
- `src/clay/ingestion/market/service.py`

## Маршруты и AI Rules
— без изменений.
