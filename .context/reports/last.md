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
