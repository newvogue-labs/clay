---
id: obs-2026-06-01-003
date: 2026-06-01
tags: [production-bug, bootstrap, integration-suite, factory-extraction, a6]
type: critical-finding
---

# A6 recon: production-баг двойной инициализации в `bootstrap.py`

## Контекст

В A6 recon при проверке `bootstrap.py` обнаружено, что `validation_lab_service` и `reliability_service` создавались **дважды** — первый блок (lines 95-153) с `session_factory=ingestion_session_factory`, второй блок (lines 154-193) **перезаписывал** их **без** `session_factory`. `alpha_readiness_service` (создавался во 2-м блоке) собирался поверх **non-persistent** копий.

**Сценарий бага:** оператор применяет `validation_lab.apply_activation('strategy_mode', 'defensive')`. Запись идёт через 1-й `validation_lab_service` (persistent), но `alpha_readiness_service` хранит ссылку на **2-й** (non-persistent) → `alpha.build_snapshot` читает `_strategy_mode = "momentum"` (in-memory default), а не `"defensive"` (БД).

**Эффект:** весь persistence-код A3+A4+A5 **работал в тестах, но не в production** (alpha-метрики расходились с реальным состоянием). Тесты ловили каждый сервис в изоляции; integration suite не существовал.

## Решение

**Factory extraction + integration suite через production factory.**

1. Извлечён `build_services(config_loader, session_factory=None)` factory в `bootstrap.py` — единственный source of truth для service graph.
2. Модульный bootstrap = `services = build_services(...); exports = services["..."]` (один проход, нет шанса на regression типа double-init).
3. Integration suite (`tests/integration/test_restart_survival.py`) гоняет **production** factory на file-based SQLite. Параллельный hand-rolled bundle (как старый `build_alpha_bundle`) **не** поймал бы этот баг — suite строится из того же кода, что и production, и ловит regressions.

## Why / How to apply

- **Integration-тесты должны гонять production wiring**, а не parallel hand-rolled bundle. Иначе они тестируют «другую вселенную».
- **Двойная инициализация** — silent killer: тесты зелёные, метрики расходятся. Всегда строить service graph **одним** factory call.
- **`_RECONCILABLE_STATES` whitelist** в `RuntimeManager.reconcile_to` — restore-примитив, не backdoor-сеттер. Skip path-validation OK (reconcile = fact), но skip **target-validation** нельзя.
- **In-memory `build_alpha_bundle` в `test_alpha_readiness_service.py:51`** остаётся as-is (5 existing alpha-тестов намеренно) — дивергенция от integration suite **by design**, отмечено в `_helpers.py` docstring.
- **Связанные**: A3 §6 Q1 (`session_factory` обязательный? — нет, опционален для обратной совместимости; production ВСЕГДА передаёт factory → полностью персистентен); A4 §6 Q2 (runtime_manager reconcile → A6 closed через `reconcile_to`).

**Lessons learned (carry-forward):**
- Любой future factory / module-level singleton-graph rewrite — **один** call site, никаких дублей. Если нужен второй instance (e.g. для in-memory test fixtures) — отдельный helper, не параллельный bootstrap.
- Integration suite на production factory — обязателен для проверки service-graph wiring. Unit-тесты per-service не ловят cross-service init bugs.
