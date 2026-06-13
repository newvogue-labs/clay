> **STATUS: SUPERSEDED (2026-06-13).** Написан до реализации кода;
> live-правда AI-слоя — в `blueprint-v1.md` §9–§10 и `runbooks/runbook-004`.
> Документ сохранён как исторический контекст deploy5 (слайсы 5a–5e).

# DEPLOY-5 Build Spec — AI Model Layer

Дата: 2026-06-10
Эпик: `E5` (deployment increment)
Статус: draft
Основа:
- ADR-005 (model-provider-abstraction), ADR-009..012
- `../../architecture/deploy5-ai-model-layer.md` (архитектурный план)  
- отчёт DEPLOY-5-RECON (R1–R9)

## 1. Goal

Подключить **реальный слой вызова моделей** поверх готового скелета `ai_control` (роли, реестр моделей, назначения в `ops.ai_assignments`, governance review→apply). Сейчас модели — data-class заглушки без единого вызова API; `signal_engine` и forecast работают на детерминированной эвристике. Нужно дать живые вызовы, не нарушив privacy-постуру (kill-switch, весь egress через TUN, never-US) и human-in-loop (attended-торговля).

## 2. User/System Scenarios

### Scenario 1: периодический прогон агентов
- **Trigger:** async scheduler-job `ai-agent-cycle` (новый, off request-path).
- **Preconditions:** TUN поднят; шлюз LiteLLM жив; назначения ролей в `ops.ai_assignments`.
- **Steps:** job → `AgentRunner.run_agent(role)` → LLM-adapter (httpx) → LiteLLM gateway → провайдер → результат → persist в `ops`.
- **Expected:** свежие выводы агентов в БД; `build_snapshot` (sync, API) читает кэш.
- **Failure:** TUN down → шлюз fail-closed → adapter ловит ошибку → роль degraded, прошлый результат помечается stale; **0 утечек**.

### Scenario 2: chief синтезирует итог
- **Trigger:** после суб-агентов в рамках цикла.
- **Steps:** chief-agent (Gemini free-tier через шлюз) собирает market-scanner + news-sentiment + forecast → синтез + объяснение + вскрытие конфликтов (не имеет права silent-switch).
- **Failure:** rate-limit free-tier → backoff → fallback-chain (`fallback_ready`); при исчерпании — degraded с видимой причиной.

### Scenario 3: смена назначения модели (governance)
- **Trigger:** оператор/validation_lab предлагает новое `model_assignment`.
- **Steps:** `validation_lab.review_activation` → review-card → `apply_activation` → `AIControlService.set_assignment` (upsert + audit + event).
- **Failure:** review blocked/staged → апплай не проходит, аудит фиксирует.

## 3. In Scope

- LLM-adapter `src/clay/llm/` (httpx, OpenAI-совместимый), без вендор-SDK.
- LiteLLM gateway (**host-native, systemd --user, uid 1000 — primary**; podman-образ — fallback), `127.0.0.1:4000` + `config.yaml` (ключи в шлюзе).
- `AgentRunner.run_agent(role_id, context)` в `ai_control`.
- Новый async scheduler-job `ai-agent-cycle`.
- Персист выводов агентов в `ops`.
- Реальные `ModelVersion` + provider-routing вместо заглушек.
- Локальная forecast-модель (quant) + датасет из `market.market_bars`.
- Subagents wiring (market-scanner; news-sentiment на demo per ADR-012).
- validation_lab A/B + governed activation (использует готовый механизм).
- Cross-cut: data-exfil политика, geo-allowlist, egress-аудит, kill-switch покрывает шлюз.
- Починка 2 pre-existing fail; держать baseline зелёным.

## 4. Out Of Scope

- Реальный источник новостей (NewsAPI/X/Reddit) — отложенный под-трек (ADR-012).
- Любой UI/frontend (DEPLOY-5 — backend-only).
- Платные провайдеры как основные (ADR-010).
- Авто-рестарт v2rayN/sing-box (FOOTGUN C) — только оператор.
- Cutover live-5432 (отдельный DEPLOY).

## 5. Backend Responsibilities

