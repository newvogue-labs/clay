> **Историческая запись (решение 2026-06-10).** Текущий chief-agent — `minimax-m3` (nvidia-nim), не Gemini free-tier: ADR-017 сделал all-Google tier лишь *опцией* (eligibility), дефолт рантайма = `minimax-m3` (`INITIAL_ASSIGNMENTS`); см. ADR-017 и `runbooks/runbook-004`. Маршрутизация через LiteLLM-шлюз (ADR-009) сохраняется. Тело ниже не переписано — фиксирует исходное решение.

# ADR-010 — Chief-agent на Gemini free-tier через шлюз

Дата: 2026-06-10
Статус: accepted
Связанные эпики: `E5`, `DEPLOY-5`
Решение пользователя: 3 (Gemini)
Связанные ADR: ADR-005, ADR-009

## Контекст

Chief-agent — оркестратор: синтезирует выводы суб-агентов (market-scanner, news-sentiment, forecast) и формирует итог, обязан вскрывать конфликты и не имеет права на silent-switch (роль закреплена в `ai_control`). Recon R1: текущее `INITIAL_ASSIGNMENTS` ставит chief→`openai-gpt-5.4` (заглушка). Бюджет проекта на модели — **бесплатный**. Recon R9: доступны Gemini (free-tier/CLI), relay FreeQwenApi для суб-агентов, Ollama локально.

## Решение

Роль **chief-agent** назначается на **Gemini free-tier**, маршрутизируется через LiteLLM-шлюз (ADR-009).

- Суб-агенты (market-scanner, news-sentiment) — более дешёвый/relay-вариант (FreeQwenApi) или локальные модели; **Ollama = last resort**.
- Назначение хранится в `ops.ai_assignments` через существующий governance (review→apply). Никакого hardcode вендора на роль — соблюдается ADR-005.
- Вызовы chief-agent выполняются в async scheduler-job `ai-agent-cycle`, не в request-path (recon R5).

## Последствия

- Free-tier → rate limits: нужен backoff и управляемый fallback-chain (`fallback_ready`), деградация без обвала.
- Латентность chief учитывается в бюджете async-job, не в синхронном `build_snapshot`.
- Смена провайдера chief = governance-операция (review-card), а не правка кода.

## Addendum 2026-06-11 — Dual-transport routing + live-метрики + политика провайдеров

### Архитектура роутинга (5b-iii.1)

Первоначальный дизайн (см. ADR-009 addendum) предполагал static select-функцию
в `lifespan.py`, решающую транспорт один раз на старте app. Это создавало
проблему: governance может сменить назначение в рантайме (review→apply),
а клиент в раннере остался бы stale.

**Решение:** `RoutingModelClient` — композитный `ModelClient`, держит оба
транспорта и диспатчит **per-call по `model_id`**:

```
RoutingModelClient.chat(model_id="minimax-m3")
  → transport_for("minimax-m3")  # "cloud"
  → LiteLLMModelClient.chat(...)
```

- Решение по transport-атрибуту реестра (`local` → Ollama, `cloud` → LiteLLM).
- Неизвестный/без атрибута → fail-loud `ModelUnavailableError`.
- Lifespan-вайринг тривиален: собрал два клиента → обернул в роутер → отдал
  в `AgentRunner`. `AgentRunner` ничего не знает о транспортах.

### Live-метрики (5b-iii.4c, 2026-06-11)

| Метрика | Local (gemma4:e2b-it-qat) | Cloud (minimax-m3 via TokenRouter) |
|---------|---------------------------|-----------------------------------|
| VRAM | idle → пик +2 GB | idle → пик +30 MB |
| Content | 932 / 210 токенов | 1115 / 1718 токенов |
| Thinking | 1607 / 1239 токенов | NULL |
| Latency cold | ~19 s | ~3–5 s (через шлюз) |
| Latency hot | ~6 s | ~3–5 s |

Gemini boundary-live (5b-iii.2): 200, latency 1.23s, 43 токена (12p+31c, 24 reasoning).

### Политика провайдеров (решение Emma 2026-06-11)

- **ДЕМО-режим:** любые бесплатные провайдеры и агрегаторы (TokenRouter,
  Gemini free-tier), но строго через LiteLLM-шлюз за TUN + kill-switch.
- **REAL-MONEY (будущее):** только официальные платные провайдеры с
  контрактом.
- **Секреты:** только `~/.config/clay/litellm/litellm.env` (600),
  никогда в git и никогда через чат.

## Addendum 2026-06-12 — Multi-role sequential cycle + reasoning sematics + RPD budget

### Multi-role: variant A (один job, sequential)

**Проблема:** каждая роль требует отдельного запуска цикла. Если делать N
scheduler job'ов (variant B) — N-кратная нагрузка на APScheduler и
потенциальные race-условия при одновременном старте.

