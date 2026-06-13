# Текущее состояние Clay

- **Infrastructure & Ingestion:** ✅ MVP-ready (Live-gates G0-G4 closed).
- **Trading Layer (FSM):** ✅ MVP-ready (Finding G CLOSED).
- **DEPLOY TRACK:** ✅ G6-obs → DEPLOY-0/0.1/1/2/3/3.5a/3.5a-V2/3.5b/3.5c/3.5d/3.5e closed.
- **DB-AUTOSTART:** ✅ `restart=always` + `podman-restart` + linger. 0 коммитов.
- **DEPLOY-5-RECON + DOCS α1/α2:** ✅ CLOSED.
- **DEPLOY-5 Phase 3 (code):** ✅ **5b-iii CLOSED целиком.** 3 cloud-провайдера × полный цикл. Dual-transport live на обоих плечах.
- **DEPLOY-3.5e (kill-switch):** ✅ **CLOSED.** Пользователь `clay` (uid 945). LiteLLM под uid 945. Always-on nft. Latch/udev — history.
- **DB-AUTOSTART:** ✅ `restart=always` + `podman-restart` + linger.
- **HEAD:** `c0a53f5` — fix(api): SSE heartbeat + shared stream helper (FOOTGUN F)
- **origin/main:** `c0a53f5` запушено (0 отставания).

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
- **5c.3 (Gemma 4 31B host-config + gateway):** ✅ **ЗАКРЫТ.** config.yaml + restart → 6 моделей, boundary-live 200/1.4s. 0 коммитов.
- **5c.2 (multi-role scheduler):** ✅ **ЗАКРЫТ.** AIAgentCycleJob sequential multi-role, per-role isolation, ROLE_IDS (JSON), FOOTGUN D fix (reasoning_content fallback). Commit `c82acd5`.
- **5c.4 (live smoke 4 роли):** ✅ **ЗАКРЫТ.** 1 полный тик 4/4 + overlap пруф + FOOTGUN D live + per-role isolation в бою. Трек 5c доказан end-to-end.
- **DEPLOY-CUTOVER** (pg_dump live→podman): 📋 отложен.

## Pending

- **docs-5c:** ✅ **CLOSED.** runbook-004 DSN fix, multi-role docs, FOOTGUN D/E, ADR-010 addendum, incident-log. Commit `8065297`.
- **Fix-slice FOOTGUN A:** ✅ **CLOSED.** `database_url` required. Commit `4d6da5a`.
- **5c.5.1 (subagent→chief context):** ✅ **CLOSED.** Repo-метод + рендер + 14 тестов. Commit `daa079c`.
- **FOOTGUN E (candidate):** 📋 LiteLLMModelClient — захватывать status+body ответа в error.
- **5c.5.2 attend-smoke:** ✅ **CLOSED.** Пруф синтеза chief доказан (runs 31–34, ID 34 chief→minimax-m3, 3387 chars, ссылается на 3 субагентов). 5c.5 целиком закрыт.
- **UI-DATA-RECON:** ✅ **CLOSED.** SSE-роуты 200 с пустыми стримами → FOOTGUN F.
- **FOOTGUN F-a (SSE heartbeat):** ✅ **CLOSED.** `sse.py` helper + heartbeat 15s + рефакторинг 10 стримов + events.py. Commit `c0a53f5`.
- **docs-5c.5:** ✅ **CLOSED.** roles-taxonomy.md, ADR-010 addendum 3, runbook-004 re-smoke, backlog sync. Commit `7e88747`.
- **FOOTGUN E:** 📋 LiteLLMModelClient — захватывать status+body ответа в error.
- **SSE-RECON:** 📋 Emma проводит аудит SSE-кода → UI-трек нарезка.
- **Provider pool free-tier:** 📋 Emma → список → recon → приоритезация.
- **Retention/index `ai_agent_runs`:** 📋 база растёт (~1152/день@300s×4).

## Critical Context

- **Live-5432** НЕ ТРОГАТЬ. **Podman-5433** — рабочая БД.
- **CLAY_DATABASE_URL** = `127.0.0.1:5433` (podman). Канонический путь `backend/.env` (синхронизирован с корневым `.env`). FOOTGUN A (env_file) — open.
- **TUN UP** (exit=🇳🇱 Netherlands, MIRhosting). Kill-switch вооружён, counter=4.
- **LiteLLM:** host-native (uv tool, 1.88.1), порт 4000, systemd --user unit, **6 моделей**: gemma4-e2b, local-ollama, gemini-2.5-flash, minimax-m3, gemini-3.1-flash-lite, **gemma-4-31b**
- **Ollama:** system-сервис, `OLLAMA_HOST=127.0.0.1`, `OLLAMA_CONTEXT_LENGTH=65536`, `OLLAMA_NUM_PARALLEL=1`, порт 11434
- **Dual-transport:** RoutingModelClient per-call по transport-полю registry. Cloud: LiteLLM → 3 провайдера. Local: Ollama native `/api/chat`.
- **3 live провайдера:** Ollama (gemma4 local), TokenRouter (MiniMax-M3), Google (Gemini 3.1 Flash Lite, Gemini 2.5 Flash fallback)
- **test:** 463 passed. Ruff 13/Pyright 33 baseline.
- **SSE heartbeat:** новый `clay/events/sse.py` — `sse_event_stream()` с keep-alive каждые 15s. Все 11 stream-роутов на нём.
- **keys:** 2 ключа в `~/.config/clay/litellm/litellm.env` (600): GEMINI_API_KEY, TOKENROUTER_API_KEY. Gemma-4-31b использует тот же GEMINI_API_KEY.
- **Тик 4 ролей ≈ 52s sequential.** Правило интервала: `interval ≥ 2× длительность тика` (300s → запас ×5.7).
- **Last smoke:** 26 runs (17 success / 9 error) в 5433. Per-role isolation proven live.

## Commits (сессия)

| SHA | Message |
|-----|---------|
| `c0a53f5` | fix(api): SSE heartbeat + shared stream helper (FOOTGUN F) |
| `7e88747` | docs(ai_control): roles taxonomy + hierarchy v1 notes (5c.5) |
| `daa079c` | feat(ai_control): feed subagent outputs into chief context (5c.5) |
| `4d6da5a` | fix(settings): require explicit CLAY_DATABASE_URL (FOOTGUN A) |
| `8065297` | docs(runbook): 5c multi-role + DSN fix + footguns D/E |
| `a8c360b` | docs(context): update state, reports for 5c.3 + 5c.2 close |
| `c82acd5` | feat(scheduler): multi-role ai agent cycle + reasoning_content fallback |
| `57bfc9a` | docs(context): update state, reports for 5c.1 close + 5c.3 host-config |
| `00adb03` | feat(ai_control): wire subagent roles to gemma-4-31b + role prompts + hermetic tests |
| `63bbd58` | docs(context): update state, reports, handoff for 3.5e close + DB-autostart |
| `b59c7f3` | docs(killswitch,gateway,backlog): rewrite runbook-003 for uid-945 isolation |
| `73b59ac` | feat(ai-control): add gemini-3.1-flash-lite registry, assign forecast-model (5b-iii.5b) |
