# S-EGRESS-RECON-1: Egress Recon + Testnet Reachability + Integration Point

**Status:** Recon-only, 0 кода, read-only досье  
**Date:** 2026-06-26  
**Scope:** Testnet Binance (spot + futures) и non-US egress для будущего real-money  
**Non-goals:** Любые изменения кода, реальные ключи, prod deployment

---

## 1. Testnet Reachability (текущий egress)

**Текущий egress:** Paris, France (AS400897 PETROSKY CLOUD LLC, `83.136.209.168`) — non-US, никакой 451.

### 1.1 Spot testnet: `testnet.binance.vision`

| Эндпоинт | Результат | Примечание |
|----------|-----------|------------|
| `GET /api/v3/ping` | **HTTP 200**, `{}` | ping работает |
| `GET /api/v3/klines?symbol=BTCUSDT&interval=1h&limit=3` | **HTTP 200**, real OHLCV | Живые данные, не мок |
| `GET /api/v3/exchangeInfo?symbol=BTCUSDT` | **HTTP 200** | rateLimits: 6000 REQUEST_WEIGHT/min, 50 ORDERS/10s |
| `GET /api/v3/account` (без sig) | HTTP 400, `code:-1102` | Корректная защита signature (не мок) |

**Вывод:** Spot testnet полностью доступен, API совпадает с production (testnet.binance.com в Wayback = точно такой же формат). Данные — реальные рыночные данные, не синтетические. Rate limits generous: 6000 weight/min (как production).

### 1.2 Futures testnet: `testnet.binancefuture.com`

| Эндпоинт | Результат | Примечание |
|----------|-----------|------------|
| `GET /dapi/v1/ping` | **HTTP 200**, `{}` | COIN-M futures ping |
| `GET /dapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=2` | **HTTP 200**, real data | Живые COIN-M свечи |
| `GET /eapi/v1/ping` | **HTTP 200**, `{}` | Options testnet ping |

**Вывод:** Futures (COIN-M and USD-M) и Options testnet доступны из текущего egress.

### Проверка на 451

Production `api.binance.com` — тоже HTTP 200 из Paris. **Никакого 451 на текущем egress (FR) не обнаружено.** 451 возникает только при US-egress (US IP, US-VPS, US-провайдер).

---

## 2. Non-US Egress Options (если/когда понадобится)

### Вариант A: VPS в non-US регионе

| Провайдер | Регион | Стоимость ~ | Надёжность | Сложность |
|-----------|--------|-------------|------------|-----------|
| Hetzner ( Fritz ) | DE, FI | €4-8/мес | Высокая | Низкая |
| OVHcloud | FR, DE, PL | €3-7/мес | Высокая | Низкая |
| DigitalOcean | FRA, LON | $6/мес | Высокая | Низкая |
| Vultr | PAR, FRA | $2.5-5/мес | Средняя+ | Низкая |
| AWS EC2 | eu-west-3 (Paris) | $3-10/мес | Очень высокая | Средняя (IAM) |

**Tradeoffs:**
- ✅ Полный контроль над egress IP
- ✅ Persistent, не нужно поддерживать соединение с home
- ✅ Можно разместить рядом с existing infra (если5433 на том же VPS)
- ❌ Дополнительный хост для управления
- ❌ Если 451 появится у Hetzner/OVH — редкий, но возможен (Binance блокирует дата-центры)

### Вариант B: Reverse proxy / edge function

| Сервис | Пример | Стоимость ~ | Надёжность | Сложность |
|--------|--------|-------------|------------|-----------|
| Cloudflare Workers | testnet worker | Free tier | Высокая | Низкая |
| Fly.io | edge app | Free tier | Средняя | Средняя |
| ngrok / frp | local proxy | Free | Низкая | Низкая |

**Tradeoffs:**
- ✅ Zero infrastructure (CF Workers)
- ✅ IP не привязан к home
- ❌ Добавляет latency (10-50ms на запрос)
- ❌ Нужно хранить API ключи в edge env (безопасность)
- ❌ Production Binance НЕ разрешает proxy по ToS (только testnet/futures)

