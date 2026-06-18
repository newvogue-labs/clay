# ADR-016: Config write-path под автономный reconcile

- **Status:** Accepted (2026-06-18)
- **Driver:** S3d-1
- **Replaces:** sudo -u clay cp dance (S3c-2)

## Context

Reconcile-петля живёт в backend, который запускается вручную под emma (uid 1000).
Перенос backend в systemd-под-clay невозможен: clay сетево заперт (singbox_tun,
fail-closed) → ingestion-egress сломается. Canonical `/etc/clay/litellm/config.yaml`
принадлежит clay:clay; backup+write через `sudo -u clay cp` требуют пароль под emma →
для автономной петли нежизнеспособно. Кросс-юзерный cp-танец уже породил 2 бага на
rehearsal (PermissionError backup; temp 0600 нечитаем для cp).

## Decision

1. Backend остаётся под emma.
2. Canonical config → mode **0644**. Секретов в нём нет (только `key_ref` — имена
   env-vars; литералы ключей в `litellm.env`, 600). emma читает нативно для parity
   и backup.
3. Запись/install — через узкий root-helper `/usr/local/sbin/clay-config-install`:
   назначение захардкожено, validate → timestamped backup → атомарный install
   (clay:clay 0644), без restart. sudoers: emma NOPASSWD только на этот helper.
   Restart остаётся отдельным NOPASSWD на `systemctl restart clay-litellm.service`.

## Rejected

- **NOPASSWD на `sudo -u clay cp`**: произвольная запись-как-clay → может затереть
  `litellm.env` (живые ключи). Дыра-footgun.
- **Backend → systemd-под-clay**: egress-jail clay ломает ingestion.

## Consequences

- Убран кросс-юзерный cp-танец (источник 2 rehearsal-багов); запись = одна
  аудируемая привилегированная транзакция.
- Canonical world-readable, но без секретов.
- Rehearsal live: Applied=True, Restart OK, Health OK, Equivalent=True.
