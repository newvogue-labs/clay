# Runbook-004 — LiteLLM Gateway (внешний LLM egress-boundary Clay)

> **Статус:** ✅ host-native установка применена и зелёная (DEPLOY-5 / 5a-ii).
> **ADR:** [ADR-009 — External LLM Egress Gateway](../adrs/009-external-llm-egress-gateway.md)
> **Связанные:** [ADR-010 (Gemini free-tier)](../adrs/010-chief-agent-gemini-free-tier.md), runbook-003 (kill-switch).

## 1. Назначение

LiteLLM — **единственная** точка исходящего трафика к LLM-провайдерам. Код Clay
ходит к моделям только через OpenAI-совместимый HTTP-эндпоинт шлюза
(`http://127.0.0.1:4000`), напрямую к провайдерам не обращается. Это даёт:
централизованный egress-контроль (kill-switch + geo-allowlist), единый
OpenAI-API-контракт, и развязку версий/зависимостей от backend.

## 2. Архитектурная граница

### Внешние провайдеры (Gemini, ADR-010) — через LiteLLM

```

clay backend (py3.14, src/clay/llm/LLMAdapter)

│  HTTP, OpenAI-compat  POST /v1/chat/completions

▼

LiteLLM gateway  127.0.0.1:4000   (py3.13 managed-uv, отдельный процесс)

│  провайдерские вызовы

▼

egress boundary (singbox_tun + kill-switch, runbook-003) → провайдер

```

`LLMAdapter` импортирует litellm **не** в процесс — связь только по HTTP.

### Локальная модель (Gemma 4) — native Ollama /api/chat

```

clay backend (AgentRunner → OllamaNativeClient)

│  HTTP POST /api/chat  (stream:false, think:true)

▼

Ollama 127.0.0.1:11434   (gemma4:e2b-it-qat, num_ctx=65536)

│  loopback (TUN/kill-switch не участвует)

```

