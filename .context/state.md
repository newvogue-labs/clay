# Текущее состояние Clay

- **Infrastructure & Ingestion:** ✅ MVP-ready (Live-gates G0-G4 closed).
- **Trading Layer (FSM):** ✅ MVP-ready (Finding G CLOSED).
- **DEPLOY TRACK:** ✅ Все до DEPLOY-5 Phase 3 closed.
- **S3a (SQL repo + seed):** ✅ CLOSED. `SqlProviderPoolRepository`, seed (4/3/7).
- **S3b (ConfigReconciler parity-render):** ✅ CLOSED. `render()` + `diff()`. Parity `Equivalent: True`.
- **S3c-1 (ConfigWriter shadow):** ✅ CLOSED. `write_shadow()`, validate, backup, noop-skip. 24 тестов.
- **S3c-1R (recon канонического пути):** ✅ CLOSED. FOOTGUN H снят. Канонический путь: `/etc/clay/litellm/config.yaml`. System-юнит User=clay.
- **S3c-2 (apply_live live-запись + restart):** ✅ CLOSED. `apply_live()` с backup→write→restart→health→rollback. 10 тестов. No-op live run: `Applied: False`.
- **S3c-2 rehearsal (live — force):** ✅ `Applied=True`, `Restart OK`, `Health OK`, `Rolled back=False`. Поймал 2 бага (backup PermissionError + temp 0600 нечитаемый для clay) — починены в коммите.
- **S3c-3 (degraded-mode ADR-015):** ✅ CLOSED. `evaluate_pool_health()`, `DegradedModeError`, `reconcile()` с never-empty invariant. 12 тестов. ADR-015 Accepted.
- **FOOTGUN H:** ✅ СНЯТ (restart безопасен: runtime из файла, файл правильный).
- **Dead user-unit cleanup:** ✅ юнит clay-litellm.service (emma) удалён.
- **Reload strategy:** `sudo systemctl restart clay-litellm.service` (hot-reload `--reload`/`/config/update` недоступны).
- **Privilege:** sudoers-правило на restart (`/etc/sudoers.d/99-clay-litellm`). Запись — `sudo -u clay cp`.

## Commits (текущая сессия)

| SHA | Message |
|-----|---------|
| `1ae7424` | docs(adr): ADR-013 addendum — provider pool schema, state machine, variant A |
| `d845edd` | feat(ai-control): provider-pool schema migration 0016 |
| `e24f3b3` | feat(ai-control): ProviderPool resource-manager + FSM fixture |
| `5278453` | feat(ai-control): SqlProviderPoolRepository + idempotent seed |
| `b0b77cb` | feat(ai-control): ConfigReconciler render + parity diff (S3b) |
| `a0b5f17` | feat(ai-control): ConfigWriter shadow + apply_live + degraded-mode (S3c-1/2/3) |
| `2e68a76` | docs(adr): ADR-015 degraded-mode — never-empty invariant, fail-loud (S3c-3) |
| `6def8b5` | docs(runbook): update runbook-004 + backlog for FOOTGUN E+F, S3c host changes |
| `9dc40cd` | docs(context): update state, reports, handoff for S3c-3 + rehearsal |
| `9388bec` | test(ai-control): fix apply_happy_path backup.exists() with real cp side-effect (S3c-2 test-gap) |

## Pending

- **Scheduler-петля (вариант A, раз в N мин):** 📋 Подключить reconcile-петлю. Развилка: uid (emma vs clay) → sudoers, см. ревью-заметку.
- **S4 (полный сид пула):** 📋 Развернуть провайдерские ключи и деплои из live-инфры.
- **Retention/index `ai_agent_runs`:** 📋 Package с latency/token/cost capture (Ф1b).
- **UI-Фаза 2-3** (write/governance, чат-окно, промпты в БД): 📋 ADR-014.
- **Deploy-cutover** (pg_dump live→podman): 📋 отложен.

## Critical Context

- **Live-5432** НЕ ТРОГАТЬ. **Podman-5433** — рабочая БД (пароль из `.env`).
- **Канонический LiteLLM конфиг:** `/etc/clay/litellm/config.yaml` (owner clay:clay, mode 0640).
- **LiteLLM:** system-юнит (User=clay), порт 4000. reload = `sudo systemctl restart clay-litellm.service`.
- **Dual-transport:** RoutingModelClient per-call по transport-полю registry.
- **3 live провайдера:** Ollama (local), NVIDIA NIM (Minimax-M3), Google (Gemini).
- **test:** 558 passed (+12 S3c-3). Ruff 0. Rehearsal live: green.
- **КОНВЕРГЕНЦИЯ-FOOTGUN:** Пароль 5432 (live) = `clay`. Pre-flight TS 2.27.1 защищает от случайного alembic на live.
- **FOOTGUN H (RESTART-REVERT):** ❌ СНЯТ. Runtime-модели (7 шт, NVIDIA) из файла `/etc/clay/litellm/config.yaml`. Restart безопасен.
