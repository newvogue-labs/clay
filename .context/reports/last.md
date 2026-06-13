# Отчёт: DEPLOY-5 Phase 3 code — сессия 2026-06-11

## Что сделано

### 5b-iii.1 — LiteLLMModelClient + RoutingModelClient
- ✅ A1–A5: transport-поле, LiteLLM клиент, RoutingModelClient, wiring, 9 тестов
- ✅ 439 passed, committed `a4489ac feat(ai)`

### 5b-iii.2 — host-config Gemini-ключ + boundary-live
- ✅ Ключ из бэкапа → litellm.env (600), drop-in EnvironmentFile
- ✅ gemini-2.5-flash в config.yaml
- ✅ boundary-live: 200, 1.23s, 43 токена
- ✅ 0 коммитов

### 5b-iii.3 — attended smoke forecast-model → gemini-2.5-flash
- ✅ STARTUP прошёл, job registered
- ❌ **429 Too Many Requests** на 1-м тике (Gemini free-tier RPD=20 исчерпан)
- ✅ STOP исполнен чисто, 0 ретраев

### 5b-iii.4a — TokenRouter/MiniMax-M3 host-config + boundary-live
- ✅ Ключ в litellm.env, minimax-m3 в config.yaml
- ✅ Step 0: `MiniMax-M3` model-ID обнаружен
- ✅ boundary-live: 200, 3.78s, 219 токенов
- ✅ 0 коммитов

### 5b-iii.4b — feat: minimax-m3 в реестр + chief-agent назначение
- ✅ placeholder `openai-gpt-5.4` удалён из реестра и INITIAL_ASSIGNMENTS
- ✅ `minimax-m3` добавлен (transport=cloud)
- ✅ `chief-agent → minimax-m3` штатно (0 bypass)
- ✅ 440 passed, 0 new lint/type
- ✅ committed `bbf6623 feat(ai-control)`
- 🎯 FOOTGUN найдено: IngestionSettings не читает .env, дефолтит в live 5432

### 5b-iii.4c — attended smoke chief-agent → minimax-m3 (полный цикл)
- ✅ **2 цикла**, content_len=1115/1718, error=NULL
- ✅ thinking=NULL (cloud), VRAM +30MB (vs +2GB локально)
- ✅ **Dual-transport доказан live на обоих плечах**
- ✅ 0 коммитов

### 5b-iii-docs — документация закрытия трека
- ✅ runbook-004: dual-transport, provider procedure, quota, FOOTGUN
- ✅ ADR-010 addendum: RoutingModelClient per-call, live-метрики, provider policy
- ✅ config.yaml.example: 4 модели
- ✅ backlog: 3 пункта
- ✅ committed `6969224 docs(mission-control)`

### 5b-iii.5a — Gemini 3.1 Flash Lite host-config + boundary-live
- ✅ Новый ключ (AIzaSyB9y... → AQ.Ab8RN6...)
- ✅ Discovery: `gemini-3.1-flash-lite` стабильный
- ✅ boundary-live: **200, 0.69s, 19 токенов** (рекорд шлюза)
- ✅ 5 моделей в шлюзе
- ✅ 0 коммитов

### 5b-iii.5b — feat: gemini-3.1-flash-lite в реестр + forecast-model переназначение
- ✅ `gemini-3.1-flash-lite` добавлен в `_build_model_registry` (transport=cloud)
- ✅ `gemini-2.5-flash` сохранён в реестре (fallback-кандидат)
- ✅ `INITIAL_ASSIGNMENTS`: forecast-model → gemini-3.1-flash-lite
- ✅ DB 5433: assignment обновлён (SELECT-пруф)
- ✅ 441 passed (+1 new transport test)
- ✅ committed `73b59ac feat(ai-control)`

### 5b-iii.5c — attended smoke forecast-model → Gemini 3.1 Flash Lite (полный цикл)
- ✅ **2 цикла**, content=283/317, error=NULL
- ✅ thinking=NULL (cloud), VRAM 660→547 MiB (flat, gemma не грузилась)
- ✅ kill-switch: 71 pkts — 0 прироста
- ✅ pyright src=33 (базовый инвариант подтверждён)
- ✅ **5b-iii.5 ЗАКРЫТ целиком**
- ✅ 0 коммитов

### Итог DEPLOY-5 Phase 3 code
- ✅ **5b-iii CLOSED** — dual-transport доказан live на обоих плечах
- ✅ 3 cloud-провайдера × полный цикл: TokenRouter/MiniMax-M3, Gemini 2.5 Flash, Gemini 3.1 Flash Lite
- ✅ Реестр: 7 моделей (3 cloud + 2 local + 2 legacy/fallback)
- ✅ HEAD `73b59ac`, pytest 441, ruff 47 (13 src), pyright src=33

## Коммиты (сессия)