**Причина обхода LiteLLM:** OpenAI-совместимый `/v1` эндпоинт Ollama возвращает
пустой `content` для моделей с thinking-шаблоном (Ollama #15288) при `think:false`.
Native `/api/chat` с `think:true` возвращает раздельные `thinking` + `content`.
Это **намеренное решение** (ADR-009 addendum, 2026-06-11) — локальный транспорт
не создаёт неконтролируемого egress, так как идёт по loopback без TUN.

## 3. Почему pinned Python 3.13 (хотя на хосте 3.14)

Осознанное решение, **не** баг:

- Шлюз изолирован от Clay по HTTP-границе — общий интерпретатор не нужен.
- litellm 1.88.1 и его C-расширения (pydantic-core, httpx, orjson, tokenizers)
  не гарантированы на свежем 3.14 (нет части wheel'ов → риск в долгоживущем proxy).
- `uv tool install --python 3.13` создаёт managed-интерпретатор, развязанный с
  хостовым 3.14; апгрейд хоста 3.14→3.15 шлюз не сломает.
- Эмпирически подтверждено: на 3.13 установка чистая, `/health/liveliness`=200.

## 4. Установка (host-native, основной путь)

```

# 4.1 LiteLLM как изолированный uv-tool на managed Python 3.13

uv tool install --python 3.13 'litellm[proxy]'   # → ~/.local/bin/litellm (1.88.1)

# 4.2 конфиг (из reference-копии репо, без секретов)

mkdir -p ~/.config/clay/litellm

cp deploy/litellm/config.yaml.example ~/.config/clay/litellm/config.yaml

# при необходимости отредактировать model_list под реальные ключи/модели

# 4.3 systemd --user unit

cp deploy/litellm/clay-litellm.service ~/.config/systemd/user/clay-litellm.service

systemctl --user daemon-reload

systemctl --user enable --now clay-litellm.service

# 4.4 linger (чтобы --user сервис жил без активной сессии)

loginctl enable-linger "$USER"

```

## 5. Гейты здоровья

| Гейт | Команда | Эталон |
| --- | --- | --- |
| unit active | `systemctl --user is-active clay-litellm.service` | `active` |
| liveliness (local-only) | `curl -s http://127.0.0.1:4000/health/liveliness` | `200` |
| base_url адаптера | `echo "$CLAY_LLM_BASE_URL"` | `http://127.0.0.1:4000` |
| pytest | `cd backend && uv run pytest -q` | `430 passed` |
| рантайм-egress | аудит трафика на `/health/liveliness` | `0` внешних |

> `/health/liveliness` — **локальный** пинг (без провайдеров). Полный `/health`
> пингует модели → реальный провайдерский egress, поэтому отложен на 5b.

## 6. Известный нюанс — `:cloud` модели

Все локальные Ollama-модели — `:cloud`-варианты (напр. `deepseek-v4-flash:cloud`)
и требуют подписки `ollama.com/upgrade`. Поэтому E2E через них даёт
`500 litellm.APIConnectionError: "this model requires a subscription"` — это
**ожидаемо**, шлюз при этом исправен (liveliness=200). Полноценный E2E (5b)
требует **либо** локально спуленной не-cloud модели (`ollama pull llama3.2`),
**либо** реальных провайдерских ключей (см. §8).

## 7. AI agent cycle (chief-agent)

Периодический async-джоб, зарегистрированный в `ClayScheduler` при
`CLAY_SCHEDULER_AI_AGENT_ENABLED=true` (default **false**). Выполняет
один полный цикл «наблюдение → размышление → запись».

### Флаги

| Переменная | Default | Описание |
| --- | --- | --- |
| `CLAY_SCHEDULER_AI_AGENT_ENABLED` | `false` | Включить цикл. **Opt-in.** |
| `CLAY_SCHEDULER_AI_AGENT_INTERVAL_SECONDS` | `300` | Интервал между стартами цикла (сек). |
| `CLAY_SCHEDULER_AI_AGENT_ROLE_ID` | `chief-agent` | Роль, под которой runner резолвит модель. |

### Путь данных

```
scheduler tick (interval)
  → AIAgentCycleJob.run_once()
    → asyncio.to_thread → build_snapshot(session)     # AI-control snapshot
    → _render_context(snapshot)                        # 7 plain-text секций
    → AgentRunner.run_agent(role_id, context)          # ModelResolver → ModelClient
      → локальный транспорт: OllamaNativeClient
        → POST /api/chat (127.0.0.1:11434)
    → asyncio.to_thread → AIAgentRun → session.commit  # ops.ai_agent_runs
```

### Модель и ресурсы

- **Модель:** `gemma4:e2b-it-qat` (Google Gemma 4, E2B instruct, QAT q4_0, 4.3 GB).
- **Ollama:** `OLLAMA_CONTEXT_LENGTH=65536`, `OLLAMA_NUM_PARALLEL=1`.
- **VRAM (GTX 1660 SUPER 6 GB):** idle ~0.6 GB → пик ~2.6 GB (подтверждено live 2026-06-11).
- **Latency:** первый цикл ~19s (загрузка модели в VRAM), последующие ~6s (горячий кеш).

### ⚠️ Governance gate (обязателен перед go-live)

Текущее штатное назначение роли `chief-agent` — `openai-gpt-5.4` (cloud-заглушка).
**Перед постоянной активацией** `CLAY_SCHEDULER_AI_AGENT_ENABLED=true` необходимо:

1. Добавить локальную модель в реестр моделей (`AIControlService._build_model_registry`) — через PR.
2. Переназначить `chief-agent → gemma4:e2b-it-qat` штатным governance-путем
   (`review_assignment → apply_assignment`, через API control center).

Прямые DB-insert'ы в `ops.ai_assignments` допустимы **только** в attended-smoke.

### Procedura attended smoke (кратко)

```bash
# 1. Флип .env
export CLAY_SCHEDULER_AI_AGENT_ENABLED=true
export CLAY_SCHEDULER_AI_AGENT_INTERVAL_SECONDS=60

# 2. Старт
uv run --env-file .env python -m clay

# 3. Проверка через 2-3 цикла
curl -s 127.0.0.1:8000/health/ready                     # healthy
psql 'postgresql://clay:pass@127.0.0.1:5433/clay' -c '
  SELECT id, created_at, role_id, model_id,
         length(content), length(thinking), error
  FROM ops.ai_agent_runs ORDER BY id DESC LIMIT 5;'

# 4. Revert
# CLAY_SCHEDULER_AI_AGENT_ENABLED=false
```

## 8. Эксплуатация

```

systemctl --user status clay-litellm.service

journalctl --user -u clay-litellm.service -n 100 --no-pager

systemctl --user restart clay-litellm.service

```

## 9. Секреты и провайдерские ключи

- Ключи в git **не хранятся** (reference-конфиг обезличен).
- Бэкап ключей старой podman-инсталляции:
  `~/.config/clay/_backup/old-podman-litellm-*.tar.gz` (chmod 600, содержит `.env`).
- Для 5b: восстановить ключи из бэкапа **или** завести Gemini free-tier (ADR-010),
  добавить запись в `model_list`, протестировать boundary-live за TUN + kill-switch.

## 10. Fallback — podman (контингент)

Host-native — основной путь. Если он недоступен, образ оставлен как fallback:

```

# образ сохранён локально (НЕ удалять):

podman images | grep litellm   # ghcr.io/berriai/litellm:main-stable (~1.93GB)

podman run -d --name clay-litellm \

-p 127.0.0.1:4000:4000 \

-v ~/.config/clay/litellm/config.yaml:/app/config.yaml:ro \

ghcr.io/berriai/litellm:main-stable \

--config /app/config.yaml --host 0.0.0.0 --port 4000

```

Podman-вариант используется **только** при отказе host-native; держать оба
одновременно на `:4000` нельзя.

## 11. Reference-артефакты в репо

- `deploy/litellm/config.yaml.example` — обезличенный шаблон конфига.
- `deploy/litellm/clay-litellm.service` — шаблон systemd --user unit.
