---
date: 2026-06-26
from: Agent (Emma Clay)
session: S-EXEC-2 review (5 confirmations pending merge)
---

## Что сделано

- **ADR-025:** Accepted (v2).
- **S-EXEC-2:** ✅ CLOSED — TestnetExecutionClient (ccxt) + integration + 5 confirmations.
  - Branch `feat/testnet-execution`, commit `83fa532`.
  - ccxt добавлен в `pyproject.toml` (runtime dep, pin>=4.3,<5.0).
  - `ExecutionClient` Protocol (NEW, parallel to MarketDataClient).
  - `ExecutionConfig` (env-driven, не в TOML).
  - `WorkspaceStateSnapshot` execution-aware: `live` без override → `can_open_binance=False`.
  - Provenance source расширен на `"testnet"` (VARCHAR(16) вмещает, DEFAULT_READ_SCOPE={baseline,live} unchanged).
  - Декреты S-EXEC-2 выполнены: mode fail-safe, ключи только env, manual-only Q5, идемпотентность clientOrderId, partial-fill explicit.
  - **5 confirmations предоставлены Emma:**
    1. Регресс-числа: +3 тестовых файла, uv.lock +499 строк (ccxt resolved), ruff 0, py_compile OK
    2. DEFAULT_READ_SCOPE = `frozenset({"baseline","live"})` **не тронут** — testnet исключён из default калибровки (git diff repsitory_demo.py = пусто)
    3. ccxt pin `>=4.3,<5.0` в `pyproject.toml`
    4. test_build_execution_client_testnet_missing_keys_raises → Explicit ExecutionConfigError, не фолбэк
    5. SessionControlService НЕ импортирует execution — auto-execution путь не разведён, integration сознательно deferred

## Следующий шаг

**Merge authorized** после 5 подтверждений.

Приоритет: **S-EXEC-4 (testnet smoke integration)** перед S-EXEC-3 (override sequence).
Обоснование: адаптер должен быть сетево доказан до строительства high-risk override пути.

Для S-EXEC-4 нужно:
- `CLAY_BINANCE_TESTNET_API_KEY/SECRET` (testnet аккаунт)
- Manual/integration smoke test: разместить+отменить микро-ордер на testnet
- Прокоммитить `source="testnet"` provenance → доказать изоляцию

## Блокеры

- Testnet ключи ещё не настроены (нужно `CLAY_BINANCE_TESTNET_API_KEY/SECRET`).
- Integration smoke против реального testnet — manual, requires keys.

## На заметку

- HEAD: `83fa532` (feat/testnet-execution)
- ADR: `docs/adr/025-execution-layer-and-real-money-gate.md` Accepted
- Execution пакет: `backend/src/clay/execution/`
- Тесты: `backend/tests/execution/` (2 файла), `backend/tests/workspace/test_workspace_execution.py` (1 файл)