| SHA | Message |
|-----|---------|
| `73b59ac` | feat(ai-control): add gemini-3.1-flash-lite registry, assign forecast-model (5b-iii.5b) |
| `6969224` | docs(mission-control): dual-transport routing, provider policy, quota runbook (5b-iii) |
| `bbf6623` | feat(ai-control): add minimax-m3 cloud model, assign chief-agent (5b-iii.4b) |
| `a4489ac` | feat(ai): LiteLLM cloud ModelClient + per-call transport routing via model registry |
| `5e2f5b8` | docs(context): update state.md + reports/last.md for 5b-iii.1 |

HEAD `73b59ac`.

## Сессия 2026-06-12 — 3.5e + DB-autostart

### DEPLOY-3.5e.1 — изоляция kill-switch: пользователь `clay` + LiteLLM миграция + nft
- ✅ Пользователь `clay` (uid 945), группа `clay`, emma в группе, ACL на /home/emma
- ✅ Репо: `chgrp -R clay` + setgid + g+rwX
- ✅ LiteLLM: uv tool install под clay → бинарь в `/var/lib/clay/.local/`
- ✅ Конфиги: `/etc/clay/litellm/` (config.yaml 640, litellm.env 600 — clay:clay)
- ✅ System unit: `/etc/systemd/system/clay-litellm.service`, `User=clay`
- ✅ Старый user-unit: `systemctl --user disable --now`
- ✅ Новый nft: uid 945 только — lo/singbox_tun/private accept, catch-all reject
- ✅ udev-правило удалено, unit `WantedBy=multi-user.target` (always-on)
- ✅ Gate B: port 4000 uid 945, liveliness 200, 5 моделей
- ✅ 0 коммитов

### DEPLOY-3.5e.2 — fail-closed verify
- ✅ T2: clay без TUN → URLError (counter 0→3), emma OK
- ✅ T3: clay amn0 → URLError (catch-all reject, counter 3→6)
- ✅ T6: LiteLLM boundary TUN down → APIConnectionError (counter 6→66), liveliness 200
- ✅ T8: reboot → kill-switch active, emma internet, LiteLLM uid 945, DB start (podman)
- ✅ Control: TUN up → clay egress 152.53.64.139 (≠US), counter 0 прирост
- **3.5e ЗАКРЫТ целиком.** 0 коммитов

### DEPLOY-3.5e-docs — runbook-003/004 + backlog
- ✅ runbook-003: полная переработка под 3.5e модель
- ✅ runbook-004: пути uid 945, health gates, attended smoke template, rate-limit table, node rule
- ✅ backlog: Gemini retry → ✅ closed, +2 пункта (restart-policy, DNS)
- ✅ committed `b59c7f3 docs(killswitch,gateway,backlog)`

### DB-AUTOSTART — clay_timescaledb restart-policy
- ✅ Path A: `podman update --restart=always` + `podman-restart` + linger
- ✅ Reboot → контейнер Up (healthy), extversion 2.27.1, ai_agent_runs=8
- ✅ Регресс-проверка: kill-switch active, LiteLLM uid 945, интернет emma
- ✅ 0 коммитов

## Итог

| Track | Status |
|-------|--------|
| 5b-iii | ✅ CLOSED — dual-transport, 3 cloud × полный цикл, 441 pytest |
| 3.5e | ✅ CLOSED — uid 945, always-on, fail-closed proven |
| DB-AUTOSTART | ✅ restart=always + podman-restart + linger |
| 5c.1 | ✅ CLOSED — gemma-4-31b registry, role prompts, hermetic tests, 442 pytest |
| HEAD | `00adb03` (14 unpushed) |

## Сессия 2026-06-12 — 5c.1 (subagent roles)

### Recon 5c.0 — forensics + findings
- __P0:__ git HEAD `63bbd58` — легитимный коммит Emma (state/handoffs/reports), не мой
- __P1:__ DB-назначения НЕ откатывались (subagent A дал ложные данные — неверный пароль `clay:clay@5433`)
- __P2:__ Роли market-scanner/news-sentiment-agent уже определены в INITIAL_ASSIGNMENTS и _build_role_registry
- __P3:__ FOOTGUN раскрыт: `IngestionSettings.env_file` отсутствует → pytest ходил в live 5432 через module-level singleton bootstrap. Тест зависит от ambient env — объяснение «вчера 441, сегодня 440»

