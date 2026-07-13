---
tags:
  - execution
  - architecture-v2
---

# ADR-032: Exchange Execution Adapter (Multi-Venue)

- **Status:** Proposed
- **Date:** 2026-07-12
- **Supersedes:** —
- **Replaces:** —
- **Depends on:** ADR-025 (Execution Layer + Real-Money Gate), ADR-008 (Exchange Abstraction & Multi-Exchange Portability — идея портируемости)
- **Donor-ref:** ccxt, vn.py, Hummingbot, Nautilus, Barter, freqtrade (pattern-only), daily_stock_analysis

## Context

ADR-025 ввёл `ExecutionClient` Protocol и первый конкретный адаптер `TestnetExecutionClient`, который **жёстко зашит на одну биржу**: `ccxt.binance(...)`, `set_sandbox_mode(True)`, spot-URL в константе класса. Это корректно для testnet-bring-up (S-TESTNET-1, закрыт @ `d5bb2a9`), но не масштабируется:

- **Нет доменного порта.** `ExecutionClient` возвращает DTO, но ccxt-специфика (dict-ответы, `params`, ccxt-исключения) может протекать в domain при добавлении второй биржи.
- **Нет модели возможностей венью.** Мин/макс объём, шаг цены/количества, precision-mode, поддержка типов ордеров различаются per-venue и **per-symbol** — сейчас нигде не формализовано.
- **Нет идемпотентности/reconciliation.** Таймаут после отправки ордера сейчас неотличим от отказа — на safety-critical пути это footgun (двойное исполнение).

**Связь с ADR-008 / ADR-025.** ADR-008 — data-plane (market-data, httpx), **заморожен** (`mc-archive`, Proposed) и остаётся as-is (ADR-025 §Invariants-6: «ADR-008 unchanged, асимметрия осознанная»). Аспирация *multi-exchange portability* из 008 реализуется здесь, но **на execution-плоскости** и в линии ADR-025. Поэтому ADR-032 — **обобщение ADR-025**, а не супер-сед ADR-008.

**Триггер.** Track A demo bring-up (ручной GUI, без денег): Bybit demo → Binance Demo (`demo.binance.com`) → OKX demo. Для >1 венью нужен порт, а не второй хардкод.

## Decision

### (a) `ExchangeAdapter` — доменный async-порт; ccxt = driver ВНУТРИ

Единый доменный Protocol; ccxt живёт **только внутри** адаптера и **не протекает** наружу (ни dict-ответов, ни ccxt-исключений, ни `params`). Форма порта — по образцу vn.py (MIT), execution-семантика — из ADR-025.

```python
class ExchangeAdapter(Protocol):
    environment: Environment

    async def validate_order(self, req: OrderRequest, rules: MarketRules) -> None: ...
    async def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest: ...
    async def place_order(self, req: OrderRequest) -> OrderAck: ...
    async def cancel_order(self, symbol: Symbol, venue_order_id: str) -> None: ...
    async def get_order(self, symbol: Symbol, venue_order_id: str) -> OrderState: ...
    async def get_open_orders(self, symbol: Symbol | None = None) -> list[OrderState]: ...
    async def reconcile_orders(self, symbol: Symbol, since: datetime) -> list[OrderState]: ...
    async def get_balances(self) -> list[Balance]: ...
    async def get_market_rules(self, symbol: Symbol) -> MarketRules: ...
```

### (b) Доменные DTO (frozen, `Decimal`) + StrEnum

Все денежные/количественные величины — `Decimal`, никаких float. DTO — `@dataclass(frozen=True)`.

```python
class Environment(StrEnum):   # immutable, задаётся при построении адаптера
    PRODUCTION = "production"; TESTNET = "testnet"; DEMO = "demo"; PAPER = "paper"

class OrderSide(StrEnum):  BUY = "buy"; SELL = "sell"
class OrderType(StrEnum):  MARKET = "market"; LIMIT = "limit"; STOP_LIMIT = "stop_limit"
class TimeInForce(StrEnum): GTC = "gtc"; IOC = "ioc"; FOK = "fok"

class OrderState(StrEnum): NEW="new"; PARTIALLY_FILLED="partially_filled"; \
    FILLED="filled"; CANCELED="canceled"; REJECTED="rejected"; EXPIRED="expired"
```

