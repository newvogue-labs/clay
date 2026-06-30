> **STATUS: SUPERSEDED (2026-06-13).** Написан до реализации кода;
> live-правда AI-слоя — в `blueprint-v1.md` §9–§10 и `runbooks/runbook-004`.
> Документ сохранён как исторический контекст deploy5 (слайсы 5a–5e).
> Namespace в тексте — планировочный (`clay_mc`, `app/backend`); реальный код использует `clay` / `backend`.

# DEPLOY-5 — AI Model Layer Implementation Plan

> **For agentic workers:** Implement slice-by-slice per build spec. Each slice passes its gate before next begins.
>
> **Paths:** актуальный layout `backend/src/clay/` (НЕ устаревший `clay_mc/` из E5-плана).

Дата: 2026-06-10
Эпик: `E5` (deployment increment)
Build spec: ../build_specs/deploy5-ai-model-layer.md
Dependencies: E1, E2, E5, ADR-005, ADR-009..012

## 1. Objective

По завершении: Clay делает реальные LLM-вызовы через локальный шлюз в async-цикле, chief синтезирует выводы суб-агентов, forecast считается локально, governance-активация работает, privacy-постура (kill-switch/TUN/never-US) подтверждена egress-аудитом, baseline зелёный.

## 2. Current Context (из recon R1–R9)

- **Реестр/роли:** `src/clay/ai_control/service.py` (~28K), `models.py`; назначения `ops.ai_assignments`; `INITIAL_ASSIGNMENTS` в `db/repositories_runtime_state.py:41-46`.
- **Вызова генерации НЕТ** (R3): `provider`/`model_id` читаются только в `_build_assignments`, `_build_conflicts`, `_simulate_conflicts`, `_build_review_card`. → `AgentRunner.run_agent` пишем с нуля.
- **Зависимости (R2):** только `httpx`. Нет openai/anthropic/google.genai/litellm-python. → adapter на httpx.
- **Каданс (R5):** `ClayScheduler` async jobs (health 30s, ingestion 60s, reliability 300s, ops-retention 86400s). `build_snapshot()` СИНХРОННЫЙ, зовётся из API.
- **Новости (R4):** `ingestion/context/connectors/demo_news.py` (+demo sentiment); `db/repositories_context.py` (store/latest news+sentiment).
- **Конфиг (R6):** 6 env-vars; LLM-ключей нет; `config/models.py`, `settings/{ingestion,scheduler}`.
- **validation_lab (R7):** `validation_lab/service.py` — `run_validation`, `review_activation` (target_type='model_assignment'✅), `apply_activation`→`set_assignment` (upsert+audit+event).
- **signal_engine:** `signal_engine/service.py` — детерминированный, sentiment≥0.6 bull/≤0.4 bear.
- **Baselines (R8):** pytest 407 passed + 2 failed (`tests/api/test_entrypoint.py::test_main_host_default`, `tests/db/test_ingestion_schema.py::test_ingestion_settings_expose_v1_timeframes`); pyright 33; ruff 13.
- **CLI/шлюз (R9):** LiteLLM нашёлся в системе только как podman-образ `ghcr.io/berriai/litellm:main-stable`. **Решение DEPLOY-5:** ставим host-native (uv/pipx venv, systemd --user, uid 1000) как primary ради стабильности и прямого покрытия kill-switch; podman — fallback.

## 2.5 Окружение исполнения (host, verified 2026-06-10)

- **ОС/ядро:** CachyOS, kernel 7.0.11-cachyos; Wayland/KDE Plasma 6.6.5.
- **CPU/RAM:** Intel i5-4590 (4 ядра), 32 ГиБ.
- **GPU:** NVIDIA GTX 1660 SUPER (6 ГБ); driver 610.43.02; CUDA Toolkit 13.3.0.
- **Python:** 3.14.4 (проект — `uv`); Node 26.1 / Bun 1.3.14 — только UI-трек, вне DEPLOY-5.
- **Контейнеры:** Podman 5.8.2 + Podman Compose 1.6.0; NVIDIA Container Toolkit 1.19.1 (GPU в контейнерах). **Docker НЕ установлен** — все контейнерные шаги только podman/podman-compose.
- **LLM локально:** Ollama 0.30.7 (CUDA 13.3.0) — last resort; Gemini CLI 0.45.2 — dev-проверки.
- **Сеть/безопасность:** v2rayN/sing-box/xray (проверенный egress-путь); mitmproxy + Wireshark + nmap (egress/data-exfil верификация); UFW, WireGuard. Mullvad/AmneziaVPN/Clash Verge Rev на хосте — **вне scope** (egress на проверенном пути, FOOTGUN C).
- **Инструменты:** git 2.54, gh 2.93, ripgrep 15.1, DBeaver 26.1; менеджеры версий mise/pdm/paru (для host-native шлюза).

