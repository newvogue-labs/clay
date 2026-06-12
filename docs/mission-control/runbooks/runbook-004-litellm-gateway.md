# Runbook-004 — LiteLLM Gateway (внешний LLM egress-boundary Clay)

> **Статус:** ✅ host-native установка под uid 945 (clay), DEPLOY-3.5e.
> **ADR:** [ADR-009 — External LLM Egress Gateway](../adrs/009-external-llm-egress-gateway.md)
> **Связанные:** [ADR-010 (Gemini free-tier)](../adrs/010-chief-agent-gemini-free-tier.md), runbook-003 (kill-switch).

## 1. Назначение

LiteLLM — **единственная** точка исходящего трафика к LLM-провайдерам. Код Clay
ходит к моделям только через OpenAI-совместимый HTTP-эндпоинт шлюза
(`http://127.0.0.1:4000`), напрямую к провайдерам не обращается. Это даёт:
централизованный egress-контроль (kill-switch + geo-allowlist), единый
OpenAI-API-контракт, и развязку версий/зависимостей от backend.

## 2. Архитектурная граница

### Внешние провайдеры (Gemini, TokenRouter) — через LiteLLM

```
clay backend (py3.14, src/clay/llm/LLMAdapter)
│  HTTP, OpenAI-compat  POST /v1/chat/completions
▼
LiteLLM gateway  127.0.0.1:4000   (py3.13 managed-uv, uid 945, отдельный процесс)
│  провайдерские вызовы через TUN
▼
egress boundary (singbox_tun + kill-switch uid 945, runbook-003) → провайдер
```

`LLMAdapter` импортирует litellm **не** в процесс — связь только по HTTP.

### Локальная модель (Gemma 4) — native Ollama /api/chat

```
clay backend (AgentRunner → OllamaNativeClient)
│  HTTP POST /api/chat  (stream:false, think:true)
▼
Ollama 127.0.0.1:11434   (gemma4:e2b-it-qat, uid ollama)
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

## 4. Установка (host-native, uid clay)

### 4.1 Пользователь и окружение

```bash
# Пользователь создан (DEPLOY-3.5e.1):
# sudo useradd -r -u 945 -U -m -d /var/lib/clay -s /usr/sbin/nologin clay

# LiteLLM установлен под clay:
sudo -u clay env HOME=/var/lib/clay uv tool install --python 3.13 'litellm[proxy]==1.88.1'
# Бинарь: /var/lib/clay/.local/bin/litellm
# Окружение: /var/lib/clay/.local/share/uv/tools/litellm/

# Конфиги:
/etc/clay/litellm/config.yaml        (clay:clay, 640)
/etc/clay/litellm/litellm.env        (clay:clay, 600) — ключи провайдеров
```

### 4.2 Systemd unit (`/etc/systemd/system/clay-litellm.service`)

```ini
[Unit]
Description=Clay LiteLLM gateway (OpenAI-compat, local-only)
After=network-online.target

[Service]
Type=simple
User=clay
Group=clay
EnvironmentFile=/etc/clay/litellm/litellm.env
ExecStart=/var/lib/clay/.local/bin/litellm --config /etc/clay/litellm/config.yaml --host 127.0.0.1 --port 4000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now clay-litellm
```

### 4.3 Старый user-unit (superseded)

Ранние версии (до 3.5e) использовали systemd --user unit и конфиги
в `~/.config/clay/litellm/`. Эти файлы оставлены как бэкап, не используются.
Актуальный сервис — system-unit под uid 945.

## 5. Гейты здоровья

| Гейт | Команда | Эталон |
| --- | --- | --- |
| unit active | `systemctl is-active clay-litellm` | `active` |
| uid | `ps -o uid -p $(systemctl show -p MainPID clay-litellm --value)` | `945` |
| liveliness (local-only) | `curl -s http://127.0.0.1:4000/health/liveliness` | `200` |
| /v1/models | `curl -s 127.0.0.1:4000/v1/models` | 6 моделей |
| рантайм-egress | аудит трафика на `/health/liveliness` | `0` внешних |

> `/health/liveliness` — **локальный** пинг (без провайдеров). Полный `/health`
> пингует модели → реальный провайдерский egress, поэтому используется только
> в boundary-тестах.

## 6. AI agent cycle

### Флаги

| Переменная | Default | Описание |
| --- | --- | --- |
| `CLAY_SCHEDULER_AI_AGENT_ENABLED` | `false` | Включить цикл. **Opt-in.** |
| `CLAY_SCHEDULER_AI_AGENT_INTERVAL_SECONDS` | `300` | Интервал между стартами цикла (сек). |
| `CLAY_SCHEDULER_AI_AGENT_ROLE_IDS` | `["chief-agent"]` | JSON-список ролей для sequential multi-role цикла. |