`OrderRequest` несёт обязательный `client_order_id` (идемпотентность, см. (e)).

### (c) `MarketRules` — capability-overlay per market-type + per-symbol

Нормализация-контракт: min/max amount, min/max price, min cost (notional), precision-mode (tick/step vs significant-digits), поддерживаемые `OrderType`/`TimeInForce`. Паттерн «capability-флаги на подкласс» — clean-room по `_ft_has` из freqtrade (**GPL — только паттерн, код НЕ копировать**).

### (d) Контракт-функции

`validate_order` / `quantize_order` / `reconcile_orders` — часть порта (a), реализуются через `MarketRules`. `quantize` округляет к сетке венью ПЕРЕД отправкой; `validate` бросает доменную ошибку до сети.

### (e) Идемпотентность + reconciliation (🔴 mandatory)

- Каждый `place_order` несёт `client_order_id` (идемпотентный ключ).
- **Таймаут после отправки ордера ≠ retryable.** Он поднимает `AmbiguousExecutionError` — состояние неизвестно. Прежде чем что-либо повторять, обязателен `reconcile_orders(...)` по `client_order_id`. **Слепой retry запрещён** (риск двойного исполнения). Паттерн команда/событие + reconciliation — из Nautilus (**LGPL ⚠️ — паттерн, не линковать код**) и order-tracker/client-id из Hummingbot (Apache).

### (f) Таксономия ошибок (two-tier + Ambiguous)

Доменные исключения, ccxt-ошибки маппятся внутри адаптера:
- **Retryable** (transient): сеть, rate-limit, 5xx — безопасен backoff-retry.
- **Terminal** (deterministic): отклонён, недостаточно средств, невалидный символ — retry бессмыслен.
- **Ambiguous**: `AmbiguousExecutionError` — только через reconcile (см. e).

Разделение request-ошибок и account-ошибок — по образцу Barter (MIT).

### (g) Resilience: CircuitBreaker + fallback-chain (🔴 read-only)

CircuitBreaker перед венью-вызовами; выбор реализации (паттерн из daily_stock_analysis, MIT — read-only — vs `pybreaker`) фиксируется в build_spec слайса. **Fallback НИКОГДА не роутит `place_order`/`cancel_order` на другую венью** — только read-операции (`get_order`, `get_balances`, `reconcile`). Ордер-плоскость венью-sticky.

### (h) Первый конкретный адаптер — Binance; per-venue подкласс = capability-overlay

`BinanceExecutionAdapter(ExchangeAdapter)` замещает хардкод из ADR-025 `TestnetExecutionClient`; `Environment` выбирает endpoint (в т.ч. `demo.binance.com` для Track A). Следующие венью (Bybit, OKX) = подклассы с override `MarketRules`/capability-флагов, без дублирования порта.

## Invariants

1. **Async-only.** Весь порт — `async`. Никаких sync-вызовов на сетевом пути.
2. **Decimal everywhere.** Деньги/объёмы — `Decimal`. Float запрещён в DTO и арифметике.
3. **Frozen DTO.** Все доменные DTO иммутабельны.
4. **No driver leak.** ccxt (dict/exceptions/`params`) не покидает адаптер.
5. **Environment immutable.** Задаётся при построении, не меняется в рантайме.
6. **Idempotency + reconcile-before-retry.** Таймаут = `AmbiguousExecutionError`, только reconcile; слепой retry запрещён.
7. **Fallback read-only.** Ордер-плоскость никогда не роутится на другую венью.
8. **Q5 сохраняется.** ADR-025 real-money gate не ослабляется; реальных денег нет, пока адаптер не пройдёт `high-risk-operation-ready`.
9. **ADR-008/data-plane untouched.** Market-data (httpx) не затрагивается.

