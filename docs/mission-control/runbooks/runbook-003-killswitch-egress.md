# Runbook-003 — Kill-switch и egress (DEPLOY-5 AI-слой)

Дата: 2026-06-10
Статус: active
Связанный эпик: `E5` · `DEPLOY-5`
Связано: ADR-009, runbook-004 (LiteLLM gateway)

## Назначение

Гарантировать, что весь LLM-egress (включая контейнер шлюза LiteLLM) идёт через TUN и never-US, и при падении туннеля система **fail-closed** (0 утечек). Описывает проверку, аварийное поведение и восстановление.

## Когда применять

- Перед «boundary live» (первый реальный внешний вызов модели).
- При падении/переподнятии TUN.
- При плановой проверке egress (периодически).
- При инциденте «подозрение на утечку».

## Роли

- **Оператор (Emma):** единственный, кто трогает туннель (v2rayN GUI TUN + reboot). Поднимает TUN до прогона агентов.
- **Clay/агент:** НЕ перезапускает v2rayN/sing-box (FOOTGUN C); только наблюдает и переходит в degraded.

## Факты (PROVEN 3.5b/3.5c)

- Anchor kill-switch: `meta skuid 1000` (uid emma).
- `table inet clay_killswitch`; allow4 `{192.168.0.0/24,10.88.0.0/16,10.89.0.0/24,172.18.0.0/30,224.0.0.0/4,255.255.255.255}`, allow6 `{fe80::/10,ff00::/8}`.
- Persistence: `/etc/systemd/system/clay-killswitch.service` (DefaultDependencies=no, After=nftables.service, Before=network-pre.target).
- Egress-путь: app → `singbox_tun` (172.18.0.1/30) → socks5 127.0.0.1:10808 → xray(uid1000) → TUN → sing-box(uid0) → enp3s0 → VPS. Uplink `cf.090227.xyz:443` (Cloudflare CDN).
- Leak confirmed: TUN down → ipify `176.195.172.124` (домашний ISP РФ).

## Процедура проверки egress

1. Поднять TUN (оператор), дождаться готовности.
2. Проверить исходящий IP/страну (never-US, не домашний РФ-IP).
3. Запустить шлюз (runbook-004), проверить, что его процесс/контейнер ходит только через TUN.
4. Smoke-вызов модели; зафиксировать исходящий IP в egress-аудите.

## Аварийное поведение (TUN down)

- Kill-switch режет egress uid 1000 (host-native шлюз LiteLLM работает как emma → попадает напрямую; podman-fallback — проверить маскарад uid на enp3s0) → внешние вызовы **не уходят** мимо TUN.
- Clay ловит ошибку adapter → роль degraded, последний вывод помечен stale.
- Offline-watcher пишет в локальный файл (работает как emma).
- Оператор поднимает TUN → агент повторяет цикл.

## Восстановление

1. Оператор поднимает TUN.
2. Проверить egress (шаги выше).
3. Дождаться следующего `ai-agent-cycle` или триггернуть вручную.
4. Снять degraded после успешного прогона.

## Верификация data-exfil (mitmproxy)

- Перед «boundary live» прогнать исходящий трафик шлюза через **mitmproxy** (локально) и убедиться, что в провайдеров уходит **только минимизированный/обезличенный контекст** (нет ключей, балансов, PII, сырых ордеров) — ADR-009.
- **Wireshark/nmap** — проверить, что egress идёт строго через TUN-путь (enp3s0 → sing-box → VPS), мимо TUN ничего нет.
- Зафиксировать исходящий IP/страну (never-US) в egress-аудите.

> Альтернативные туннели на хосте (Mullvad, AmneziaVPN, Clash Verge Rev) — **вне scope DEPLOY-5**. Egress остаётся на проверенном пути v2rayN/sing-box, управляемом только оператором (FOOTGUN C).

## Остаточный риск

- systemd-resolved DNS-метаданные на enp3s0 в момент падения TUN — отслеживать, при необходимости закрыть отдельным правилом.
