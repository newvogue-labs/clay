---
tags:
  - ops
  - infra
---

# Runbook-003 — Kill-switch и egress (DEPLOY-3.5e)

Дата: 2026-06-12 (переписан под модель 3.5e; версии 3.5b–3.5d superseded)
Статус: active
Связанный эпик: `E5` · `DEPLOY-5`
Связано: ADR-009, runbook-004 (LiteLLM gateway)

## Назначение

Гарантировать, что весь LLM-egress (LiteLLM, uid 945) идёт **только** через `singbox_tun`,
и при падении туннеля система **fail-closed** (0 утечек). Оператор (uid 1000) не фильтруется
никогда — интернет Emma свободен вне зависимости от состояния TUN.

## Архитектура (3.5e)

- **Субъект фильтрации:** системный пользователь `clay` (uid 945).
  Правила nft НЕ упоминают uid 1000 и любые другие uid.
- **Разрешено для uid 945:**
  - `lo` (loopback — связь с локальными сервисами: Ollama, БД 5433, LiteLLM health)
  - `singbox_tun` (единственный разрешённый egress-интерфейс)
  - LAN/private сети (`@allow4`/`@allow6` — Podman, локальные сети)
- **Всё остальное:** `counter reject` — catch-all на любом интерфейсе.
  Clay не уходит ни через enp3s0, ни через amn0 (Amnezia), ни через любой другой tun.
- **Always-on:** unit `clay-killswitch.service` enabled, грузится с boot.
  Latch и udev-arm УДАЛЕНЫ (3.5d) — они были нужны для защиты uid 1000,
  которая больше не фильтруется.
- **Fail-closed по построению:** при TUN down у uid 945 нет разрешённого egress-пути
  (единственный accept для внешнего трафика — `oifname "singbox_tun"`).
- **Disarm (редкий, ручной):** `systemctl stop clay-killswitch` грузит clean.nft
  и удаляет таблицу. Нужен только для диагностики или временного разрешения clay-egress
  без TUN.

## Факты (PROVEN 3.5e)

- Anchor: `meta skuid 945` (uid clay).
- `table inet clay_killswitch`; allow4/allow6 — как в DEPLOY-3.5b (без изменений).
- Модель арма (DEPLOY-3.5e): **always-on** — unit `WantedBy=multi-user.target`,
  грузится при старте системы. `ExecStart=nft -f /etc/clay-killswitch.nft`,
  `ExecStop=nft -f /etc/clay-killswitch-clean.nft`.
- Файлы НЕ в git: `/etc/clay-killswitch.nft`, `/etc/clay-killswitch-clean.nft`.
- `udev/rules.d/99-clay-killswitch.rules` удалён (суперсед 3.5d).
- Egress-путь clay: `LiteLLM (uid 945)` → `singbox_tun` → VPS → провайдер.
- **Verified (DEPLOY-3.5e.2, 2026-06-12):**
  - T1: emma curl ipify при armed + TUN up → ✅ 200, counter 0
  - T2: `sudo -u clay curl ipify` при TUN down → ❌ URLError, counter↑
  - T3: clay egress через amn0 при TUN down → ❌ URLError (catch-all reject)
  - T6: LiteLLM cloud boundary при TUN down → ❌ APIConnectionError, counter 0→66
  - T8: reboot → интернет emma ✅ сразу, clay-killswitch active, LiteLLM uid 945

## Процедура проверки egress

1. Проверить, что таблица armed: `systemctl is-active clay-killswitch` → `active`.
2. Проверить reject-counter: `nft list table inet clay_killswitch | grep 'skuid 945 counter'`
   — при штатной работе 0 или минимальный (стартовые DNS и т.п.).
3. Проверить исходящий IP clay (при TUN up):
   `sudo -u clay curl -m5 https://api.ipify.org` — ≠ US, ≠ домашний РФ.
4. Проверить egress LiteLLM: boundary-пробник через шлюз (runbook-004).

## Аварийное поведение (TUN down)

- Kill-switch режет egress uid 945 → LiteLLM не может соединиться с провайдерами.
- Clay ловит `APIConnectionError` → роль degraded, последний вывод помечен stale.
- Оператор поднимает TUN → следующий цикл агента проходит штатно.
- Оператор (uid 1000) не затронут — интернет, Amnezia, браузер работают.
  Никаких ритуалов/лач/udev.

## Восстановление

1. Оператор поднимает TUN (через Amnezia/sing-box).
2. Проверить egress (процедура выше).
3. Дождаться следующего `ai-agent-cycle` или триггернуть вручную.
4. Снять degraded после успешного прогона.

## Верификация data-exfil (mitmproxy)

(Без изменений из версии 3.5b — применяется к трафику uid 945 через TUN)

## История

- **DEPLOY-3.5b (2026-06-07):** Первая реализация — nft `skuid 1000`, `oifname "enp3s0"`.
  Latch + udev-arm. Резало весь uid 1000 при TUN down.
- **DEPLOY-3.5c (2026-06-08):** Исправление persistence (clean.nft, stable boot).
- **DEPLOY-3.5d (2026-06-11):** udev-arm + boot-clean. Latch оставлен.
- **DEPLOY-3.5e (2026-06-12):** Миграция якоря на uid 945 (пользователь `clay`).
  Always-on, никакой фильтрации uid 1000, latch/udev удалены.
  Текущая и единственная активная версия.

## Остаточный риск

- systemd-resolved DNS-метаданные на enp3s0 в момент падения TUN —
  uid 945 ходит на DNS через lo (127.0.0.53), что разрешено правилом `oifname "lo"`.
  Опциональное ужесточение: резать DNS для uid 945 на любом интерфейсе, кроме `singbox_tun`.
- Container `clay_timescaledb` не имеет restart-policy — не переживает ребут хоста.
  После ребута: `podman start clay_timescaledb`. (Задокументировано в backlog.)