## Donor verdicts

| Донор | Лицензия | Вердикт | Что берём |
|---|---|---|---|
| ccxt | MIT | ✅ driver | внутри адаптера: endpoints, HMAC, rate-limit, error-класс |
| vn.py | MIT | ✅ port-shape | форма доменного порта |
| Hummingbot | Apache-2.0 | ✅ pattern+code-ref | order-tracker, quantization, client-id |
| Nautilus | LGPL | ⚠️ pattern-only | command/event + reconciliation (не линковать) |
| Barter | MIT | ✅ pattern | split request/account errors |
| freqtrade | GPL | 🛑 pattern-only | `_ft_has` capability-overlay (clean-room, код НЕ копировать) |
| daily_stock_analysis | MIT | ✅ pattern | CircuitBreaker (read-only) |
| ArkhasFlow | — | ⛔ DROP | — |
| Jesse / backtrader | (backtrader GPL) | ⛔ ≈nothing | — |

## Config

Без новых env в этом ADR: переиспользуются `CLAY_EXECUTION_MODE` и `CLAY_BINANCE_API_*` (ADR-025). Мультивенью-креды (Bybit/OKX) вводятся в build_spec соответствующего слайса, всегда через env/secret-manager, никогда в TOML/репо/логах.

## Consequences

**Positive:** единый порт вместо N хардкодов; тестируемость (fake-adapter); идемпотентность/reconcile закрывают double-execution footgun; capability-overlay ловит venue-специфику до сети.
**Negative:** рост surface area (mitigated: testnet/demo-first, один адаптер за слайс); маппинг ccxt→domain на каждой венью — ручная работа.
**Neutral:** ADR-025 dry_run/testnet поведение сохраняется; data-plane не тронут.

## Alternatives

1. **Второй хардкод (ещё один `*ExecutionClient`)** — отклонено: копипаст, протечка ccxt, нет reconcile.
2. **Прямой ccxt в session/service** — отклонено: нарушает single-responsibility и ADR-025 (b).
3. **Синхронный порт** — отклонено: сетевой safety-critical путь требует async.
4. **Fallback ордеров на другую венью** — отклонено: риск двойного/расхождённого исполнения; ордер-плоскость sticky.
5. **float для цен/объёмов** — отклонено: ошибки округления на деньгах.

## Open Questions

| Q | Тема | Вердикт |
|---|---|---|
| Q1 | CircuitBreaker: daily_stock_analysis-паттерн vs `pybreaker` | **PENDING** — решить в build_spec первого слайса |
| Q2 | Порядок венью Track A | Bybit demo → Binance Demo → OKX demo |
| Q3 | Futures vs spot | spot-first (наследует ADR-025 Q1) |
| Q4 | Мультивенью-креды secret-path | build_spec per-venue; env/secret-manager only |

## Ссылки

- ADR-025: `docs/adr/025-execution-layer-and-real-money-gate.md`
- ADR-008: `docs/mission-control/adrs/adr-008-exchange-abstraction-and-multi-exchange-portability.md` (frozen)
- ADR-024: `docs/adr/024-deterministic-replay-and-trade-provenance.md`
- Донор-реестр: Notion «Донор-реестр»
- `backend/src/clay/execution/protocol.py`, `.../models.py` — текущий ExecutionClient (ADR-025)

---

## Разбивка на impl-слайсы (эпик E14)

| Слайс | Описание | Зависимости |
|---|---|---|
| **S-ADAPT-1** | `ExchangeAdapter` Protocol + доменные DTO (frozen, Decimal) + StrEnum + `MarketRules` + доменная error-таксономия. Без сети. | — |
| **S-ADAPT-2** | `BinanceExecutionAdapter` (ccxt driver внутри) замещает `TestnetExecutionClient`; `validate`/`quantize`/`place`/`get`/`cancel`. | S-ADAPT-1 |
| **S-ADAPT-3** | Идемпотентность + `reconcile_orders` + `AmbiguousExecutionError` (reconcile-before-retry). | S-ADAPT-2 |
| **S-ADAPT-4** | CircuitBreaker + read-only fallback-chain (Q1 решается тут). | S-ADAPT-2 |
| **S-ADAPT-5** | Второй венью-подкласс (Bybit demo) через capability-overlay — доказать переносимость. | S-ADAPT-3, S-ADAPT-4 |

