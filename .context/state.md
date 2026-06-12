# Текущее состояние Clay

- **Infrastructure & Ingestion:** ✅ MVP-ready (Live-gates G0-G4 closed).
- **Trading Layer (FSM):** ✅ MVP-ready (Finding G CLOSED).
- **DEPLOY TRACK:** ✅ G6-obs → DEPLOY-0/0.1/1/2/3/3.5a/3.5a-V2/3.5b/3.5c/3.5d/3.5e closed.
- **DB-AUTOSTART:** ✅ `restart=always` + `podman-restart` + linger. 0 коммитов.
- **DEPLOY-5-RECON + DOCS α1/α2:** ✅ CLOSED.
- **DEPLOY-5 Phase 3 (code):** ✅ **5b-iii CLOSED целиком.** 3 cloud-провайдера × полный цикл. Dual-transport live на обоих плечах.
- **DEPLOY-3.5e (kill-switch):** ✅ **CLOSED.** Пользователь `clay` (uid 945). LiteLLM под uid 945. Always-on nft. Latch/udev — history.
- **DB-AUTOSTART:** ✅ `restart=always` + `podman-restart` + linger.
- **HEAD:** `00adb03` — feat(ai_control): wire subagent roles to gemma-4-31b + role prompts + hermetic tests
- **origin/main:** `3a325b0` запушено (14 коммитов не запушены).

## DEPLOY TRACK

- **DEPLOY-0** (baseline): ✅ CLOSED. 409/33/47.
- **DEPLOY-0.1** (test/tooling hygiene): ✅ CLOSED. Commit `c091ac8`.
- **DEPLOY-1** (TimescaleDB Podman): ✅ CLOSED. Commit `4a353c7`. Порт `127.0.0.1:5433`.
- **DEPLOY-2** (app-on-host + alembic + health): ✅ CLOSED. 0-commit.
- **DEPLOY-3** (egress verify): ✅ CLOSED.
- **DEPLOY-3.5a** (kill-switch recon): ✅ CLOSED.
- **DEPLOY-3.5a-V2** (owner-anchor recon): ✅ CLOSED.
- **DEPLOY-3.5b** (nft kill-switch): ✅ CLOSED.
- **DEPLOY-3.5c** (persistence): ✅ CLOSED.
- **DEPLOY-3.5d** (kill-switch boot-fix): ✅ CLOSED. HEAD `3a325b0`.
- **DEPLOY-4** (scheduler ON): ✅ CLOSED.
- **DEPLOY-5-RECON** (R1–R9): ✅ CLOSED.
- **DEPLOY-5-DOCS-α1** (ADR-009..012): ✅ CLOSED.
- **DEPLOY-5-DOCS-α2** (build_spec + impl_plan + runbooks + backlog): ✅ CLOSED.
- **DEPLOY-5 Phase 3 code (5b-iii):** ✅ **ЗАКРЫТ целиком.**
  - 5b-iii.1: LiteLLMModelClient + RoutingModelClient ✅ `a4489ac`
  - 5b-iii.2: host-config Gemini boundary-live ✅ 0 коммитов
  - 5b-iii.3: attended smoke (429, Gemini free-tier RPD exhausted) ❌ STOP
  - 5b-iii.4a: TokenRouter/MiniMax-M3 host-config ✅ 0 коммитов
  - 5b-iii.4b: model in registry + chief-agent ✅ `bbf6623`
  - 5b-iii.4c: attended smoke chief-agent→minimax-m3 ✅ 2 цикла
  - 5b-iii-docs: runbook + ADR + backlog ✅ `6969224`
  - 5b-iii.5a: Gemini 3.1 Flash Lite host-config ✅ 0 коммитов
  - 5b-iii.5b: gemini-3.1-flash-lite в реестр + forecast-model ✅ `73b59ac`
  - 5b-iii.5c: attended smoke forecast-model ✅ 2 цикла, 0 ошибок
- **5c.1 (subagent roles):** ✅ **ЗАКРЫТ.** gemma-4-31b в registry, INITIAL_ASSIGNMENTS обновлены, role_prompts + параметризация _render_context, герметизация singleton под pytest, DB 5433 sync. Commit `00adb03`.
- **DEPLOY-CUTOVER** (pg_dump live→podman): 📋 отложен.

## Pending

- **5c.2 (multi-role scheduler):** 📋 variant A (list role_ids in 1 job)
- **5c.3 (Gemma 4 31B host-config + gateway):** 📋 boundary-live тест
- **5c.4 (live smoke оба субагента):** 📋 node selection (Binance ≠US + Gemini probe 200)
- **Fix-slice FOOTGUN IngestionSettings:** env_file не добавлен (env_file ломает тесты production .env). Герметизация singleton решена через os.environ.setdefault в conftest.py.

## Critical Context

- **Live-5432** НЕ ТРОГАТЬ. **Podman-5433** — рабочая БД.
- **CLAY_DATABASE_URL** = `localhost:5433` (podman). FOOTGUN A: .env НЕ читается pydantic-settings, нужен явный env var.
- **TUN UP** (exit=🇳🇱 Netherlands, MIRhosting). Kill-switch вооружён (udev-arm, 71 reject pkts).
- **Scheduler ON**: `CLAY_SCHEDULER_ENABLED=true`.
- **LiteLLM:** host-native (uv tool, 1.88.1), порт 4000, systemd --user unit, 5 моделей: gemma4-e2b, local-ollama, gemini-2.5-flash, minimax-m3, **gemini-3.1-flash-lite**
- **Ollama:** system-сервис, `OLLAMA_HOST=127.0.0.1`, `OLLAMA_CONTEXT_LENGTH=65536`, `OLLAMA_NUM_PARALLEL=1`, порт 11434
- **Dual-transport:** RoutingModelClient per-call по transport-полю registry. Cloud: LiteLLM → 3 провайдера. Local: Ollama native `/api/chat`.
- **3 live провайдера:** Ollama (gemma4 local), TokenRouter (MiniMax-M3), Google (Gemini 3.1 Flash Lite, Gemini 2.5 Flash fallback)
- **test:** 441 passed (+1 transport test). Ruff/Pyright baseline.
- **keys:** 2 ключа в `~/.config/clay/litellm/litellm.env` (600): GEMINI_API_KEY, TOKENROUTER_API_KEY
- **env open issue:** `IngestionSettings.env_file` отсутствует → bootstrap дефолтит на live 5432. Для attended smoke и тестов обязателен явный `CLAY_DATABASE_URL`.

## Commits (сессия)

| SHA | Message |
|-----|---------|
| `00adb03` | feat(ai_control): wire subagent roles to gemma-4-31b + role prompts + hermetic tests |
| `63bbd58` | docs(context): update state, reports, handoff for 3.5e close + DB-autostart |
| `b59c7f3` | docs(killswitch,gateway,backlog): rewrite runbook-003 for uid-945 isolation |
| `73b59ac` | feat(ai-control): add gemini-3.1-flash-lite registry, assign forecast-model (5b-iii.5b) |
| `6969224` | docs(mission-control): dual-transport routing, provider policy, quota runbook (5b-iii) |
| `bbf6623` | feat(ai-control): add minimax-m3 cloud model, assign chief-agent (5b-iii.4b) |
| `a4489ac` | feat(ai): LiteLLM cloud ModelClient + per-call transport routing via model registry |
| `5e2f5b8` | docs(context): update state.md + reports/last.md for 5b-iii.1 |