### 5c.1 — subagent roles на реальные модели + role-prompts + герметизация
- ✅ **(0b)** Герметизация singleton под pytest: `os.environ.setdefault("CLAY_DATABASE_URL")` в tests/conftest.py + file-based SQLite с таблицами до загрузки bootstrap
- ✅ Registry: добавлен `gemma-4-31b` (transport=cloud, provider=Google AI Studio, 1500 RPD, 256K ctx), удалены `openai-gpt-5.4-mini` и `anthropic-claude-sonnet-4.5`
- ✅ INITIAL_ASSIGNMENTS: `market-scanner→gemma-4-31b`, `news-sentiment-agent→gemma-4-31b`
- ✅ role_prompts: словарь (market-scanner + news-sentiment-agent) передан в AgentRunner в lifespan.py
- ✅ _render_context: параметризован по `role_id` (сигнатура + вызов в run_once)
- ✅ DB 5433 sync: UPDATE market-scanner→gemma-4-31b, news-sentiment-agent→gemma-4-31b (SELECT-пруф)
- ✅ Тесты: обновлены затронутые (model_id замены во всех тестах), новый тест role_prompts dispatch + fallback
- ✅ **442 passed**, ruff 13 (src baseline), pyright 33 (src baseline)
- ✅ committed `00adb03 feat(ai_control): wire subagent roles to gemma-4-31b + role prompts + hermetic tests`

### DSN ответ
- Реальный пароль 5433: `clay:LjRVpJBOeveAm6ejI1hwd32BdIULVg2j@127.0.0.1:5433` (из `.env`)
- `clay:clay@5433` — неверен (subagent A). `clay:clay@5432` — live (FOOTGUN, дефолт IngestionSettings без env)
- runbook-004 шаблон `clay:clay@5433` устарел — `clay` имеет пароль (scram-sha-256), не `clay`
- env_file не добавлен — ломает тесты (подхватывает production .env). Герметизация singleton решена через environ

## Сессия 2026-06-12 — 5c.3 + 5c.2

### 5c.3 PREFLIGHT + host-config (Gemma 4 31B в gateway)
- ✅ **P0 hermetic gate:** podman stop → 442 pytest (энв чист)
- ✅ **P1 psql:** 4 строки, субагенты→gemma-4-31b
- ✅ **P2 нода-probe:** Gemini 200, 50 models
- ✅ config.yaml: gemma-4-31b→gemini/gemma-4-31b-it, restart → 6 моделей
- ✅ boundary-live: 200, 1.4s
- ✅ kill-switch flat, 0 коммитов
- **5c.3 ЗАКРЫТ**

### 5c.2 — multi-role scheduler + FOOTGUN D fix
- ✅ Settings: `CLAY_SCHEDULER_AI_AGENT_ROLE_IDS` (JSON list, default ["chief-agent"])
- ✅ AIAgentCycleJob: sequential multi-role, per-role isolation
- ✅ FOOTGUN D: LiteLLMModelClient — content fallback to reasoning_content, fail-loud
- ✅ ChatMessage: reasoning_content field
- ✅ Tests: multi-role dispatch, isolation, FOOTGUN-D, ROLE_IDS parsing
- ✅ **448 passed**, ruff 13, pyright 33
- ✅ committed `c82acd5`

## Сессия 2026-06-12 — 5c.4 attended smoke (4 роли)

### PREFLIGHT
- ✅ Gateway "I'm alive!", /v1/models = 6
- ✅ Assignments: chief→minimax-m3, scanner→gemma-4-31b, news→gemma-4-31b, forecast→gemini-3.1-flash-lite
- ✅ psql: extversion=2.27.1 (podman), baseline=8 runs
- ✅ Gemini probe: 200 "pong", Binance ≠US reachable
- ✅ Git clean HEAD `a8c360b`, kill-switch active counter=4
- ✅ `.env`→5432 root (Jun 7 mtime, эпоха P0). **Исправлен** на 5433 (синхронизирован с backend/.env)

### Smoke: 3 раунда, ~14 новых строк

| Раунд | Тиков | Gemma-4-31b | Gem-3.1-FL | MiniMax-M3 |
|-------|-------|-------------|------------|------------|
| R1 (60s) | 1 + 1⏭️ overlap | scanner✅357 + news✅544 | forecast✅567 | chief✅1539 |
| R2 (120s) | — | ❌ 400 User location (TUN/гео) | ❌ | ❌ |
| R3 (120s) | ~1.5 | scanner❌→✅556, news❌ | forecast✅421 | chief✅1178→✅1757 |

### Гейты 5c.4
- ✅ **FOOTGUN-D live:** 3 непустых gemma-content (357/544/556 chars), error=NULL
- ✅ **Per-role isolation live:** scanner/news fall → chief/forecast persist → next tick green
- ✅ **Overlap-protection raw:** `maximum number of running instances reached (1)`
- ✅ **Kill-switch flat:** counter=4 (0 рост), VRAM flat 9.4G/31G
- ✅ **0 коммитов**, git clean
- ✅ **Total: 26 runs** (17 success / 9 error) в podman-5433

