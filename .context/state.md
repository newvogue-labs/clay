# Текущее состояние Clay

- **Infrastructure & Ingestion:** ✅ MVP-ready (Live-gates G0-G4 closed).
- **Trading Layer (FSM):** ✅ MVP-ready (Finding G CLOSED).
- **DEPLOY TRACK:** ✅ G6-obs → DEPLOY-0/0.1/1/2/3/3.5a/3.5a-V2/3.5b/3.5c/3.5d/3.5e closed.
- **DB-AUTOSTART:** ✅ `restart=always` + `podman-restart` + linger. 0 коммитов.
- **DEPLOY-5-RECON + DOCS α1/α2:** ✅ CLOSED.
- **DEPLOY-5 Phase 3 (code):** ✅ **5b-iii CLOSED целиком.** 3 cloud-провайдера × полный цикл. Dual-transport live на обоих плечах.
- **DOCS-CONSOLIDATION:** ✅ CLOSED. 1 коммит `9e61966` — blueprint §9-10, ADR-013/14/15, supersede deploy5, planning dedup.
- **FOOTGUN E:** ✅ CLOSED. `_format_gateway_error()` — status+body capture. 3 hermetic теста. Commit `2084cee`.
- **UI-F1a:** ✅ CLOSED. Overview enrichment (runs_summary, error_rate, RPD budgets, registry_version) + settings live. Commit `7106f9f`.
- **HEAD:** `7106f9f` — feat(ai_control): enrich overview with runs summary, error rate, RPD budgets, registry version (UI-F1a)
- **origin/main:** `9e61966` docs-consolidation (2 unpushed: FOOTGUN E + UI-F1a).

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
- **5c.1 (subagent roles):** ✅ **ЗАКРЫТ.**
- **5c.3 (Gemma 4 31B host-config + gateway):** ✅ **ЗАКРЫТ.**
- **5c.2 (multi-role scheduler):** ✅ **ЗАКРЫТ.**
- **5c.4 (live smoke 4 роли):** ✅ **ЗАКРЫТ.**
- **DEPLOY-CUTOVER** (pg_dump live→podman): 📋 отложен.

## Pending

- **DOCS-RECON:** ✅ CLOSED (read-only, 0 коммитов).
- **UI-Ф1a overview enrichment:** ✅ CLOSED. Commit `7106f9f`.
- **Provider pool free-tier:** 📋 Emma → список сайтов-источников → LiteLLM config.yaml пул. ADR-013 v1 — gateway-side, 0 кода Clay.
- **Retention/index `ai_agent_runs`:** 📋 база растёт (~1152/день@300s×4). Package с latency/token/cost capture (Ф1b).
- **UI-Ф1b** (latency/token capture + retention): 📋 нужны колонки в `ai_agent_runs` — бандл с retention.
- **UI-Фаза 2-3** (write/governance, чат-окно, промпты в БД): 📋 ADR-014.

## Critical Context

- **Live-5432** НЕ ТРОГАТЬ. **Podman-5433** — рабочая БД.
- **CLAY_DATABASE_URL** = `127.0.0.1:5433` (podman). Канонический путь `backend/.env`.
- **TUN UP** (exit=🇳🇱 Netherlands, MIRhosting). Kill-switch вооружён.
- **LiteLLM:** host-native (uv tool, 1.88.1), порт 4000, systemd --user unit, **6 моделей**.
- **Ollama:** system-сервис, порт 11434.
- **Dual-transport:** RoutingModelClient per-call по transport-полю registry.
- **3 live провайдера:** Ollama (local), TokenRouter (MiniMax-M3), Google (Gemini).
- **test:** 466 passed. Ruff 0 / Pyright 0.
- **SSE heartbeat:** `clay/events/sse.py` — `sse_event_stream()` с keep-alive каждые 15s.
- **Тик 4 ролей ≈ 52s sequential.** Интервал 300s (запас ×5.7).
- **FOOTGUN E закрыт:** `_format_gateway_error()` — status+body в error-строку.

## Commits (сессия)

| SHA | Message |
|-----|---------|
| `7106f9f` | feat(ai_control): enrich overview with runs summary, error rate, RPD budgets, registry version (UI-F1a) |
| `2084cee` | fix(ai_control): capture gateway status+body in run error (FOOTGUN E) |
| `9e61966` | docs(ai-layer): consolidate AI-layer docs (blueprint §9-10 + ADR-013/14/15 + supersede deploy5 + e5 path-fix + planning dedup/migrate + backlog reorder + index update) |
| `c0a53f5` | fix(api): SSE heartbeat + shared stream helper (FOOTGUN F) |
| `7e88747` | docs(ai_control): roles taxonomy + hierarchy v1 notes (5c.5) |
| ... | (предыдущие коммиты) |
