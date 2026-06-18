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

## Commits (S3d-pre + S3d-1)

| SHA | Message |
|-----|---------|
| `1756d7b` | feat(ai-control): live migration 0016 on 5432 + seed (4/3/7) + backup |
| `c6d5c9a` | feat(ai-control): S3d-1 helper-based root write-path + ADR-016 + rehearsal |

## Commits (S3d-2 + S3d-3)

| SHA | Message |
|-----|---------|
| `4e5bc3b` | feat(scheduler): S3d-2 provider-pool-reconcile job (flag-gated) |
| `72572e0` | docs: S3d-3 activate reconcile loop + S3 closed |

## S3 status: ✅ ПОЛНОСТЬЮ ЗАКРЫТ

S3 (stateful provider-pool: schema → API → reconcile → degraded → live-миграция → write-path → auto-cycle) CLOSED.

## Pending

- **S4 (полный сид пула):** 🔜 Развернуть провайдерские ключи и деплои из live-инфры. Ожидает архитектора.
- **Retention/index `ai_agent_runs`:** 📋 Package с latency/token/cost capture (Ф1b).
- **UI-Фаза 2-3** (write/governance, чат-окно, промпты в БД): 📋 ADR-014.
- **Deploy-cutover** (pg_dump live→podman): 📋 отложен.

## Critical Context

- **Live-5432** НЕ ТРОГАТЬ. **Podman-5433** — рабочая БД (пароль из `.env`).
- **Канонический LiteLLM конфиг:** `/etc/clay/litellm/config.yaml` (owner clay:clay, mode 0640).
- **LiteLLM:** system-юнит (User=clay), порт 4000. reload = `sudo systemctl restart clay-litellm.service`.
- **Dual-transport:** RoutingModelClient per-call по transport-полю registry.
- **3 live провайдера:** Ollama (local), NVIDIA NIM (Minimax-M3), Google (Gemini).
- **test:** 566 passed (+4 S3d-2). Ruff 0. Клиент: `curl -s http://127.0.0.1:8000/health` для проверки.
- **КОНВЕРГЕНЦИЯ-FOOTGUN:** Пароль 5432 (live) = `clay`. Pre-flight TS 2.27.1 защищает от случайного alembic на live.
- **FOOTGUN H (RESTART-REVERT):** ❌ СНЯТ. Runtime-модели (7 шт, NVIDIA) из файла `/etc/clay/litellm/config.yaml`. Restart безопасен.
- **S3d-3 reconcile loop:** ACTIVE. `CLAY_SCHEDULER_PROVIDER_POOL_RECONCILE_ENABLED=true` в `.env`. Sync job, ThreadPoolExecutor, interval 300s. kill-switch: флаг OFF + рестарт backend.
- **Backend:** запущен под emma (`python -m clay`), порт 8000. Рестарт: `kill PID && cd backend && export $(cat .env | xargs) && uv run python -m clay`.