### Наблюдения
- **Тик 4 ролей ≈ 52s** → правило `interval ≥ 2×` (300s запас ×5.7)
- **FOOTGUN E (candidate):** пустая 400 без тела при гео/transient → неинформативный error
- **Двойной `.env`:** корневой (Jun 7, 5432) vs backend/.env (Jun 11, 5433). **Канонический = backend/.env**

### 5c.4 ЗАКРЫТ ОКОНЧАТЕЛЬНО. Трек 5c (субагенты) доказан end-to-end на 4 ролях.

## Сессия 2026-06-12 — docs-5c + fix-A + 5c.5.1

### docs-5c — документация трека 5c
- ✅ runbook-004: DSN-шаблон починен, pkexec su форма, multi-role, overlap-protection, интервал правило
- ✅ FOOTGUN D (закрыт) + E (candidate) секция
- ✅ ADR-010 addendum: multi-role variant A, reasoning fallback, RPD budget
- ✅ incident-log.md: INC-001 pytest→5432
- ✅ backlog: FOOTGUN A/E, retention, 5c.5, restart-policy ✅, 5c.4 ✅
- ✅ `.env`→5432: корневой .env синхронизирован с backend/.env
- ✅ Commit `8065297`, docs-only, 0 src/tests

### fix-A — FOOTGUN A (IngestionSettings.database_url required)
- ✅ `database_url: str` — убран дефолт `clay:clay@localhost:5432`, поле REQUIRED
- ✅ Аудит import-time точек: bootstrap.py:182/335, db/session.py:19, signal_engine/service.py:59
- ✅ 4 `# type: ignore[reportCallIssue]` (pydantic-settings false positives)
- ✅ Негатив-тест: `test_unset_env_raises_readable_error` (ValidationError)
- ✅ **449 passed**, ruff 13, pyright 33
- ✅ Commit `4d6da5a`

### 5c.5.1 — выводы субагентов в контекст chief-agent
- ✅ Repo-метод `list_latest_agent_runs` в OpsRepository (DISTINCT ON role_id, error NULL + content NOT NULL)
- ✅ Секция «=== subagent_reports ===» в _render_context (только для chief-agent)
- ✅ session проброшен в _render_context через AIAgentCycleJob.run_once (AgentRunner не тронут)
- ✅ Docs-нота: порядок ROLE_IDS (субагенты → chief последним)
- ✅ 14 тестов: latest-per-role, рендер 3/1/0 отчётов, кап 2000, регрессион-пин
- ✅ **463 passed**, ruff 13, pyright 33
- ✅ Commit `daa079c`

## Сессия 2026-06-13 — docs-5c.5 + FOOTGUN F-a fix

### Слайс 1 — docs-5c.5 (docs-only)
- ✅ `docs/mission-control/roles-taxonomy.md` — 4 яруса, 13 ролей
- ✅ ADR-010 Addendum 3 — иерархия v1, smoke-пруф runs 31–34
- ✅ runbook-004: re-smoke процедура при cloud RPD исчерпании, FOOTGUN F нота
- ✅ backlog sync: 4 задачи (INFO-лог, LIMIT+retention, FOOTGUN E, FOOTGUN F)
- ✅ 4 файла, 198 insertions, docs-only
- ✅ Commit `7e88747`, push origin/main

### Слайс 2 — SSE-RECON (read-only, 0 коммитов)
- ✅ Исходники 3 стримов: `workspace_stream.py`, `control_center_stream.py`, `reliability_stream.py`
- ✅ EventBus: in-memory fan-out (`asyncio.Queue`), 12 call-sites
- ✅ Frontend: слушает `.ready` + `.refresh` события, snapshot на маунте (не только по SSE)
- ✅ Диагноз: нет heartbeat → reconnect-шум (271 ошибка, Status code: null)
- ❌ F-b (snapshot error → LOADING навсегда) — опровергнут кодом хука (try/catch → isLoading=false)

### Слайс 3 — FOOTGUN F-a fix (backend-only)
- ✅ `backend/src/clay/events/sse.py` — `encode_sse()` + `sse_event_stream()` с heartbeat 15s (`asyncio.wait_for` → `:keep-alive`)
- ✅ 10 stream-роутов + events.py отрефакторены на helper (−192 строк дублирования)
- ✅ `X-Accel-Buffering: no` добавлен во все стримы
- ✅ **463 passed**, ruff 0, pyright 0
- ✅ Proof-1: curl stream → CORS, `.ready`, `:keep-alive` через 15s
- ✅ Proof-2: `/control-center/overview` 200, `/workspace/trading` 200, `/reliability/overview` 200 (F-b снят)
- ✅ Commit `c0a53f5`, push origin/main

## Итог

| Track | Status |
|-------|--------|
| docs-5c.5 | ✅ CLOSED |
| SSE-RECON | ✅ CLOSED |
| FOOTGUN F-a | ✅ CLOSED |
| HEAD | `c0a53f5` (0 unpushed) |
