# Текущее состояние Clay

## Завершено (эта сессия)

- **S-DOCSYNC-2:** ✅ MERGED (ADR doc-sync B + 015→018 + master-index, M214)
- **S-RUNTIME-VERIFY-1:** ✅ Ring 1 GO + FOOTGUN B verified + live gates (M215/M216)
- **S-RUFF-2:** ✅ ruff 58→0 + durability assertions (M217)
- **S-Ф1b-2:** ✅ ai_agent_runs indexes I1/I2 + retention 180d + ADR-023 (M218)

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD** | `a319695` |
| **Tests** | **622 passed** |
| **Ruff** | **0** |
| **Alembic** | 0019 (5433 only, TS 2.27.1) |
| **ADR** | 001–023 (mc-archive 001–015, docs/adr 016–023) |
| **Demo** | 20 sessions, 13W/7L, +4.95%, all gates green |

## ADR-статус

| № | Заголовок | Статус |
|---|-----------|--------|
| 020 | Fractional Kelly + EV-Gate | Accepted |
| 021 | Session-Level Risk Limits | Proposed |
| 023 | ai_agent_runs — Indexes + Retention | Accepted |

## Critical Context

- **Рабочая БД:** `127.0.0.1:5433` (podman clay_timescaledb, TS 2.27.1). 5432 — бит, не трогать.
- **Pre-money код-цепочка:** ЗАКРЫТА ✅
- **Release readiness:** `data-freshness=fail` (stale market — operational, не код), `validation-gate=warn` (ждёт replay)

## Pending (выбор Emma)

- 🔒 **Real-money блокер:** Binance 451 из US — нужен non-US egress или testnet
- ▶️ **Живая paper-demo:** поднять ingestion + первый replay → снимет release_readiness="blocked"
- 🧬 **Idea-bank:** 4 донор-слайса из daily_stock_analysis
