# Текущее состояние Clay

## Завершено (предыдущие сессии)

- **S-KELLY-2-R:** ✅ CLOSED — EV-gate block proof
- **S-RISKLIMITS-1/1b:** ✅ ADR-021 draft+recon+v2 — 5 session-level risk limits L1-L5
- **S-DOCSYNC-2:** ✅ MERGED (ADR doc-sync B + 015→018 + master-index, M214)
- **S-RUNTIME-VERIFY-1:** ✅ Ring 1 GO + FOOTGUN B verified + live gates (M215/M216)
- **S-RUFF-2:** ✅ ruff 58→0 + durability assertions (M217)
- **S-Ф1b-2:** ✅ ai_agent_runs indexes I1/I2 + retention 180d + ADR-023 (M218)

## Завершено (эта сессия)

- **S-REPLAY-5:** ✅ MERGED (M226, `b703ea2`) — replay harness + faithful resolution (ADR-024)
- **S-REPLAY-6 доводка:** ✅ CLOSED — real-data soak на 5433 (62 sessions, 42W/19L, b:1.0→1.309, p:0→0.564), clock-desync guard, ADR-024 Accepted — **готов к M227**

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD** | `b703ea2` (M226) + unstaged (S-REPLAY-6 доводка) |
| **Tests** | **669 excl slow / 670 incl slow** (test_soak.py committed) |
| **Ruff** | **0** |
| **Alembic** | 0020 (source column, 5433) — миграций не добавляли |
| **ADR** | 001–024 (024 Accepted) |
| **Demo (live)** | 20 sessions 13W/7L, +4.95% |
| **Demo (5433 soak)** | 62 replay sessions 42W/19L, b 1.0→1.3095, p 0→0.564 |

## ADR-статус

| № | Заголовок | Статус |
|---|-----------|--------|
| 020 | Fractional Kelly + EV-Gate | Accepted |
| 021 | Session-Level Risk Limits | Proposed |
| 023 | ai_agent_runs — Indexes + Retention | Accepted |
| 024 | Deterministic Replay + Trade Provenance | Accepted |

## Critical Context

- **Рабочая БД:** `127.0.0.1:5433` (podman clay_timescaledb, TS 2.27.1). 5432 — бит, не трогать.
- **Pre-money код-цепочка:** ЗАКРЫТА ✅
- **Release readiness:** `data-freshness=fail` (stale market — operational, не код), `validation-gate=warn` (ждёт replay)
- **S-REPLAY-6:** ✅ CLOSED — soak 268s, recalibration p/b, L2 block proved, guard на clock-desync, ADR-024 Accepted

## Pending (выбор Emma)

- 🔒 **Real-money блокер:** Binance 451 из US — нужен non-US egress или testnet
- ▶️ **Живая paper-demo:** поднять ingestion + первый replay → снимет release_readiness="blocked"
- 🧬 **Idea-bank:** 4 донор-слайса из daily_stock_analysis