### Multi-role sequential cycle (5c.2, 5c.4)

Цикл выполняет роли **последовательно** в одном job типа `AIAgentCycleJob`.
Для каждой роли из `ROLE_IDS`:
1. Резолвится модель по `ops.ai_assignments`.
2. Строится контекст с роль-специфичным prompt.
3. Выполняется вызов LLM (через RoutingModelClient — cloud или local).
4. Результат персистится в `ops.ai_agent_runs` с role_id, model_id, content, error.

Ошибка одной роли **не блокирует** остальные (per-role isolation, 5c.4 live-пруф).

> **Порядок ROLE_IDS:** субагенты → chief последним (например `["market-scanner", "news-sentiment-agent", "forecast-model", "chief-agent"]`), чтобы chief в своём тике видел результаты текущего тика.

**Overlap-protection:** `max_instances=1` + APScheduler Lock — **не ослаблять**.
Если тик длиннее интервала, APScheduler логгирует `maximum number of running
instances reached` и скипает следующий (raw-пруф 5c.4).

**Правило интервала:** `interval ≥ 2× длительность тика`. Замер: тик
4 ролей ≈ **52s** sequential. Latency-ряд: Flash Lite 0.69s / 2.5 Flash
1.23s / Gemma 31B 1.4s / MiniMax 3.78s. На production-интервале 300s
запас ×5.7. При добавлении ролей/провайдеров — пересчитывать.

### Процедура attended smoke (uid clay)

На хосте `sudo` заменён на `pkexec`. Рабочая форма:

```bash
pkexec su -s /bin/bash clay -c '
  cd /home/emma/Projects/clay/backend
  set -a; . ./.env; set +a
  export CLAY_SERVER_HOST=127.0.0.1
  export CLAY_SCHEDULER_ENABLED=true
  export CLAY_SCHEDULER_AI_AGENT_ENABLED=true
  export CLAY_SCHEDULER_AI_AGENT_INTERVAL_SECONDS=60
  export CLAY_SCHEDULER_AI_AGENT_ROLE_IDS=["chief-agent","market-scanner","news-sentiment-agent","forecast-model"]
  exec timeout 180 uv run python -m clay
'
```

**Контракты:**
- JSON-список ROLE_IDS — в одинарных кавычках (shell-safe, Jinja2-безопасно).
- Пароли в `.env` (source внутри su-шелла) — **не в argv**, не светятся в `ps`.
- `.env` канонический: `backend/.env` (см. §14).
- `exec timeout` — автоматический shutdown через N секунд.

**Fallback** (если `pkexec su` блокирован polkit):
```bash
pkexec systemd-run --uid=clay --gid=clay \
  -p WorkingDirectory=/home/emma/Projects/clay/backend \
  -p EnvironmentFile=<tmp-файл 600, флаги+DSN, удалить> \
  -t uv run python -m clay
```

**STOP-условия:** 429 → 0 ретраев кода; нет коннекта к 5433 → STOP (не фабриковать).

Доступ к репо: через группу `clay` (`chgrp -R clay + setgid + ACL`).

### Dual-transport routing (5b-iii)

(Без изменений — описание маршрутизации через RoutingModelClient.)

### DSN и канонический .env

**Канонический путь:** `backend/.env` (source внутри su-шелла).
**Корневой `.env` проекта** (эпоха P0, mtime Jun 7, порт 5432) —
не источник истины. После синхронизации (5c.4) оба файла указывают
на 127.0.0.1:5433 с сильным паролем.

**Инвариант:** DB-факты только через raw psql. Нет коннекта = STOP.
Пароль БД для attended smoke — из `.env`, **не** `clay:clay` (неверен
для 5433, scram-sha-256 аутентификация).

### FOOTGUN A: IngestionSettings не читает .env

`pydantic-settings` в `IngestionSettings` не имеет `env_file` в `model_config`.
`.env` не загружается автоматически. При дефолте — bootstrap смотрит на
live 5432. Для attended smoke и тестов обязателен явный `CLAY_DATABASE_URL`
(source `.env` или export).

## 7. Live-сравнение плеч (5b-iii, 2026-06-11)