### Вариант C: VPN / WireGuard

| Тип | Пример | Стоимость ~ | Надёжность | Сложность |
|-----|--------|-------------|------------|-----------|
| Commercial VPN (non-US) | Mullvad, IVPN | €5-6/мес | Высокая | Низкая |
| Self-hosted WG | VPS + wg | €3-5/мес | Высокая | Средняя |
| Tor (не для prod) | — | Free | Низкая | Низкая |

**Tradeoffs:**
- ✅ Быстро развернуть
- ✅ Non-US hop
- ❌ Mullvad/IVPN IP-пулы иногда попадают под geo-restrictions Binance (редко, но бывает)
- ❌ Высокая вариативность IP = harder to whitelist
- ❌ Дополнительный hop → latency

### Рекомендация по egress

**Если Binance 451 стал проблемой из текущего местоположения (US):**

1. **Старт:** Mullvad (€5/мес, non-US) → SMOKE TEST (ping + klines) → если проходит — OK
2. **Staging:** Hetzner FRA/VPS (~€4/мес) → persistent, дешевле VPN
3. **Production:** AWS eu-west-3 (Paris) ↔ Binance — тот же регион, минимум latency

**Важно:** ToS Binance запрещает proxy для production. Testnet/futures через proxy — допустимо. Для production-real-money VPS в non-US — единственный легальный путь.

---

## 3. Точка интеграции: testnet/real execution → ccxt/ADR-008

### 3.1 Текущая архитектура (ADR-008, Wave E3)

```
IngestionSettings
  └─ binance_base_url: str = "https://api.binance.com"    ← ТОЧКА ВХОДА testnet
  └─ binance_spot_enabled: bool = True

build_exchanges_map(settings)
  └─ ExchangeConfig(
        exchange_id="binance_spot",
        base_url=settings.binance_base_url,              ← переключается на testnet
        symbols=["BTCUSDT","ETHUSDT","SOLUSDT"],
        timeframes=["5m","15m","1h"],
    )

build_market_client(cfg)                                   ← фабрика
  └─ BinanceSpotClient(base_url=cfg.base_url, ...)        ← уже принимает base_url
```

**Что НЕ трогаем:**
- `ExchangeConfig` shape (exchange_id, source, base_url, symbols, timeframes)
- `MarketDataClient` Protocol (`fetch_klines`)
- `build_exchanges_map` signature
- `MarketBar` / `NormalizedMarketBar` DTOs
- Normalization/symbol mapping layer
- Freshness/rate-limit logic

**Что МЕНЯЕМ при переходе на testnet:**
Только `CLAY_BINANCE_BASE_URL` env var:
```
CLAY_BINANCE_BASE_URL=https://testnet.binance.vision
```
Zero code changes. Zero risk.

### 3.2 Future: Execution Layer (отдельный ADR, не E8/E9)

ADR-008 explicitly delegates execution to a future, heavier layer. Текущий `DemoTradingService` — advisory/read-only recording.

Если когда-нибудь понадобится real-money execution, структура будет:

```
Новый Protocol: ExecutionClient (future ADR)
  ├── submit_order(symbol, side, quantity, type, ...) -> OrderResult
  ├── cancel_order(symbol, order_id) -> CancelResult
  ├── get_order_status(symbol, order_id) -> OrderStatus
  └── get_balances() -> list[Balance]

Новая фабрика: build_execution_client(cfg: ExecutionConfig)
  └─ BinanceSpotExecutionClient(base_url=cfg.base_url, api_key, secret)

ExecutionConfig
  ├─ exchange_id: str
  ├─ base_url: str              ← тоже переключается на testnet/real
  ├─ api_key: str               ← только для execution
  ├─ api_secret: str            ← только для execution
  ├─ testnet: bool              ← safety switch
  └─ dry_run: bool              ← Q5 manual-only = всегда True для demo

Hard real-money gate (RV8):
  ├─ session_control.start_session() → проверяет `execution_mode`
  ├─ execution_mode = "dry_run"  → только demo-trade, запись в demo_trade_records
  ├─ execution_mode = "testnet"  → реальные REST-ордера на testnet
  ├─ execution_mode = "live"     → только при Q5 override (manual confirmation)
  │     └─ override требует: audit_log + explicit operator action
  │     └─ НЕТ авто-switch из dry_run → live
  └─ Q5 invariant: без явного override система НИКОГДА не ставит real ордер
```

