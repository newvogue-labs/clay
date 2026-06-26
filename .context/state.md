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

## Baseline

| Метрика | Значение |
|---------|----------|
| **HEAD** | `e663019` (S-EGRESS-RECON-1) |
| **Tests** | **669 excl slow / 670 incl slow** |
| **Ruff** | **0** |
| **Alembic** | 0020 (source column, 5433) |
| **ADR** | 001–024 (024 Accepted) |
| **Demo (live)** | 20 sessions, 13W/7L, +4.95% |
| **Demo (5433 soak)** | 62 replay sessions, 42W/19L, b 1.0→1.3095, p 0→0.564 |

## ADR-статус

| № | Заголовок | Статус |
|---|-----------|--------|
| 020 | Fractional Kelly + EV-Gate | Accepted |
| 021 | Session-Level Risk Limits | Proposed |
| 023 | ai_agent_runs — Indexes + Retention | Accepted |
| 024 | Deterministic Replay + Trade Provenance | Accepted |

## Critical Context

- **Рабочая БД:** `127.0.0.1:5433` (podman clay_timescaledb, TS 2.27.1)
- **Pre-money код-цепочка:** ЗАКРЫТА ✅
- **S-REPLAY-6:** ✅ MERGED (M227)
- **Egress (Paris, FR):** Binance spot + futures testnet reachable, 451 absent
- **Testnet:** `testnet.binance.vision` / `testnet.binancefuture.com` — HTTP 200, live data, zero code to switch

## Pending (выбор Emma)

- **A)** Real-money egress (Binance non-US/VPS) — док S-EGRESS-RECON-1 готов
- **B)** Idea-bank: S-LLM-PARSE-1 и другие донор-слайсы
- **C)** Накопить ≥30 реальных live-исходов для live-калибровки
- **D:** Отдельный ADR на execution layer (after testnet-first)
