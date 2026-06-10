# Runbook-004 — LiteLLM gateway (локальный шлюз моделей)

Дата: 2026-06-10
Статус: active
Связанный эпик: `E5` · `DEPLOY-5`
Связано: ADR-009, ADR-010, runbook-003 (kill-switch/egress)

## Назначение

Единая точка LLM-egress: запуск, конфигурация, проверка и восстановление локального шлюза LiteLLM, через который Clay делает все внешние вызовы моделей. Вендор-ключи живут в шлюзе, не в Clay.

## Режим установки (решение)

**Primary — host-native** (рекомендуется):
- LiteLLM в изолированном venv (`uv` или `pipx`), не трогая системный Python.
- Запуск как `systemd --user` сервис от emma → процесс имеет **uid 1000** → **напрямую попадает под kill-switch** (`meta skuid 1000`).
- Плюсы: нет podman-сетевого слоя (pasta/slirp4netns), чище биндинг `127.0.0.1:4000`, стабильнее подключение, ровнее покрытие kill-switch.
- Инструкция: https://github.com/BerriAI/litellm/

**Fallback — podman** (задокументирован, не основной):
- Образ `ghcr.io/berriai/litellm:main-stable`; запуск через `podman` / `podman-compose 1.6.0` (Docker не установлен).
- При rootless-podman egress идёт через user-mode сетевой стек (pasta/slirp4netns) — лишний NAT-хоп; ОБЯЗАТЕЛЬНО проверить, что маскарад на enp3s0 сохраняет uid 1000 (покрытие kill-switch).
- Рассматривать, если нужен reproducible-образ / изоляция важнее стабильности.

> Решение revisable. См. ADR-009 (egress gateway). Привязка в обоих режимах — только `127.0.0.1:4000`.

## Когда применять

- Первичный запуск шлюза.
- После reboot (для host-native — `systemctl --user` autostart; для podman — перезапуск контейнера).
- При ошибках 429/5xx от провайдеров.
- При ротации ключей провайдеров.

## Роли

- **Оператор (Emma):** управляет ключами провайдеров и жизненным циклом шлюза; поднимает TUN до старта шлюза.
- **Clay/агент:** знает только `CLAY_LLM_BASE_URL`; не хранит вендор-ключи; не перезапускает туннель.

## Привязка и egress

- Bind: `127.0.0.1:4000` (OpenAI-совместимый API).
- Egress шлюза — через TUN; покрыт kill-switch (runbook-003), fail-closed при TUN down.
- host-native: процесс uid 1000 → под правилом `meta skuid 1000` автоматически.

## Конфиг (config.yaml — в шлюзе)

- model_list: логические имена → провайдеры:
  - chief-agent → Gemini free-tier (ADR-010)
  - subagents → relay (FreeQwenApi) / локально
  - forecast → локальная quant-модель (ADR-011), gemini опц. fallback
  - last resort → Ollama (localhost:11434)
- Ключи провайдеров — в env шлюза/секрет-файле, НЕ в `.env` Clay.
- fallbacks: цепочка free-tier → relay → local.

## Запуск (эскиз — детали на слайсе 5a)

1. Оператор поднимает TUN.
2. **host-native:** `uv`/`pipx` venv → `litellm --config config.yaml --port 4000 --host 127.0.0.1`; оформить `systemd --user` unit. **podman (fallback):** запустить контейнер, смонтировать config.yaml + секреты, bind 127.0.0.1:4000.
3. Health: `curl 127.0.0.1:4000/health` (локально).
4. Проверить egress через TUN (runbook-003).
5. Smoke: один вызов логической модели.

## Проверка

- `/health` отвечает.
- Исходящий IP/страна корректны (never-US).
- Логические имена резолвятся в провайдеров.

## Восстановление

- 429/5xx: backoff на стороне Clay + fallback-chain; при устойчивой ошибке провайдера — переключить логическое имя на fallback в config.yaml.
- Шлюз упал: host-native — `systemctl --user restart`; podman — перезапуск контейнера (оператор); повторить проверку.
- TUN down: шлюз fail-closed → Clay degraded → оператор поднимает TUN.

## Безопасность

- Ключи только в шлюзе.
- Контекст минимизирован/обезличен до отправ��и (data-exfil политика, ADR-009).
- geo-allowlist (never-US) + egress-аудит.
