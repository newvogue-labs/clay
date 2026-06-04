# Report: Wave E — E3 produce-side multi-exchange seam

> **Сессия 2026-06-04.** E1 (`6d6953f`), E2 (`d94e893`), E3 (this commit). **293 passed** (288 → 293, +5 net, 0 regress). Pyright src 35 (baseline 35).

## E3 — produce-side multi-exchange seam ✅

### Решения Emma
- E3 обрезан до produce-side (read-side вырезан в pre-E5 decision-gated слайс)
- Product-fork: (i) primary-source preference — склон к этому

### Создано
| Файл | Суть |
|---|---|
| `backend/src/clay/ingestion/market/exchange_config.py` | `ExchangeConfig` frozen dataclass |
| `backend/src/clay/ingestion/market/factory.py` | `build_market_client` dispatch + `build_exchanges_map` |
| `backend/tests/ingestion/market/test_factory.py` | 3 unit tests (binance, unknown fail-fast, exchanges map) |

### Изменено
| Файл | Суть |
|---|---|
| `ingestion/market/__init__.py` | +exports |
| `ingestion/market/service.py` | `exchange_clients: dict[str, tuple[MarketDataClient, ExchangeConfig]]`; `set_http_client` iterates all |
| `bootstrap.py` | `build_exchanges_map` + `build_market_client` вместо прямого `BinanceSpotClient` |
| `ingestion/service.py` | `_MarketBatch.source`; outer exchange loop; per-exchange ingest runs; `batch.source` вместо `self.market_service.client.source` |
| 6 test-файлов | dict-based `MarketIngestionService`; seam + isolation tests |

### Проверки
| Критерий | Статус |
|---|---|
| (a) production 1-exchange byte-identical | ✅ 288 baseline зелёные |
| (b) factory fail-fast | ✅ ValueError на неизвестном exchange_id |
| (c) per-exchange isolation | ✅ упавший → freshness unknown, здоровый → persist |
| (d) read-side НЕ тронут | ✅ 9 call-sites + 3 dedup = 0 изменений |
| (e) 0 новых ENV | ✅ flat settings не тронуты |
| (f) A6: 0 import clay.bootstrap | ✅ |
| (g) synthetic 2-exchange seam | ✅ dispatch доказан без Bybit |

### Acceptance
| | baseline | E3 | Δ |
|---|---|---|---|
| pytest | 288 | **293** | +5 (factory ×3 + seam + isolation) |
| regressions | — | 0 | ✅ |
| pyright src | 35 | **35** | 0 new |
| migrations | — | 0 | ✅ |

### Что дальше
- **E4 (Bybit-адаптер, изолированно)** — чистый `MarketDataClient` имплементатор, symbol/tf-маппинг внутри адаптера, 0 вайринга в bootstrap/ingestion
- **Read-side pre-E5** — source-фильтр + dedup + product decision (i)
- **E5** — live-вайринг Bybit
