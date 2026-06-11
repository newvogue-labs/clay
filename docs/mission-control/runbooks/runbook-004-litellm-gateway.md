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
| pytest | `cd backend && uv run pytest -q` | `410 passed` |
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

## 7. Эксплуатация

```

systemctl --user status clay-litellm.service

journalctl --user -u clay-litellm.service -n 100 --no-pager

systemctl --user restart clay-litellm.service

```

## 8. Секреты и провайдерские ключи

- Ключи в git **не хранятся** (reference-конфиг обезличен).
- Бэкап ключей старой podman-инсталляции:
  `~/.config/clay/_backup/old-podman-litellm-*.tar.gz` (chmod 600, содержит `.env`).
- Для 5b: восстановить ключи из бэкапа **или** завести Gemini free-tier (ADR-010),
  добавить запись в `model_list`, протестировать boundary-live за TUN + kill-switch.

## 9. Fallback — podman (контингент)

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

## 10. Reference-артефакты в репо

- `deploy/litellm/config.yaml.example` — обезличенный шаблон конфига.
- `deploy/litellm/clay-litellm.service` — шаблон systemd --user unit.
