# ADR-001 — Runtime State Model And Control Plane Boundary

Дата: 2026-03-30
Статус: accepted
Связанный эпик: `E1`

## Контекст

`CLAY Mission Control` строится как локальная торгово-аналитическая панель, которая должна:

- жить на одном ПК;
- управлять несколькими сервисами;
- выдерживать деградацию облачных моделей и `API`;
- переводиться между `background`, `pre-session`, `active`, `paused`, `review` и `degraded`;
- оставаться объяснимой и предсказуемой.

Если сделать систему как один большой процесс “UI + orchestration + data + analysis”, то:

- runtime-ошибки труднее локализовать;
- degraded mode превращается в импровизацию;
- опаснее управлять критичными сервисами;
- сложнее валидировать переходы состояния;
- тяжелее вести audit.

## Решение

Принять архитектурное решение:

1. Ввести отдельный `local control plane`.
2. Отделить `control plane` от `managed services`.
3. Ввести явную `runtime state machine` с ограниченным набором разрешённых состояний.
4. Разделить сервисы на:
   - `always-on`
   - `background-critical`
   - `on-demand`
5. Все переходы состояний и критичные runtime-операции проводить только через `runtime-manager`.

## Canonical runtime states

- `background_monitoring`
- `pre_session`
- `active_session`
- `paused`
- `review`
- `degraded`

## Control plane components

- `control-api`
- `runtime-manager`
- `service-registry`
- `config-manager`
- `health-monitor`
- `scheduler`
- `event-publisher`

## Managed services

Примеры:

- `market-data-service`
- `connector-manager`
- `forecast-inference-service`
- `chief-agent-service`
- `briefing-worker`
- `replay-worker`

## Обоснование

Этот вариант выбран потому что он:

- упрощает observability;
- позволяет fail sanely;
- не даёт критичным переходам происходить “где-то сбоку”;
- поддерживает degraded mode как first-class behavior;
- уменьшает риск случайной связки UI и heavy analytics;
- лучше подходит под дальнейшее тестирование и build-by-epic.

## Рассмотренные альтернативы

### A. Один большой локальный monolith process

Отклонено.

Причины:

- слишком сильная связность;
- сложнее recovery;
- сложнее health-check;
- control logic и heavy analysis начинают душить друг друга.

### B. Всё держать always-on

Отклонено.

Причины:

- лишняя нагрузка на локальную машину;
- не соответствует реальному рабочему циклу пользователя;
- делает деградацию и pause-режимы менее управляемыми.

### C. Полностью event-driven distributed runtime

Отклонено для `v1`.

Причины:

- архитектурный оверкилл;
- лишняя сложность для single-PC локального сценария.

## Последствия

### Положительные

- лучше управляемость;
- понятная state machine;
- легче тестировать переходы;
- легче показывать пользователю, что реально происходит;
- легче строить runbooks и acceptance criteria.

### Отрицательные

- больше компонентов;
- нужен дисциплинированный service registry;
- нужен явный runtime-manager как отдельная ответственность.

## Что теперь обязательно

- все runtime transitions должны идти через один компонент;
- UI не должен напрямую командовать managed service, минуя control API;
- degraded mode не должен быть “визуальной меткой без логики”;
- invalid config не должен ломать систему.

## Что это не запрещает

- в будущем добавлять новые managed services;
- в будущем расширять список внутренних technical sub-states;
- позже добавить remote access или desktop packaging.

Но всё это должно сохранять базовую границу между `control plane` и `managed services`.
