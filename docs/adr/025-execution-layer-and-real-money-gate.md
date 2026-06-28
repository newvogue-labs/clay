# ADR-025: Execution Layer + Real-Money Gate (RV8)

- **Status:** Proposed
- **Date:** 2026-06-26
- **Supersedes:** —
- **Replaces:** —
- **Depends on:** ADR-008 (Exchange Abstraction), ADR-024 (Replay/Provenance)
- **Donor-ref:** —
- **v2:** 2026-06-26 — исправлена премиза про ccxt: добавлена как новая зависимость, ExecutionClient объявлен NEW protocol parallel to MarketDataClient

## Context

`DemoTradingService` — advisory/read-only recording: логирует `operator_action` в `demo_trade_records`, реальных ордеров **не отправляет**. Это безопасное состояние, но оно не execution layer — это manual journal.

**Гэп:**
- `can_open_binance: bool` в `WorkspaceStateSnapshot` — UI-флаг, блокирует старт сессии при `blocking_reason is None`. Это preflight, не execution gate.
- Hard real-money gate (RV8) — **не существует в коде**. «Override» — архитектурное намерение, не coded invariant.
- Без `ExecutionClient`-протокола переход на testnet или real-money требует bypass: прямые вызовы ccxt в session_control или ad-hoc скрипты.
- **ADR-008 реализован только для market-data:** `MarketDataClient` protocol → hand-rolled httpx-клиенты (`BinanceSpotClient`/`BybitClient`). Execution-под-слой (auth, order-API) — **явно отложен** в ADR-008: «отправка ордеров — отдельный, более тяжёлый под-слой». `ccxt` **отсутствует** в зависимостях (`pyproject.toml`).

**Триггер:** S-EGRESS-RECON-1 показал, что testnet (`testnet.binance.vision`) достижим из текущего Paris-egress. Prerequisite для testnet-валидации pipeline — абстракция, которую можно переключить на testnet без side-effects на prod.

## Decision

### (a) ExecutionClient Protocol (`NEW`, параллельно `MarketDataClient`)

Новый Protocol, независимый от `MarketDataClient` (ADR-008). Market-data ingestion (httpx, `BinanceSpotClient`) не затронута. `ExecutionClient` — отдельный слой для order management поверх ccxt:

```python
class ExecutionClient(Protocol):
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        *,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "GTC",
        client_order_id: str | None = None,
    ) -> OrderResult: ...

    def cancel_order(self, symbol: str, order_id: str) -> CancelResult: ...

    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus: ...

    def get_open_orders(self, symbol: str | None = None) -> list[OrderStatus]: ...

    def get_balances(self) -> list[Balance]: ...

    def get_recent_trades(
        self, symbol: str, *, limit: int = 500
    ) -> list[TradeFill]: ...
```

**Примечание:** Protocol — contract, не ccxt wrapper. Адаптер решает, как маппить поля на биржевой API.

### (b) CLAY_EXECUTION_MODE

Три режима, env var + immutable runtime config:

| Режим | Описание | Executor | Ключи | Риск |
|-------|----------|----------|-------|------|
| `dry_run` | Advisory-only, текущее поведение `DemoTradingService` | None | Не нужны | 0 |
| `testnet` | Реальные REST-ордера на testnet | `TestnetExecutionClient` | Testnet-ключи | 0 |
| `live` | Реальные ордера на prod | `LiveExecutionClient` | Prod-ключи | **High** |

**Default:** `dry_run`. **Нет авто-переключения** между режимами — только operator-initiated.

### (c) RV8 — Hard Real-Money Gate

Формализация в коде (ранее — architectural only):

**Q5 invariant:** система **НИКОГДА** не ставит real ордер без явного ручного override оператора.

```python
class ExecutionMode(str, Enum):
    DRY_RUN = "dry_run"
    TESTNET = "testnet"
    LIVE = "live"


class ExecutionConfig:
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    # override_state = None | "pending" | "confirmed"
    override_state: str | None = None
    override_actor: str | None = None  # operator identifier
    override_audit_id: str | None = None
    last_override_at: datetime | None = None
```

**Правила:**
1. `dry_run` → advisory-only, `DemoTradingService.log_current_trade()` работает как сейчас.
2. `testnet` → оператор инициирует через UI/CLI, аудит фиксирует `execution_mode=testnet`. Без override не нужно — testnet = 0 денежный риск.
3. `live` → **только** после Q5 override sequence:
   - UI: кнопка "Switch to live execution" → подтверждение → 2FA (опционально)
   - Backend: `execution_mode = "live"` фиксируется только при `override_state == "confirmed"` + валидный `override_audit_id`
   - Audit: `audit_writer.write("execution_mode.live.activated", {...})` — immutable append-only
   - Нет авто-switch: `live` не включается из config, env, или кода без override

**Согласование с `can_open_binance`:**
- `can_open_binance = True` только если `execution_mode != "live"` **или** `override_state == "confirmed"`.
- При `execution_mode = "live"` без override → `can_open_binance = False`, `blocking_reason = "Live execution requires Q5 override"`.

