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

## Альтернативы

- OpenAI / Anthropic (платно). Отклонено: стоимость.
- Полностью локальный chief (Ollama). Отклонено сейчас (качество/железо), **ревизуемо** как fallback/последняя инстанция.
