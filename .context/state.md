# Текущее состояние Clay

## Завершено (предыдущие сессии)

- **S-KELLY-2-R:** ✅ CLOSED — EV-gate block proof
- **S-RISKLIMITS-1/1b:** ✅ ADR-021 draft+recon+v2 — 5 session-level risk limits L1-L5
- **S-DOCSYNC-2:** ✅ MERGED (ADR doc-sync B + 015→018 + master-index, M214)
- **S-RUNTIME-VERIFY-1:** ✅ Ring 1 GO + FOOTGUN B verified + live gates (M215/M216)
- **S-RUFF-2:** ✅ ruff 58→0 + durability assertions (M217)
- **S-Ф1b-2:** ✅ ai_agent_runs indexes I1/I2 + retention 180d + ADR-023 (M218)
- **S-REPLAY-5:** ✅ MERGED (M226) — replay harness + faithful resolution (ADR-024)
- **S-REPLAY-6:** ✅ MERGED (M227) — real-data soak 5433 (62 sessions, 42W/19L), guard, ADR-024 Accepted

## Завершено (эта сессия)

- **S-EGRESS-RECON-1:** ✅ CLOSED — testnet reachable из Paris (no 451), non-US egress map, ADR-008 integration point найден. Commit `e663019`.
- **S-EXEC-1 / ADR-025:** ✅ DRAFT — Execution Layer + Real-Money Gate (RV8) Proposed. testnet-first, 0 кода.
- **S-EXEC-2 / ADR-025 implementation:** ✅ MERGED — `TestnetExecutionClient` (ccxt) + integration. Commit `83fa532` (feat) + `43dce0c` (context/lock). Merge commit `fbd7c7f...`. Branch deleted.
- **S-EXEC-4 / Testnet smoke:** ✅ MERGED — live smoke на `testnet.binance.vision`, adapter fixes (timeout, cancel_order, url). Скрипт + gated pytest. Merge commit `b23ef5d...`. Branch deleted.

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD** | `b23ef5d` (S-EXEC-4 merge: testnet live smoke + adapter fixes) |
| **Tests** | **682 passed excl slow / 2 skipped** (682 offline green + smoke skip) |
| **Ruff** | **0** |
| **Alembic** | 0020 (source column, 5433) |
| **ADR** | 001–025 (025 Accepted) |
| **Demo (live)** | 20 sessions, 13W/7L, +4.95% |
| **Demo (5433 soak)** | 62 replay sessions, 42W/19L, b 1.0→1.3095, p 0→0.564 |

## ADR-статус

| № | Заголовок | Статус |
|---|-----------|--------|
| 020 | Fractional Kelly + EV-Gate | Accepted |
| 021 | Session-Level Risk Limits | Proposed |
| 023 | ai_agent_runs — Indexes + Retention | Accepted |
| 024 | Deterministic Replay + Trade Provenance | Accepted |
| 025 | Execution Layer + Real-Money Gate (RV8) | Accepted |

## Critical Context

- **Рабочая БД:** `127.0.0.1:5433` (podman clay_timescaledb, TS 2.27.1)
- **Pre-money код-цепочка:** ЗАКРЫТА ✅
- **S-REPLAY-6:** ✅ MERGED (M227)
- **Egress (Paris, FR):** Binance spot + futures testnet reachable, 451 absent
- **Testnet:** `testnet.binance.vision` / `testnet.binancefuture.com` — HTTP 200, live data, zero code to switch
- **ADR-025:** Accepted (v2), S-EXEC-2 + S-EXEC-4 merged. `backend/.env` untracked.
- **Testnet smoke:** order 9585437 — place 304ms, cancel 347ms, weight 55/6000, 0 fills, 0 контаминации калибровки.

## Pending (выбор Emma)

- **A)** ~~Real-money egress~~ → merged into execution layer path (ADR-025)
- **B)** Idea-bank: S-LLM-PARSE-1 и другие донор-слайсы
- **C)** Накопить ≥30 реальных live-исходов (S-EXEC-4 smoke доказал адаптер; следующий шаг — S-EXEC-3 override)
- **D)** ~~Execution layer ADR~~ → ADR-025 Accepted, S-EXEC-2 + S-EXEC-4 merged
- **→ Следующий слайс:** S-EXEC-3 (RV8 override sequence + LiveExecutionClient stub)