### (d) ExecutionConfig (отдельный от ExchangeConfig)

`ExchangeConfig` — market data ingestion (url, symbols, timeframes).  
`ExecutionConfig` — execution (mode, credentials, safety flags).

```python
@dataclass(frozen=True)
class ExecutionConfig:
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    exchange_id: str = "binance_spot"
    base_url: str = ""  # переопределяется адаптером
    api_key: str = ""   # secrets only, не в TOML
    api_secret: str = ""  # secrets only, не в TOML
    testnet: bool = False  # safety switch
    recv_window: int = 5000
```

**Secrets path:** только env (`CLAY_BINANCE_API_KEY`, `CLAY_BINANCE_API_SECRET`) или secret manager. Никогда — в репо, TOML, или логах.

### (e) Адаптер: TestnetExecutionClient (первый concrete)

Первый реализованный адаптер — testnet. Привязка:

```python
class TestnetExecutionClient:
    BASE_URL = "https://testnet.binance.vision"  # spot
    # Или: "https://testnet.binancefuture.com"  # futures

    def __init__(self, api_key: str, api_secret: str, recv_window: int = 5000):
        self._client = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "options": {"defaultType": "spot", "adjustForTimeDifference": True},
        })
        self._client.set_sandbox_mode(True)  # ccxt-native testnet
        self._client.urls["api"] = self.BASE_URL
```

**Интеграция:**
- Входная точка: `SessionControlService.start_session()` после preflight (ADR-021) + replay check (ADR-024).
- Переключатель: `execution_service = build_execution_client(execution_cfg)` — `None` при `dry_run`.
- `dry_run` → `DemoTradingService.log_current_trade()` (существующий путь).
- `testnet`/`live` → `execution_service.place_order(...)` → результат записывается в `demo_trade_records` через `ingest_result()`.

### (f) Запись fills в provenance

`source` колонка (ADR-024) расширяется:

```python
ProvenanceSource = Literal[
    "baseline",   # frozen Ring 1
    "live",       # demo outcomes (operator manual)
    "replay",     # replay harness
    "testnet",    # testnet fills (новое)
]
```

`testnet` fills — реальные исполнения в sandbox, **не** миксовать с `baseline`/`live` в калибровке до отдельного решения.

## Override expiry

- Каждый активный execution-override имеет конечный TTL. Источник истины — backend; срок выражается абсолютным таймстемпом `execution_override_expires_at` (ISO 8601, UTC) в `WorkspaceStateSnapshot` (см. ADR-001 addendum 2026-06-28).
- Backend проставляет `expires_at` при активации override и обнуляет (`null`) при revoke или по истечении.
- Клиент НЕ владеет сроком: показывает countdown от `expires_at` с поправкой на `server_time`, а по достижении нуля делает refetch snapshot и подчиняется ответу backend (никакого локального снятия override).
- Переходы режима (`dry_run → testnet → live`) и confirm/revoke — явные operator-действия (см. E3), не автоматические и не «тихие» (silent override остаётся out of scope).
- По истечении override execution-режим возвращается к безопасному базовому состоянию согласно real-money gate (Q5 invariant).

## Invariants

1. **Q5: no auto-execution.** Система никогда не переходит в `live` и не ставит ордер без явного override.
2. **Default = dry_run.** Если `CLAY_EXECUTION_MODE` не задан — advisory-only.
3. **Secrets never in repo.** `api_key`/`api_secret` — только env/secrets manager.
4. **Audit append-only.** Все переключения режимов → immutable audit log.
5. **Testnet ≠ Demo.** `testnet` fills (`source="testnet"`) не контаминируют `live` калибровку до отдельного решения.
6. **ADR-008 unchanged. Асимметрия осознанная:** Market data ingestion (`ExchangeConfig`, `MarketDataClient`, httpx-клиенты) — untouched. Execution-слой получает `ccxt` как новую зависимость: лёгкость на read-пути (`httpx`), надёжность на safety-critical order-пути (`ccxt` — testnet/prod endpoints, HMAC, rate limits, error taxonomy).

## Config

Новые env vars:

```bash
# Execution mode (default: dry_run)
CLAY_EXECUTION_MODE=dry_run | testnet | live

# Binance execution credentials (только для testnet/live)
CLAY_BINANCE_API_KEY=...
CLAY_BINANCE_API_SECRET=...

# Safety
CLAY_EXECUTION_ALLOW_LIVE_OVERRIDE=true  # future 2FA gate
```

Новая секция в `config/models.py`:

```python
class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["dry_run", "testnet", "live"] = "dry_run"
    exchange_id: str = "binance_spot"
    api_key: str = ""  # loaded from env, not TOML
    api_secret: str = ""  # loaded from env, not TOML
    testnet: bool = False
    recv_window: int = 5000
    allow_live_override: bool = False  # future 2FA/hardware gate
```

### Dependencies

Новая runtime-зависимость (добавляется в `backend/pyproject.toml`):

```toml
dependencies = [
  ...
  "ccxt>=4.3,<5.0",
]
```