- **Endpoints:** изменений API-контракта не тре��уется для v1 (вызовы — в job). Опц. статус-поле в существующем control-эндпоинте.
- **Services:** `src/clay/llm/adapter.py` (LLMAdapter), `ai_control` `AgentRunner`, расширение `AIControlService`.
- **Jobs:** `ai-agent-cycle` (async, ClayScheduler), бюджет/таймаут на LLM.
- **Validation:** проверка base_url, доступности шлюза, geo-allowlist.
- **Audit:** каждый прогон агента и смена назначения → audit-событие.

## 6. Data Contracts

### LLM-adapter (внутренний, OpenAI-compat через шлюз)
```json
{ "model": "<logical-name>", "messages": [{"role":"system","content":"..."},{"role":"user","content":"<минимизированный контекст>"}], "temperature": 0.2, "max_tokens": 512 }
```
### Agent output (persist)
```json
{ "role_id": "chief-agent", "model_id": "gemini-2.5-flash", "produced_at": "<iso>", "summary": "...", "explanation": "...", "conflicts": [], "confidence": 0.0, "degraded": false }
```

## 7. Storage Changes

- Новая таблица `ops.ai_agent_outputs` (или расширение `ops.ai_control_state`) — последние выводы по ролям + метаданные (model_id, produced_at, degraded, confidence). Решить на 5b (см. Open Questions).
- Alembic-миграция (следующий номер после 0014).
- Retention: ops-retention job (уже есть, 86400s) расширить.

## 8. Config Changes

- Clay `.env`: добавить **только** `CLAY_LLM_BASE_URL` (+ опц. `CLAY_LLM_MASTER_KEY`).
- Вендор-ключи — **в config шлюза** (`litellm config.yaml`), не в Clay.
- Defaults: `CLAY_LLM_BASE_URL=http://127.0.0.1:4000`.
- Validation: при старте проверять reachability шлюза (не падать жёстко — degraded, если недоступен).

## 9. Observability And Audit

- Логи прогона агентов (latency, model_id, degraded).
- Метрики: успех/ошибка вызовов, rate-limit hits.
- Health: статус шлюза в reliability.
- Audit-события: agent.run, assignment.changed.
- **Egress-аудит:** периодическая проверка исходящего IP/страны (never-US), 0-leak при TUN down; **mitmproxy** для L7-проверки data-exfil (что реально уходит в провайдеров, ADR-009).

## 10. Reliability And Degraded Mode

- Degraded если: TUN down, шлюз недоступен, провайдер 429/5xx, исчерпан fallback.
- В degraded: используем последний валидный вывод (помечен stale), сигналы не доминируются устаревшими данными; торговля остаётся attended.
- Kill-switch покрывает контейнер шлюза (fail-closed).

## 11. Acceptance Criteria

- [ ] `run_agent` делает реальный вызов через шлюз и возвращает структурированный вывод.
- [ ] `ai-agent-cycle` работает в async-планировщике, не блокирует request-path.
- [ ] При TUN down — **0 внешних утечек** (egress-аудит подтверждает), роль degraded.
- [ ] chief на Gemini free-tier; суб-агенты/forecast по ADR-010/011; назначения через governance.
- [ ] forecast — локальный инференс на обученной quant-модели.
- [ ] news-sentiment на demo (ADR-012), низкоуверенный вход.
- [ ] validation_lab A/B + apply_activation для `model_assignment` работают.
- [ ] pytest зелёный (2 pre-existing fail починены/ре-бейзлайн); ruff не растёт; pyright не растёт.

## 12. Test Requirements

- Unit: adapter (mock httpx), run_agent, миними��ация контекста (запрет секретов/PII).
- Service: scheduler job, persist, degraded-переходы.
- Integration (без внешнего egress): шлюз-mock/локальный stub.
- Failure-mode: TUN-down 0-leak, rate-limit fallback.
- Migration test для новой таблицы.

## 13. Risks

- Free-tier лимиты Gemini → нужен надёжный fallback.
- Локальная quant-модель на 6GB GPU — ограничение размера.
- Context-minimization ошибки → риск exfil (тесты обязательны).
- Расхождение ML-track карточек карты проекта (ресинк по ADR-011).

## 14. Open Questions

- Новая таблица `ops.ai_agent_outputs` vs расширение `ai_control_state`? (решить на 5b)
- Где запускать local forecast inference — в процессе Clay или отдельным local endpoint за шлюзом? (5d)
- Шаг датасета/таймфреймы для обучения forecast. (5d)
