# Отчёт: сессия 2026-06-26 — S-EXEC-2 merged, STOP перед S-EXEC-4

## Что сделано

### S-EXEC-2 — MERGED — TestnetExecutionClient + интеграция

Merge commit `fbd7c7f...` (no-ff) в `main`. Branch `feat/testnet-execution` удалена (локальная и remote).

#### Дополнительный коммит

- `eabba54` security: untrack `backend/.env` из git index (файл сохранён в working tree).

### Выполнено по декретам (S-EXEC-2)

- **D1 Mode fail-safe:** `ExecutionConfig.from_env()` — default `dry_run`; invalid/missing → `dry_run`. `live` → `ExecutionConfigError` (не реализован). Потолок слайса = testnet.
- **D2 ccxt в pyproject.toml:** `ccxt>=4.3,<5.0` runtime dep. Асимметрия: data-ingestion на httpx (ADR-008), execution на ccxt (testnet/prod switching, auth, rate limits).
- **D3 Ключи только env:** `CLAY_BINANCE_TESTNET_API_KEY/SECRET` — только env, не в репо/логах. `mode=testnet` без ключей → громкий `ExecutionConfigError` (не тихий фолбэк).
- **D4 Manual-only Q5:** `SessionControlService` **не импортирует** `clay.execution`, `start_session` не вызывает `place_order`. Auto-execution путь **не разведён**. Integration deferred intentionally.
- **D5 Provenance testnet:** `source` Literal расширен на `"testnet"`. `DEFAULT_READ_SCOPE = frozenset({"baseline","live"})` — **не тронут**. Testnet НЕ попадает в default калибровку p/b (ADR-024 §d инвариант сохранён).
- **D6 Идемпотентность:** `clientOrderId` → `newClientOrderId`. Partial-fill → `PartialFillError`. Reject/timeout → доменные exceptions. Ошибки ccxt классифицируются без тихого swallow.
- **D7 Egress:** testnet из Paris = HTTP 200 (M228). VPS не нужен.
- **D8 Тесты:** unit (factory, config, binance mock ccxt) + workspace integration (`test_workspace_execution.py`). Integration smoke — deferred.
- **D10 can_open_binance execution-aware:** `live` без override → `False`; `testnet` → `True` при preflight ok; `dry_run` → нет impact.

#### 5/5 Confirmations (Emma checkpoint)

1. **Регресс-числа:** +3 тестовых файла, `uv.lock` +499 строк (ccxt resolved), ruff 0, py_compile OK.
2. **DEFAULT_READ_SCOPE не тронут:** `git diff repositories_demo.py = пусто`. Testnet исключён из default калибровки.
3. **ccxt pin-диапазон:** `"ccxt>=4.3,<5.0"` в `pyproject.toml`.
4. **mode=testnet без ключей → громкий fail:** `test_build_execution_client_testnet_missing_keys_raises` → `ExecutionConfigError`.
5. **SessionControlService integration deferred:** нет импорта `clay.execution`, нет вызова `place_order` в `start_session`. Manual-only Q5 через отсутствие проводки.

#### Безопасность

- `backend/.env` был tracked → удалён из индекса (`git rm --cached`), `.gitignore` покрывает корень. Файл сохранён в working tree.

## Итог

**HEAD `eabba54` (S-EXEC-2 merge + security fix). main зелёный, pushed.**

ADR-025 Accepted, S-EXEC-2 merged. **Next: S-EXEC-4 (testnet integration smoke).**

Блокер S-EXEC-4: нужны `CLAY_BINANCE_TESTNET_API_KEY/SECRET` (генерация на testnet.binance.vision, отдельный аккаунт).