**Обоснование:** `ccxt` — единственная зрелая библиотека, покрывающая Binance Spot/Futures testnet и prod с единым интерфейсом, HMAC-подписью, RecvWindow-sync, rate-limit учётом и classifying ошибок. Self-rolled order path — footgun на safety-critical пути.

## Consequences

### Positive
- Чёткое разделение data ingestion ↔ execution
- Testnet валидация pipeline без реального риска
- RV8 формализован в коде, не architectural intent
- Миграция `dry_run → testnet → live` = explicit, auditable steps
- `can_open_binance` становится execution-aware

### Negative
- Новый Protocol + adapters = surface area для багов (mitigated: testnet-first)
- Secrets management complexity (api_key rotation, testnet vs prod credentials)
- `testnet` fills требуют отдельного решения по включению в калибровку
- **Новая зависимость:** `ccxt` (async) добавляется в `pyproject.tomл` — первый ccxt-код в кодовой базе. Асимметрия осознанная: data ingestion остаётся на httpx (ADR-008), execution берёт на себя ccxt (testnet/prod endpoints, auth, HMAC, rate limits).

### Neutral
- `DemoTradingService.log_current_trade()` не меняется — `dry_run` = текущее поведение
- `MarketDataClient`, `ExchangeConfig`, ingestion pipeline — untouched

## Alternatives

1. **Оставить advisory-only** — отклонено: не позволяет валидировать signals → execution на реальном API. Testnet-first нужен для soak'а ≥30 fills без денежного риска.
2. **Вшить execution в `SessionControlService`** — отклонено: single responsibility, execution = отдельный domain.
3. **Написать собственный Binance-клиент вместо ccxt** — отклонено: добавляем `ccxt` как явную зависимость для execution-слоя. ccxt покрывает testnet/prod переключение, HMAC-подпись, recvWindow, rate limits, error taxonomy. Self-rolled order path — footgun на safety-critical пути.
4. **Сделать `live` default с env-disable** — отклонено: нарушает Q5. `dry_run` = default потому что safe.

## Open Questions

| Q | Тема | Вердикт |
|---|------|---------|
| Q1 | Futures vs spot для первого adapter | **PENDING** — spot=проще, futures=больше возможностей. Предлагаю spot-first. |
| Q2 | 2FA/hardware gate для live override | **FUTURE** — `allow_live_override = true` зарезервирован, реализация — отдельный slice. |
| Q3 | testnet fills в калибровку | **FUTURE ADR** — отдельное решение. Пока `testnet` = изолированный источник. |
| Q4 | ccxt dependency | **RESOLVED** — `ccxt` (async) добавляется в `pyproject.toml` как новая зависимость execution-слоя. Асимметрия: data-ingestion остаётся на httpx (ADR-008). |
| Q5 | Override persistence | **ADR-025 scope** — `ExecutionConfig` хранится в runtime/memory; persistent override log — через `audit_writer`. |
| Q6 | Session restart при mode switch | **RESOLVED** — переключение режима = остановка текущей сессии + проверка preflight. |

## Ссылки

- ADR-008: `docs/adr/008-exchange-abstraction-and-multi-exchange-portability.md`
- ADR-024: `docs/adr/024-deterministic-replay-and-trade-provenance.md`
- S-EGRESS-RECON-1: `docs/mission-control/egress-recon/S-EGRESS-RECON-1.md`
- `backend/src/clay/demo_trading/service.py` — advisory-only service
- `backend/src/clay/workspace/models.py:23` — `can_open_binance`
- `backend/src/clay/workspace/service.py:272` — `can_open_binance` вычисление

---

## Разбивка на impl-слайсы

| Слайс | Описание | Зависимости | Оценка |
|-------|----------|-------------|--------|
| **S-EXEC-1** | ADR-025 + `ExecutionClient` Protocol + `ExecutionConfig` + `build_execution_client()` skeleton. `dry_run` adapter = pass-through (no-op). | — | |
| **S-EXEC-2** | `TestnetExecutionClient` (ccxt-based) + integration в `SessionControlService`. `execution_mode=testnet` → реальные REST-ордера. | S-EXEC-1 | |
| **S-EXEC-3** | RV8 gate: `live` override sequence (UI → audit → confirm) + `can_open_binance` integration. `LiveExecutionClient` stub. | S-EXEC-1 | |
| **S-EXEC-4** | Soak ≥30 testnet fills, provenance (`source="testnet"`), калибровка dry-run. | S-EXEC-2 | |
| **S-EXEC-5** | Non-US egress (Hetzner VPS) — deferred до 451 или prod-necessity. | — | |

**Порядок:** S-EXEC-1 → (S-EXEC-2 + S-EXEC-3 параллельно) → S-EXEC-4 → S-EXEC-5.

## Не-цели (out of scope)

- Real-money торговля и реальные prod-ключи
- 2FA/hardware key / multisig для Героя (зарезервировано)
- Futures adapter (spot-first)
- Автоматическая рекалибровка по триггеру
- UI для execution (предполагается existing trading workspace)