**Решение (variant A, 5c.2):** один job типа `AIAgentCycleJob` выполняет
роли **последовательно** из JSON-списка `CLAY_SCHEDULER_AI_AGENT_ROLE_IDS`.
Список задаётся env-переменной (pydantic `list[str]` → JSON-парсинг):

```python
role_ids: list[str] = ["chief-agent"]
# → export CLAY_SCHEDULER_AI_AGENT_ROLE_IDS='["chief-agent","market-scanner",...]'
```

- Внутренний цикл: для каждого `role_id` → резолв модели → контекст → LLM → persist.
- Ошибка одной роли **не прерывает** цикл — error записывается в строку с
  `model_id="unresolved"`, остальные роли выполняются (per-role isolation).
- Overlap-protection: `max_instances=1` + APScheduler Lock.

### Reasoning fallback семантика (FOOTGUN D)

Gemma 4 31B через Gemini API может возвращать `content: null` при
непустом `reasoning_content`. **Решение:** при пустом `content` — 
fallback к `reasoning_content` в `LiteLLMModelClient.parse_response`.
Если оба пусты — fail-loud `ModelUnavailableError`.

Это **намеренно** не сквозное поведение (не в `ChatMessage` валидации):
fallback на уровне ModelClient позволяет каждому транспортному клиенту
иметь свою логику. `ChatMessage` хранит оба поля.

### RPD budget по ролям (5c.4 live)

| Роль | Модель | RPD | Daily calls@300s | Профицит |
|------|--------|-----|-------------------|----------|
| chief-agent | minimax-m3 (TokenRouter) | не лимитирован | 288 | ∞ |
| market-scanner | gemma-4-31b (Gemini) | 1500 | 288 | ×5.2 |
| news-sentiment-agent | gemma-4-31b (Gemini) | 1500 (shared) | 288 | ×2.6 |
| forecast-model | gemini-3.1-flash-lite | 500 | 288 | ×1.7 |

**Правило:** `daily_calls = 86400 / interval × roles_count`.
Достаточно, если RPD > daily_calls. При interval=300s и 4 ролях:
daily_calls=1152. Лимитирующий фактор — Gemini free-tier (500 RPD на
Flash Lite, 1500 на Gemma, расщепление общей квоты на 2 роли).

### Live-метрики мульти-роль (5c.4, 2026-06-12)

| Роль | Модель | Content | Latency | Error |
|------|--------|---------|---------|-------|
| chief-agent | minimax-m3 | 1539/1178/1757/2284 chars | ~3-5s | NULL |
| market-scanner | gemma-4-31b | 357/556 chars | ~1.4s | NULL (2 успешных) |
| news-sentiment-agent | gemma-4-31b | 544 chars | ~1.4s | NULL |
| forecast-model | gemini-3.1-flash-lite | 421/567 chars | ~0.69s | NULL |

Общее время тика (4 роли sequential): ~52s.

## Альтернативы

- OpenAI / Anthropic (платно). Отклонено: стоимость.
- Полностью локальный chief (Ollama). Отклонено сейчас (качество/железо), **ревизуемо** как fallback/последняя инстанция. После live-пруфа cloud (minimax-m3, VRAM +30MB vs +2GB) локальный chief — шаг назад.

## Addendum 3 — 2026-06-13 — Иерархия v1 + 5c.5 (subagent→chief контекст)

### Механизм (5c.5.1, commit `daa079c`)

Выводы субагентов вклеиваются во **входной контекст** chief-agent через
`list_latest_agent_runs` (OpsRepository, DISTINCT ON role_id, WHERE error IS NULL
AND content IS NOT NULL). Контекст НЕ персистится в `ai_agent_runs.content` —
там хранится только ответ модели. Поэтому пруф синтеза **непрямой**:
сопоставление output content chief vs субагентов.

**Наблюдаемость:** INFO-лог рендера не реализован (backlog). При отладке —
секция `=== subagent_reports ===` присутствует в отрендеренном контексте
на стороне chief до вызова LLM и не пишется в БД.

### Рекомендованный порядок ROLE_IDS

```
["market-scanner", "news-sentiment-agent", "forecast-model", "chief-agent"]
```

Субагенты → chief последним, чтобы chief в своём тике видел результаты
текущего тика. Ошибка субагента не прерывает цикл (per-role isolation),
но chief может не получить данные упавшей роли.

### Smoke-пруф (2026-06-12)

| id | Роль | Модель | Content |
|----|------|--------|---------|
| 31 | market-scanner | gemma4:e2b-it-qat | 230 chars |
| 32 | news-sentiment-agent | gemma4:e2b-it-qat | 1323 chars |
| 33 | forecast-model | gemma4:e2b-it-qat | 337 chars |
| 34 | chief-agent | minimax-m3 | 3387 chars |

Chief явно ссылается на данные каждого субагента (совпадающие факты/формулировки),
что доказывает: синтез-путь работает end-to-end. Условия: local-ollama
(в обход Google RPD), repeatable по процедуре runbook-004 §Re-smoke.
