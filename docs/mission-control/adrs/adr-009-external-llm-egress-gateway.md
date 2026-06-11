# ADR-009 — Внешние LLM только через локальный шлюз за TUN

Дата: 2026-06-10
Статус: accepted
Связанные эпики: `E5`, `DEPLOY-5`
Решение пользователя: 4B
Связанные ADR: ADR-005 (расширяет), ADR-010, ADR-011

## Контекст

Clay работает в жёсткой privacy-постуре: kill-switch (`meta skuid 1000`), весь egress через TUN (`singbox_tun` → sing-box → VPS, never-US), attended-торговля. DEPLOY-3 подтвердил: при опущенном TUN исходящий трафик утекает на домашний ISP РФ (leak confirmed). Recon R2 показал, что в проекте **нет LLM SDK** — только `httpx`. Recon R9: LiteLLM доступен как podman-образ `ghcr.io/berriai/litellm:main-stable`; coding-CLI только headless, без серверного режима.

Задача — дать Clay доступ к внешним моделям, не создавая новых неконтролируемых каналов egress и не размазывая вендорские ключи по приложению.

## Решение

Все обращения к внешним LLM идут **только** через единый локальный шлюз **LiteLLM** (podman, bind `127.0.0.1:4000`, OpenAI-совместимый API).

- Clay общается со шлюзом по HTTP через `httpx`; знает только `CLAY_LLM_BASE_URL` (+ опц. master key). Никаких вендор-SDK в коде Clay.
- Вендорские API-ключи живут **в конфиге шлюза**, не в `.env` Clay.
- Egress контейнера шлюза обёрнут в TUN и покрыт kill-switch: при падении TUN шлюз **fail-closed** (запросы к внешним провайдерам не уходят мимо туннеля).
- Перед отправкой — **минимизация/обезличивание контекста**: только рыночные фичи и минимальный промпт; запрещено передавать секреты, ключи, балансы, идентификаторы аккаунта, PII (data-exfil политика).
- Один контейнер = единая точка для аудита egress, geo-allowlist и kill-switch.

## Последствия

- Единый chokepoint для egress-аудита и аварийного отруба.
- Нужен runbook шлюза (запуск/восстановление/проверка egress) — см. α2 `runbook-004-litellm-gateway.md`.
- Нужен слой минимизации контекста в LLM-адаптере (`src/clay/llm/`).
- Нужен positive geo-allowlist на стороне шлюза/сети.
- Никакой прямой вендор-интеграции в Clay — только через шлюз (усиливает ADR-005).

## Альтернативы

- **(A) Только локальные модели** (Ollama / local quant), без внешнего egress вовсе. Отклонено для v1: на GTX 1660 SUPER (6GB) качество reasoning chief-agent недостаточно. **Право пересмотра в сторону (A) сохраняется** — по мере тестов слой шлюза можно свернуть к полностью локальному без изменения контракта адаптера.
- Прямые вендор-SDK в Clay. Отклонено: размазывает ключи, ломает единый egress-chokepoint, противоречит ADR-005.

---

## Addendum (2026-06-11): Ратифицировано по итогам 5b-ii

### Dual-transport

Решение, не описанное в теле ADR, ратифицировано post-factum:

| Транспорт | Модели | Путь | Причина |
| --- | --- | --- | --- |
| **Native Ollama** `/api/chat` | `gemma4:e2b-it-qat`, локальные | `AgentRunner → OllamaNativeClient` → `127.0.0.1:11434` loopback | Ollama #15288 — OpenAI `/v1` с `think:false` возвращает пустой `content` на моделях с thinking-шаблоном. Native API с `think:true` возвращает раздельные `thinking` + `content`. |
| **LiteLLM gateway** | Cloud-модели (Gemini, ADR-010) | `LLMAdapter` → `127.0.0.1:4000` → TUN → kill-switch → провайдер | Единый egress-chokepoint, fail-closed при падении TUN. |

Локальный транспорт не создаёт неконтролируемого egress — loopback, TUN не участвует.

### Параметры модели

- `num_ctx=65536` при 100% GPU ≈ 2.5 GB VRAM на GTX 1660 SUPER (6 GB).
- `OLLAMA_NUM_PARALLEL=1` (один запрос за раз, OOM-prevention).
- Модель: `gemma4:e2b-it-qat` (4.3 GB, QAT q4_0, E2B instruction-tuned).
- `think:true` **всегда включён** — через `think:false` формат ответа ломается.

### Отвергнутые engine'ы

- **vLLM / SGLang:** multi-user серверы, требуют >6 GB VRAM для gemma4, OOM на текущем GPU.
- **llama.cpp:** **санкционированный upgrade-путь** при необходимости (подтверждён ADR-011 как fallback-движок для forecast-lite). В текущей архитектуре не используется.

### Governance

- Runner (`AgentRunner.run_agent`) **только читает** `assignments` через `ServiceModelResolver`.
- Validation (`_validate_role_and_model`) и apply (`apply_assignment`) живут в `AIControlService`.
- Этот ADR **не меняет** правило: изменение назначения модели — через штатный review→apply путь, не через прямой DB insert (запрещён вне attended-smoke).
