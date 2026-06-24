# Текущее состояние Clay

- **Infrastructure & Ingestion:** ✅ MVP-ready (Live-gates G0-G4 closed).
- **Trading Layer (FSM):** ✅ MVP-ready (Finding G CLOSED).
- **DEPLOY TRACK:** ✅ Все до DEPLOY-5 Phase 3 closed.
- **S3/S4:** ✅ ПОЛНОСТЬЮ ЗАКРЫТЫ.
- **S-REGISTRY-2/2b:** ✅ CLOSED. ADR-017 Proposed.
- **S-KELLY-2:** ✅ MERGED (ADR-020 Accepted, fractional Kelly + EV-gate, annotation, 27 тестов)
- **S-KELLY-2-R:** ✅ CLOSED (EV-gate block proof + known-gap documented, 11 тестов)

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
- **Session-level risk-limits gap:** 📋 ADR/дизайн для `risk-limits-active` (сейчас заглушка `"ok"`, НЕ блокирует)
- **S-KELLY-2-R-ATR:** 📋 per-signal stop/target (ATR) — enhancement
- **UI-Фаза 2-3:** 📋 ADR-014
- **5432 восстановление:** 📋 TS upgrade
- **Real-money egress:** 📋 НЕ-US endpoint для Binance

## Critical Context

- **HEAD:** обновится после коммита (дерево чисто).
- **ADRs:** 015-degraded-mode, 016-config-write-path, 017-homo-role-registry, **020-kelly-ev-gate (Accepted)**
- **Миграции:** 0018 (advisory_size_pct) — применена к 5433, обратима
- **all-Google homo:** active runtime, conflicts=0
- **Рабочая БД:** `127.0.0.1:5433` (podman clay_timescaledb, TS 2.27.1). 5432 — бит, не трогать.
- **test:** 604 passed (+11 S-KELLY-2-R). Ruff 58 errors (все предсущ.)
- **Reconcile loop:** ACTIVE noop
- **S-KELLY-2-R evidence doc:** `docs/mission-control/ev-gate-proof.md`
- **Known gap:** `session_control/service.py:522` — risk-limits-active = hardcoded `"ok"`, `blocks_start=False`, НЕ блокирует