| Метрика | Local (gemma4) | Cloud (minimax-m3) | Cloud (gemini-3.1-flash-lite) |
|---------|----------------|-------------------|------------------------------|
| VRAM | idle ~0.6 → пик ~2.6 GB | idle ~0.53 → пик ~0.56 GB | idle ~0.53 → пик ~0.55 GB |
| Latency cold | ~19s | ~3-5s | ~0.7-2s |
| Latency hot | ~6s | ~3-5s | ~0.7-2s |
| Thinking | 1607 / 1239 токенов | NULL | NULL |
| Transport | Native Ollama `/api/chat` | LiteLLM → TUN → TokenRouter | LiteLLM → TUN → Google |

## 8. Rate-limit таблица Gemini

| Модель | RPM | TPM | RPD | Годна для роли? |
|--------|-----|-----|-----|-----------------|
| `gemini-2.5-flash` | 10 | 1M | 20 | ❌ RPD=20 непригодна для permanent |
| `gemini-3.1-flash-lite` | 15 | 250K | 500 | ✅ forecast-model (RPD 500 / 60s interval ≈ большой запас) |
| `Gemma 4 31B` | 15 | **Unlimited** | 1500 | ✅ RPD 1.5K + TPM Unlimited — кандидат №1 для subagents |

**Правило расчёта бюджета роли:**

```
daily_calls = 86400 / interval_seconds × reserve_factor
Достаточно, если RPD > daily_calls
```

- forecast-model (60s): daily_calls = 1440 → RPD 500 достаточно
- chief-agent (300s): daily_calls = 288 → любой RPD > 300
- subagents (300s, 2 роли): daily_calls = 576 → Gemma 4 31B (RPD 1500) — профицит 2.6x

**Политика ретраев:**
- `429 = STOP` — 0 ретраев на уровне кода Clay.
- LiteLLM/httpx ретраит на уровне соединения (connection-error, не 429) —
  наблюдалось ~60 пакетов на 1 boundary при TUN down. Это норма для connection-errors.

## 9. Правило подбора ноды для live-smoke

Нода годна для сессии, если **оба** условия:

1. `curl -s --max-time 5 https://api.binance.com/api/v3/ping` → 200 `{}` (есть доступ к рынку)
2. `curl -s http://127.0.0.1:4000/v1/chat/completions -H ... -d '{"model":"gemini-3.1-flash-lite",...}'
   ` → 200 (Gemini geo не блокирует)

Проверять ПЕРЕД live-smoke. Если Gemini падает с 400 «User location not supported» —
ноду надо сменить (встречается на части нод, включая NL).
Geo-блок не влияет на kill-switch — трафик доходит до API.

## 10. Эксплуатация

```bash
systemctl status clay-litellm
journalctl -u clay-litellm -n 100 --no-pager
systemctl restart clay-litellm
```

## 11. Секреты и провайдерские ключи

- Ключи в git **не хранятся**.
- Актуальный файл ключей: `/etc/clay/litellm/litellm.env` (clay:clay 600).
- Бэкап старой user-инсталляции: `~/.config/clay/litellm/` (emeritus).
- Бэкап podman-эпохи: `~/.config/clay/_backup/old-podman-litellm-*.tar.gz`.

## 12. Podman fallback (emeritus)

Образ сохранён локально, но host-native под uid 945 — основной и единственный
активный путь. Podman-вариант не используется с DEPLOY-3.5e.

## 13. Reference-артефакты в репо

- `deploy/litellm/config.yaml.example` — обезличенный шаблон конфига.
- `deploy/litellm/clay-litellm.service` — шаблон systemd --user unit (emeritus).

## 14. FOOTGUN D/E — Gemma 4 через Gemini API

### FOOTGUN D (закрыт, 5c.2, commit `c82acd5`)

Gemma 4 31B через Gemini API возвращает `content: null`, а
содержимое — в поле `reasoning_content`. Если не обработать,
в `ai_agent_runs.content` попадает пустая строка → FOOTGUN D.

**Фикс:** `LiteLLMModelClient.parse_response` — fallback: если
`content` пустой (нуль/пусто), проверить `reasoning_content` и
использовать его как `content`. Если оба пусты — fail-loud.

**Live-пруф (5c.4):** 3 непустых gemma-4-31b content (357/544/556 chars),
error=NULL.

### FOOTGUN E (candidate, открыт)

При гео/transient-сбое Gemini LiteLLM возвращает `400 Bad Request`
с пустым/неинформативным телом. В `ai_agent_runs.error` попадает
строка без причины (только `LiteLLM gateway call failed... 400:`).

**План фикса:** `LiteLLMModelClient` — захватывать HTTP status +
тело ответа в error-текст для диагностируемости. Отдельный fix-слайс.