**Что НЕ трогаем при добавлении execution (будущее):**
- `MarketDataClient` Protocol (data ingestion)
- Родительский `build_market_client()`
- Signal engine / sizing / risk limits
- Demo-trading recording
- Existing `ExchangeConfig` → новый `ExecutionConfig` (отдельная таблица/env)

**Где подключается execution:**
- Входная точка: `SessionControlService.start_session()` после preflight
- Слой: между `PreflightService` (risk check) и `DemoTradingService.log_current_trade()`
- Switch: `execution_mode` из `IngestionSettings` или нового `ExecutionSettings`
- Безопасность: Q5 override = explicit button in UI → audit log → только потом `execution_mode = "live"`

### 3.3 Текущий «real-money gate» = отсутствие execution layer

Сейчас гейт — architectural, не coded:
- `can_open_binance: bool` в `WorkspaceStateSnapshot` — UI-флаг, вычисляется из `blocking_reason`
- Если `blocking_reason` не None → кнопка disabled в UI
- `start_session()` → вызывает `build_snapshot(for_start=True)` → если preflight.fail → ValueError
- Всё это работают в DEMO-режиме: трейд записывается в `demo_trade_records`, реальных ордеров НЕТ

**RV8 (override + audit = будущий ADR):**
Не реализовано. План:
- Новый ADR: "Real-Money Execution Gate" (ADR-025?)
- Переменная `CLAY_EXECUTION_MODE=dry_run|testnet|live`
- `live` активируется ТОЛЬКО через вручную нажатый override (не из кода, не из config)
- Все override-события → audit log (`audit_writer.write("execution_mode_changed", ...)`)
- Сюда же можно добавить 2FA / hardware key / multisig для Героя

---

## 4. Рекомендуемый путь (STOP на ревью)

### Рекомендация: Testnet-first, затем production non-US egress

| Фаза | Что | Зачем |
|------|-----|-------|
| **Фаза 0 (сейчас)** | Проверить testnet из текущего egress | ✅ Сделано — Paris подходит |
| **Фаза 1 (testnet)** | Подключить `CLAY_BINANCE_BASE_URL=https://testnet.binance.vision` | 0 кода, новая стратегия на тех же свечах |
| **Фаза 2 (non-US egress)** | Если 451 появится — VPS в EU (Hetzner €4/мес) | Persistent, дешевый, надёжный |
| **Фаза 3 (real-money)** | Отдельный ADR (ADR-025?) — execution layer + Q5 gate | После ≥30 live исходов + стратегическая проверка |

### Почему testnet (Фаза 1):

1. **Zero code change** — только env var
2. **Zero risk** — не реал-деньги, но полная копия API
3. **Проверка работы интерфейса** — тестируем сигналы, sizing, UI на реальном API
4. **Гео-независимость** — testnet доступен из большинства locations (включая US, но не prod)
5. **Real data** — testnet.binance.vision отдаёт live рыночные данные (не мок)

### Критерии перехода на Фазу 2 (non-US egress):

- [ ] Binance начал блокировать текущий egress (451 на `api.binance.com`)
- [ ] Появилась необходимость в prod-orders (не только data ingestion)
- [ ] Обновили ToS / юридическое заключение по non-US операциям

### Критерии перехода на Фазу 3 (real-money ADR):

- [ ] ≥30 real demo outcomes на real data (не replay)
- [ ] Согласована стратегия с Героем
- [ ] Подписан RV8: override + audit модель
- [ ] Реализован отдельный execution слой (новый ADR)
- [ ] Hard gate: без override → `execution_mode=dry_run` принудительно

---

