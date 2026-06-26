---
date: 2026-06-26
from: Agent (Emma Clay)
session: S-EXEC-2 merged, awaiting S-EXEC-4
---

## Что сделано

- **ADR-025:** Accepted (v2).
- **S-EXEC-2:** ✅ MERGED — TestnetExecutionClient (ccxt) + integration.
  - Merge commit `fbd7c7f...` (no-ff) в `main`.
  - Branch `feat/testnet-execution` удалена.
  - ccxt добавлен в `pyproject.toml` (runtime dep, pin>=4.3,<5.0).
  - `ExecutionClient` Protocol (NEW, parallel to MarketDataClient).
  - `ExecutionConfig` (env-driven, не в TOML).
  - `WorkspaceStateSnapshot` execution-aware: `live` без override → `can_open_binance=False`.
  - Provenance source расширен на `"testnet"` (DEFAULT_READ_SCOPE={baseline,live} unchanged).
  - 5/5 confirmations предоставлены и закрыты.
  - **Безопасность:** `backend/.env` был tracked → удалён из индекса (`git rm --cached`), `.gitignore` покрывает. Файл сохранён в working tree.

## Следующий шаг

**S-EXEC-4: Testnet integration smoke** (branch `feat/testnet-smoke`).
- Non-marketable limit-ордер (buy-limit ниже рынка) → query → cancel → query gone.
- Testnet ONLY (`set_sandbox_mode(True)`), микро-объём.
- Gated-тест (`slow`/manual, сетевой), НЕ в CI-дефолте.
- Adapter-level only: НЕ пишет в `demo_trade_records` (0 контаминации калибровки).
- Evidence: order id, статусы, latency, rate-limit weight-заголовки.

## Блокеры

- Нужны `CLAY_BINANCE_TESTNET_API_KEY/SECRET` (отдельный testnet-аккаунт, не прод).
- Ключи кладутся в `backend/.env` (не tracked), через тот же механизм что `CLAY_DATABASE_URL`.

## На заметку

- HEAD: `eabba54` (main, merge + security fix)
- ADR: `docs/adr/025-execution-layer-and-real-money-gate.md` Accepted
- Execution пакет: `backend/src/clay/execution/`
- Тесты: `backend/tests/execution/`, `backend/tests/workspace/test_workspace_execution.py`
