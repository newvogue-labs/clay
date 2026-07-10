---
tags:
  - ops
  - infra
---

# Runbook-001 — Preflight And Degraded Mode

Дата: 2026-03-30
Статус: active planning runbook
Связанный эпик: `E1`

## 1. Назначение

Этот runbook описывает:

- как система должна проходить `preflight` перед входом в `active_session`;
- как система должна входить в `degraded mode`;
- как пользователь и runtime должны действовать при ограниченной работоспособности.

## 2. Когда применяется

### Preflight

Запускается:

- перед каждой активной торговой сессией;
- после ручной смены модели или стратегии перед входом в сессию;
- после recovery из `degraded`, если пользователь хочет перейти в `active_session`.

### Degraded mode

Запускается, если сработало хотя бы одно условие:

- главная облачная модель недоступна;
- критичный внешний `API` недоступен;
- market data устарели;
- critical service упал;
- active config невалиден;
- runtime manager зафиксировал невозможность безопасно продолжать обычный режим.

## 3. Роли

### Runtime manager

Отвечает за:

- запуск preflight;
- решение о входе в degraded mode;
- блокировку недопустимого перехода;
- публикацию событий в UI и audit.

### Control API

Отвечает за:

- запуск команд;
- выдачу результатов checks;
- показ причин блокировки.

### Пользователь

Отвечает за:

- подтверждение перехода в `active_session`;
- подтверждение возврата из `Defensive` в normal mode;
- принятие решения продолжать ли сессию после серьёзной деградации.

## 4. Preflight checklist

Preflight считается успешным только если все обязательные проверки зелёные.

### 4.1 Runtime checks

- `runtime-manager` доступен
- `control-api` доступен
- `service-registry` доступен
- `health-monitor` доступен
- `scheduler` доступен

### 4.2 Service checks

- все required `always-on services` имеют статус `healthy`
- все required `background-critical services` имеют допустимый статус
- ни один critical service не находится в `error`

### 4.3 Data checks

- market data не stale
- connector state не stale
- last successful ingest укладывается в допустимое окно свежести

### 4.4 Session checks

- shortlist подтверждён
- активная стратегия назначена
- активная модель назначена
- risk thresholds загружены
- user-safe config применён

### 4.5 Audit checks

- audit writer доступен
- события preflight могут быть записаны

## 5. Результаты preflight

### PASS

Все обязательные проверки успешны.

Система может предложить переход:

- `background_monitoring -> pre_session`
- `pre_session -> active_session`

### SOFT FAIL

Есть ограничение, но система может работать в ослабленном режиме.

Примеры:

- secondary external API недоступен
- одна из non-critical аналитических служб не поднята
- часть optional context недоступна

Действие:

- пользователь получает предупреждение;
- система остаётся в `pre_session`;
- разрешён переход в `active_session` только если это не нарушает strict safety rules.

### HARD FAIL

Есть условие, которое делает вход в `active_session` небезопасным.

Примеры:

- market data stale
- главная модель недоступна и fallback не готов
- critical service crashed
- config invalid
- risk config не загружен

Действие:

- переход в `active_session` блокируется;
- система остаётся в `pre_session` или уходит в `degraded`;
- пользователю показывается причина и список шагов восстановления.

## 6. Автоматический вход в degraded mode

Система обязана автоматически войти в `degraded` при:

- потере chief-model access;
- потере market data freshness;
- падении critical runtime service;
- невалидном применённом конфиге;
- невозможности выполнить обязательный safety check.

## 7. Поведение системы в degraded mode

### 7.1 Что обязано произойти автоматически

- runtime state меняется на `degraded`
- в UI показывается явный degraded banner
- в audit пишется событие с причиной и timestamp
- confidence будущих сигналов понижается
- high-risk signals могут блокироваться
- система включает fallback, если он доступен

### 7.2 Что пользователь должен видеть

- причину деградации
- какие компоненты затронуты
- какие функции ограничены
- доступен ли локальный fallback
- можно ли продолжать мониторинг
- можно ли продолжать активную сессию

### 7.3 Что запрещено в degraded mode

- скрывать ухудшение качества сигналов
- показывать full-confidence signal без пометки о деградации
- тихо возвращаться в normal mode без повторной проверки

## 8. Классы degraded incidents и реакция

### A. Cloud model outage

Реакция:

- включить local fallback, если доступен;
- понизить confidence;
- запретить делать вид, что reasoning равен full mode.

### B. External API outage

Реакция:

- определить, это critical или optional source;
- если critical, ограничить сигналы;
- если optional, остаться в degraded с soft limitations.

### C. Stale market data

Реакция:

- блокировать новые рабочие сигналы;
- разрешить только мониторинг;
- запретить нормальный trading mode до восстановления freshness.

### D. Critical service crash

Реакция:

- записать incident event;
- попытаться controlled restart;
- если restart неуспешен, остаться в degraded;
- при необходимости завершить active session.

### E. Invalid config

Реакция:

- откатиться на последнюю валидную конфигурацию;
- пометить incident;
- заблокировать unsafe transition.

## 9. Recovery procedure

Возврат из `degraded` разрешён только если:

- причина деградации устранена;
- critical services снова `healthy`;
- stale data восстановлены;
- конфиг валиден;
- preflight повторно пройден.

После этого разрешён только один из переходов:

- `degraded -> background_monitoring`
- `degraded -> pre_session`

Прямой переход `degraded -> active_session` запрещён.

## 10. Когда нужно рекомендовать остановить сессию

Система должна рекомендовать остановить активную сессию, если:

- degraded mode длится слишком долго;
- fallback даёт слишком слабую аналитическую ценность;
- market data нестабильны;
- есть серия нескольких critical incidents за короткий интервал;
- risk engine указывает, что продолжение небезопасно.

## 11. Что обязано попасть в audit

Для preflight:

- кто запустил;
- когда запустил;
- список check results;
- итоговый статус;
- причина fail, если fail.

Для degraded mode:

- точная причина входа;
- затронутые сервисы;
- что было ограничено;
- включился ли fallback;
- когда начался recovery;
- чем закончился recovery.

## 12. Acceptance criteria для runbook-логики

Логика считается реализованной корректно, если:

1. Preflight выдаёт структурированный результат, а не просто “ok/not ok”.
2. Hard fail действительно блокирует вход в `active_session`.
3. Degraded mode всегда виден пользователю.
4. Recovery невозможен без повторной проверки.
5. Invalid config приводит к rollback, а не к саморазрушению.
6. Stale market data блокируют обычный боевой сигнал.
