# Текущее состояние Clay

- **Infrastructure & Ingestion:** ✅ MVP-ready (Live-gates G0-G4 closed).
- **Trading Layer (FSM):** ✅ MVP-ready (Finding G CLOSED).
- **DEPLOY TRACK:** ✅ Все до DEPLOY-5 Phase 3 closed.
- **S3/S4:** ✅ ПОЛНОСТЬЮ ЗАКРЫТЫ.
- **S-REGISTRY-2/2b:** ✅ CLOSED. ADR-017 Proposed.
- **S-KELLY-2:** ✅ MERGED (ADR-020 Accepted, fractional Kelly + EV-gate, annotation, 27 тестов)
- **S-KELLY-2-R:** ✅ CLOSED (EV-gate block proof + known-gap documented, 11 тестов)
- **ADR-021:** ✅ Proposed (session-level risk-limits admission gate, 5 лимитов)
- **S-RISKLIMITS-1b:** ✅ CLOSED (ADR-021 v2 записан, коммит `5ded307`)

## Demo — Ring 1 baseline достигнут 🏆

| Метрика | Значение |
|---------|----------|
| Сессии | **20/5** ✅ (Ring 1 baseline) |
| KPI (total records) | **20/20** ✅ |
| Win / Loss | **13 win / 7 loss** |
| Накопленный P&L | **+4.95%** |
| Все гейты | 🟢 |

## Pending

- **Ring 1 go/no-go:** 📋 Определиться после review
- **Ф1b:** 📋 retention/index `ai_agent_runs`
- **Doc-sync:** 📋 roadmap S4 + ADR-директории
- **S-RISKLIMITS-2:** ✅ MERGED (L1-L5, warn-enum, 16 тестов, `9e3cbf8`)
- **Session-level risk-limits gap:** ✅ ADR-021 Proposed — gap design закрыт
- **S-DOCSYNC-1:** 📋 следующий (ожидает команды Emma)
- **S-KELLY-2-R-ATR:** 📋 per-signal stop/target (ATR) — enhancement
- **UI-Фаза 2-3:** 📋 ADR-014
- **5432 восстановление:** 📋 TS upgrade
- **Real-money egress:** 📋 НЕ-US endpoint для Binance

## Critical Context

- **HEAD:** `9e3cbf8` (S-RISKLIMITS-2 merge). Дерево чисто.
- **ADRs:** 015, 016, 017, **020-kelly-ev-gate (Accepted)**, **021-session-risk-limits (Proposed)**
- **Миграции:** 0018 (advisory_size_pct) — применена к 5433, обратима
- **all-Google homo:** active runtime, conflicts=0
- **Рабочая БД:** `127.0.0.1:5433` (podman clay_timescaledb, TS 2.27.1). 5432 — бит, не трогать.
- **test:** 620 passed (+16 S-RISKLIMITS-2). Ruff 58 errors (все предсущ.)
- **Reconcile loop:** ACTIVE noop
- **S-KELLY-2-R evidence doc:** `docs/mission-control/ev-gate-proof.md`
- **S-RISKLIMITS-2 evidence:** `docs/adr/021-session-risk-limits.md`