## 3. Implementation Slices

### Slice 5a — Adapter + LiteLLM gateway + config + smoke + fix 2 tests
- [ ] `src/clay/llm/adapter.py`: `LLMAdapter` (httpx, OpenAI-compat), таймаут, ошибки→degraded.
- [ ] Слой минимизации контекста (запрет секретов/PII/балансов/ключей).
- [ ] LiteLLM gateway **host-native** (uv/pipx venv + `systemd --user`, работает как emma/uid 1000 → напрямую под kill-switch): `config.yaml` (logical→provider routing, ключи в шлюзе), bind `127.0.0.1:4000`. Podman-образ `ghcr.io/berriai/litellm:main-stable` — задокументированный fallback (см. runbook-004).
- [ ] `.env`: `CLAY_LLM_BASE_URL` (+опц. master key); settings-поле.
- [ ] Smoke-тест adapter **без внешнего egress** (локальный stub/mock).
- [ ] Починить/ре-бейзлайн 2 pre-existing fail; ruff не растёт.
- **Гейты:** pytest зелёный; smoke ок; 0 внешних обращений в тестах.

### Slice 5b — Chief-agent live
- [ ] `AgentRunner.run_agent(role_id, context)` в `ai_control`.
- [ ] Async job `ai-agent-cycle` в ClayScheduler (off request-path).
- [ ] Persist выводов: решить `ops.ai_agent_outputs` (new) vs расширить `ai_control_state`; alembic-миграция (после 0014).
- [ ] chief = Gemini free-tier через шлюз; backoff + fallback-chain.
- [ ] Latency-бюджет; audit `agent.run`.
- [ ] **Kill-switch тест: TUN down → 0 утечек**, роль degraded.
- **Гейты:** реальный вызов ок; 0-leak подтверждён; миграция-тест.

### Slice 5c — Subagents
- [ ] market-scanner live (через шлюз; relay/локально per ADR-010).
- [ ] news-sentiment на demo-коннекторах (ADR-012), низкоуверенный вход.
- [ ] Orchestration flow: scanner→news→forecast→chief синтез.
- [ ] Конфликты видимы; роли не делают override market signal.
- **Гейты:** flow прогоняется в job; demo-news помечен; тесты.

### Slice 5d — Forecast quant (local)
- [ ] Датасет-пайплайн из `market.market_bars` (фичи, таймфреймы).
- [ ] Тренировка: локально на GPU (GTX 1660 SUPER 6 ГБ, CUDA 13.3.0, driver 610.43.02, PyTorch CUDA) — учитывать лимит 6 ГБ VRAM (компактные LSTM/TCN/лёгкий Transformer); либо burst Lightning.ai (training-only, data-egress по ADR-009). Опц. подъём в podman с NVIDIA Container Toolkit 1.19.1.
- [ ] Локальный инференс; артефакт-стор модели; gemini опц. fallback.
- [ ] Поглощает ML-track карточки карты (ресинк по ADR-011).
- **Гейты:** локальный инференс без внешнего egress; метрики forecast.

### Slice 5e — Validation A/B + governed activation
- [ ] `run_validation` (model_comparison/live_test) для пары моделей.
- [ ] `review_activation` → review-card → `apply_activation` (model_assignment).
- [ ] Запрет silent-switch; audit+event.
- **Гейты:** A/B пишет `validation.validation_runs`; апплай через governance.

### Cross-cut (сквозной слайс)
- [ ] data-exfil политика (документ + проверки в adapter).
- [ ] positive geo-allowlist (never-US) на шлюзе/сети.
- [ ] egress-аудит (периодическая проверка исходящего IP/страны).
- [ ] kill-switch расширить на контейнер шлюза (fail-closed).

## 4. Sequencing

5a → 5b → (5c ∥ 5d) → 5e. Cross-cut идёт параллельно, обязателен до «boundary live» в 5b.

## 5. Baselines & Gates (держать на каждом слайсе)

- pytest: старт 407 passed +2 fail → после 5a **409 зелёный** (или явный ре-бейзлайн).
- pyright ≤ 33; ruff ≤ 13 (не растёт).
- БД = clay @ 5433; миграции через `uv run --env-file .env alembic upgrade head`.
- Запуск: `uv run --env-file .env python -m clay`.
- Egress только через TUN; live-5432 не трогать; v2rayN/sing-box не трогать (FOOTGUN C).

## 6. Open Questions

- Persist: новая таблица vs расширение (5b).
- Forecast inference in-process vs local endpoint за шлюзом (5d).
- Таймфреймы/горизонт обучения forecast (5d).
