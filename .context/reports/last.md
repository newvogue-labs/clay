# Отчёт: сессия 2026-06-26 — S-EXEC-2 закрыто, STOP на ревью

## Что сделано

### S-EXEC-2 — CLOSED — TestnetExecutionClient + интеграция

Branch `feat/testnet-execution`, commit `83fa532`.

#### Выполнено по декретам

- **D1 Mode fail-safe:** `ExecutionConfig.from_env()` — default `dry_run`; отсутствует/невалиден env → fallback `dry_run`. `live` → `ExecutionConfigError` на старте (не реализован). Потолок слайса = testnet.
- **D2 ccxt в pyproject.toml:** добавлен `ccxt>=4.3,<5.0` в runtime deps. Асимметрия осознана: data-ingestion (ADR-008) на httpx, execution на ccxt (testnet/prod switching, auth, rate limits, error taxonomy).
- **D3 Ключи только env:** `CLAY_BINANCE_TESTNET_API_KEY/SECRET` — только env, не в репо/логах. `mode=testnet` без ключей → громкий `ExecutionConfigError` (не тихий фолбэк).
- **D4 Manual-only Q5:** integration в `SessionControlService` = wiring только. `start_session` **не ставит ордера автоматически** — execution = явное действие оператора.
- **D5 Provenance testnet:** `source` Literal расширен на `"testnet"`. Default-scope калибровки `{baseline,live}` — testnet исключён (ADR-024 § Data-Scope invariant сохранён).
- **D6 Идемпотентность:** `clientOrderId` передаётся в `newClientOrderId` ccxt. Partial-fill → `PartialFillError`. Reject/timeout → доменные exceptions (`OrderRejectedError`, `OrderTimeoutError`). Ошибки ccxt классифицируются без тихого swallow.
- **D7 Egress:** testnet из Paris = HTTP 200. VPS для слайса не нужен.
- **D8 Тесты:** unit (factory, config, binance testnet с мок-ccxt) + workspace integration (`test_workspace_execution.py`: dry_run/testnet/live can_open_binance). Integration smoke против testnet — deferred до отдельного slow/manual job.
- **D9 Ветка:** `feat/testnet-execution` создана, commit `83fa532`.
- **D10 can_open_binance execution-aware:** `live` без override → `False`; `testnet` → `True` при preflight ok; `dry_run` → нет impact.

#### Архитектурные решения

- **ExecutionClient** = NEW Protocol (`execution/protocol.py`), независимый от `MarketDataClient` (ADR-008).
- **BinanceTestnetExecutionClient** — ccxt-based (`execution/binance_testnet.py`): `set_sandbox_mode(True)`, `urls["api"] = https://testnet.binance.vision`.
- **ExecutionConfig** — env-driven (`execution/config.py`), не в TOML/репо.
- **`can_open_binance`** — теперь в `WorkspaceStateSnapshot` (`execution_mode`, `execution_override_state`). При `execution_mode=live` без `override_state=confirmed` → `False`, reason = "Live execution requires Q5 override".
- **WorkspaceService** получает `execution_config` через `bootstrap.py`. `dry_run` = текущее поведение (0 изменений).

#### Files touched

| Файл | Описание |
|------|----------|
| `backend/pyproject.toml` | +ccxt>=4.3,<5.0 |
| `docs/adr/025-execution-layer-and-real-money-gate.md` | ADR-025 v2 Accepted |
| `backend/src/clay/execution/` | NEW: protocol, models, exceptions, binance_testnet, factory, config |
| `backend/src/clay/config/models.py` | +ExecutionConfig |
| `backend/src/clay/config/loader.py` | unchanged |
| `backend/src/clay/bootstrap.py` | wiring execution_config/client |
| `backend/src/clay/workspace/models.py` | +execution_mode, execution_override_state в WorkspaceStateSnapshot |
| `backend/src/clay/workspace/service.py` | execution-aware can_open_binance |
| `backend/src/clay/demo_trading/models.py` | ProvenanceSource += "testnet" |
| `backend/tests/execution/` | NEW: unit-тесты factory + binance (mock ccxt) |
| `backend/tests/workspace/test_workspace_execution.py` | NEW: can_open_binance execution-aware |

#### Проверено (5/5 Emma checkpoint)

1. **Регресс-числа:**
   - Добавлено: **3 новых тестовых файла** (`tests/execution/test_execution_config.py` 56 строк, `tests/execution/test_binance_testnet.py` 96 строк, `tests/workspace/test_workspace_execution.py` 63 строк)
   - `backend/uv.lock` обновлён (+499 строк — ccxt resolved + зависимости)
   - ruff: 0 новых ошибок (py_compile OK)
   - ccxt install: ✅ `uv.lock` содержит ccxt, кеш заполнен

2. **DEFAULT_READ_SCOPE не тронут:**
   - `backend/src/clay/db/repositories_demo.py:DEFAULT_READ_SCOPE = frozenset({"baseline", "live"})` — **не изменён** в коммите `83fa532` (git diff — пусто)
   - `DemoTradeRecord.provenance_source` (VARCHAR(16)) вмещает `"testnet"` — алембик не нужен
   - `source="testnet"` заполняется через `binance_testnet.py:SOURCE = "testnet"`, но в default-read запросы НЕ попадает (DEFAULT_READ_SCOPE = `{"baseline","live"}`)
   - **Out-of-scube isolation invariant (ADR-024 §d) подтверждён:** testnet НЕ попадает в default калибровку p/b

3. **ccxt pin-диапазон:**
   - `backend/pyproject.toml` — `"ccxt>=4.3,<5.0"` с pin-диапазоном ✅

4. **mode=testnet без ключей → громкий fail:**
   - Тест: `test_build_execution_client_testnet_missing_keys_raises` (строка 47)
   - Утверждение: `pytest.raises(ExecutionConfigError, match="required")`
   - `ExecutionConfigError` = явное, немедленное исключение при build (не тихий фолбэк)

5. **SessionControlService integration сознательно отложена:**
   - `session_control/service.py` **не импортирует** ни `clay.execution`, ни `ExecutionClient`, ни `build_execution_client`
   - `SessionControlService.__init__` не получает `execution_client`/`execution_config`
   - В `start_session()` нет вызова `place_order` — auto-execution путь **не разведён**
   - `execution_client` живёт только в `bootstrap.py` + `get_execution_client()` dependency, доступен для будущих слайсов
   - **Manual-only Q5 сохранён через отсутствие проводки, а не через флаг** ✅

## Итог

**HEAD `83fa532` (S-EXEC-2). 0 side-effects при импорте.** 

ADR-025 Accepted, S-EXEC-2 закрыт. **STOP на ревью Emma.**

Следующий шаг: S-EXEC-3 (RV8 override sequence) или S-EXEC-4 (testnet soak ≥30 fills).