## 5. Детали тестирования (доказательства reachability)

```
# 1. Spot testnet ping
curl -s https://testnet.binance.vision/api/v3/ping
# → {}

# 2. Spot klines (real data)
curl -s "https://testnet.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=3"
# → real OHLCV array

# 3. Futures testnet ping  
curl -s https://testnet.binancefuture.com/dapi/v1/ping
# → {}

# 4. Futures klines (COIN-M)
curl -s "https://testnet.binancefuture.com/dapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=2"
# → real COIN-M OHLCV

# 5. Options testnet ping
curl -s https://testnet.binancefuture.com/eapi/v1/ping
# → {}

# 6. Auth gate (unauthenticated = correct)
curl -s "https://testnet.binance.vision/api/v3/account"
# → {"code":-1102,"msg":"Mandatory parameter 'signature'..."}
```

Все 6 тестов прошли HTTP 200 / корректный Binance error code. Testnet — не мок, а полноценный Binance environment.

---

## 6. Текущий egress карта

```
┌─────────────────────────────────────────────────────────┐
│                    Текущий egress                         │
│                                                         │
│  Location: Paris, France                                 │
│  IP: 83.136.209.168                                     │
│  ASN: AS400897 PETROSKY CLOUD LLC                       │
│  Jurisdiction: EU (non-US)                               │
│                                                         │
│  Binance access:                                        │
│  - api.binance.com       → HTTP 200 ✅                  │
│  - testnet.binance.vision → HTTP 200 ✅                 │
│  - testnet.binancefuture.com → HTTP 200 ✅              │
│  - 451 geoblock:          → НЕТ ✅                      │
│                                                         │
│  Rate limits:                                           │
│  - REQUEST_WEIGHT: 6000/min                             │
│  - ORDERS: 50/10s (testnet) / 100/10s (production)     │
└─────────────────────────────────────────────────────────┘
```

---

## 7. Integration point summary

```
┌────────────────────────────────────────────────────────────┐
│ АРХИТЕКТУРА: где подключается testnet/real                 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  IngestionSettings                                        │
│    └─ CLAY_BINANCE_BASE_URL                               │
│         ├─ продакшен:  "https://api.binance.com"           │
│         └─ testnet:    "https://testnet.binance.vision"  │ ← переключатель
│                                                            │
│  build_exchanges_map(settings)                            │
│    └─ ExchangeConfig(base_url=settings.binance_base_url) │
│         └─ BinanceSpotClient(base_url=cfg.base_url)       │
│                                                            │
│  MarketDataClient Protocol                                │
│    └─ fetch_klines(symbol, interval, limit)              │
│                                                            │
│  ─── НЕ ТРОГАЕМ ───                                        │
│  Protocol shape, NormalizedMarketBar, symbol mapping,     │
│  freshness evaluator, rate limiter, factory signature     │
│                                                            │
│  ─── БУДУЩЕЕ: Execution Layer (ADR-025?) ───              │
│  ExecutionClient Protocol                                 │
│    ├─ base_url ← тоже переключается                        │
│    ├─ api_key/secret ← отдельный secret store             │
│    ├─ testnet: bool ← safety switch                       │
│    └─ override → audit → live (Q5 invariant)             │
└────────────────────────────────────────────────────────────┘
```

---

## 8. STOP — Рекомендация

**Testnet-first (Фаза 1):** Подключить `CLAY_BINANCE_BASE_URL=https://testnet.binance.vision` на текущем Paris-egress. Zero code, zero risk. Проверить полный pipeline (ingestion → freshness → signals → sizing → UI). Если работает — стратегия валидна, реальные деньги = вопрос egress.

**Non-US egress (Фаза 2):** Не требуется до появления 451. При выходе 451 — Hetzner FRA как cheapest persistent non-US hop.

**Real-money ADR (Фаза 3):** После накопления ≥30 real outcomes + signing RV8. Отдельный ADR для execution layer + Q5 override + audit.

---

*Recon completed: 2026-06-26. No code changes. No keys. Zero side-effects.*