## Errata 2026-07-13 (S-ADAPT-2C)

- **S-ADAPT-2C completed.** `BinanceExecutionAdapter` — боевой путь для `POST /testnet-probe`. Legacy `ExecutionClient`/`*TestnetExecutionClient`/factory/protocol/models удалены.
- **`validate`/`quantize` — sync (не async).** Doc fix: протокол объявляет `validate_order` и `quantize_order` как sync (в `ExchangeAdapter` port они sync). ADR-032 §(a) приводился с async-аннотацией — исправлено в имплементации.
- **`OrderSnapshot` vs `OrderState`:** ADR-032 §(a) `get_order` возвращает `OrderState` — исправлено: возвращает `OrderSnapshot` (полные данные).
- **`SIGNIFICANT_DIGITS`:** не реализован числово — `NotImplementedError` (долг для S-ADAPT-5+).
- **`MIN_NOTIONAL`:** legacy filterType поддержан (fallback в `get_market_rules`).
- **`price="0"` edge:** market-order `price` → `None` (не `Decimal("0")`).

**Порядок:** S-ADAPT-1 → S-ADAPT-2 → S-ADAPT-2C → (S-ADAPT-3 + S-ADAPT-4) → S-ADAPT-5.

## Errata 2026-07-13 (S-ADAPT-3)

- **S-ADAPT-3 completed.** `ResilientExecutionAdapter` — resilience wrapper через композицию (`execution/resilience.py`). Оборачивает любой `ExchangeAdapter`, reconcile-before-retry для `place_order`, bounded backoff-retry для read-операций на `TransientAdapterError`.
- **Resilience wrapper — композиция, не наследование.** `ResilientExecutionAdapter(inner: ExchangeAdapter)` делегирует через `self._inner`, ноль ccxt-импорт в resilience.py. `isinstance(ResilientExecutionAdapter(fake), ExchangeAdapter)` → True (`@runtime_checkable`).
- **Reconcile-before-retry через reconcile_orders + cid-фильтр.** Порт НЕ расширен — используется существующий `reconcile_orders(symbol, since)` + фильтр по `client_order_id`. `_ack_from_snapshot()` конвертирует `OrderSnapshot` → `OrderAck` (дропает `executed_qty`).
- **Q1(CircuitBreaker) остаётся за S-ADAPT-4.** resilience wrapper не содержит CB/fallback logic.
- **Route V7: `AmbiguousExecutionError` → HTTP 409.** Добавлен `except AmbiguousExecutionError` в `POST /testnet-probe` ВЫШЕ generic `except AdapterError → 422`. Audit: `execution.testnet_probe_ambiguous` durable write.
- **Bootstrap: `ResilientExecutionAdapter(BinanceExecutionAdapter(...))`.** `get_execution_client()` возвращает wrapper; тип-контракт `ExchangeAdapter | None` сохранён.
- **`max_place_attempts` = потолок ВСЕХ place-вызовов** (initial + re-places). При `max_place_attempts=2`: 1 initial + 1 re-place максимум. Цикл `range(max_place_attempts - 1)`.

**Порядок:** S-ADAPT-1 → S-ADAPT-2 → S-ADAPT-2C → S-ADAPT-3 → (S-ADAPT-4 + S-ADAPT-5).

## Не-цели (out of scope)

- Реальные деньги / prod-ключи (за гейтом `high-risk-operation-ready` + Q5).
- Автоматический роутинг ордеров между венью.
- Data-plane изменения (ADR-008 untouched).
- Futures adapter (spot-first).
