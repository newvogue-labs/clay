# E1 Build Spec — Runtime Foundation And Local Control Plane

Дата: 2026-03-30
Эпик: `E1`
Статус: build-spec
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-002-config-validation-and-rollback-policy.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/runbooks/runbook-001-preflight-degraded-mode.md`

## 1. Цель эпика

Собрать локальный runtime-фундамент системы `CLAY Mission Control`, который:

- запускается на ПК пользователя как `local-first` control plane;
- управляет состояниями системы;
- управляет локальными сервисами;
- хранит и валидирует конфиги;
- агрегирует статусы и health;
- выдает данные в UI;
- обеспечивает предсказуемый переход между `background`, `pre-session`, `active`, `paused`, `review` и `degraded`.

Этот эпик не строит торговую аналитику целиком. Он строит хребет, без которого дальше получится только красивая приборная панель, прикрученная к воздуху.

## 2. Входит в scope

- runtime state model
- local control plane
- process model
- service registry
- scheduler
- config system
- status aggregation
- health monitoring
- event publication для UI и audit-слоя
- UI-facing control API
- preflight orchestration foundation
- degraded mode orchestration foundation

## 3. Не входит в scope

- полноценный market data ingestion
- shortlist logic
- signal ranking
- `Chief Agent` orchestration
- trade result ingestion
- knowledge base ingestion
- replay/backtesting execution
- auto-trading

## 4. Архитектурные допущения

- Платформа пользователя: `CachyOS Linux`
- Формат продукта: `web-first`, локальная панель в браузере
- Runtime-модель: гибридная
- Пользователь: один, `single-user`
- Критичные действия всегда подтверждает пользователь
- Control plane и trading/analysis plane должны быть разделены
- Система должна уметь продолжать работу в предыдущем стабильном состоянии при плохом конфиге или частичной деградации

## 5. Главный результат эпика

После завершения `E1` разработчик должен получить:

- локальный backend-слой, который знает текущее состояние системы;
- единый реестр сервисов и их статусов;
- управляемые переходы между runtime-режимами;
- валидируемые конфиги;
- API, через которое UI может:
  - читать статус;
  - запускать и останавливать сервисы;
  - переключать режимы;
  - получать предупреждения;
  - видеть причину деградации;
  - запускать preflight.

## 6. Логические компоненты E1

### 6.1 Frontend Shell

Минимальный UI-клиент, который:

- показывает текущее состояние runtime;
- показывает состояние сервисов;
- отправляет команды управления;
- получает поток событий статуса.

На этапе `E1` UI может быть техническим и неокончательным по дизайну. Главное — функциональность и прозрачность.

### 6.2 Control API

Центральный backend для панели.

Ответственности:

- отдавать runtime state;
- отдавать service registry;
- принимать команды на управление;
- публиковать status/events;
- запускать preflight;
- применять разрешённые конфиг-изменения;
- не выполнять heavy analysis.

### 6.3 Runtime Manager

Главный управляющий компонент runtime.

Ответственности:

- хранить canonical runtime state;
- валидировать переходы между состояниями;
- запускать state transitions;
- блокировать недопустимые переходы;
- инициировать degraded mode;
- координировать возврат в normal mode.

### 6.4 Service Registry

Реестр всех локальных модулей.

Для каждого сервиса хранит:

- `service_id`
- `service_type`
- `class`
- `status`
- `health_state`
- `startup_policy`
- `criticality`
- `last_heartbeat_at`
- `last_error`
- `depends_on`

### 6.5 Health Monitor

Отвечает за health-check и freshness-check.

Проверяет:

- доступность сервиса;
- heartbeat;
- время последнего успешного цикла;
- freshness критичных данных;
- критичные dependency failures.

### 6.6 Scheduler

Управляет переходом между режимами по расписанию и подготавливает систему к рабочему окну `09:00–22:00 MSK`.

### 6.7 Config Manager

Отвечает за:

- загрузку конфигов;
- валидацию;
- применение;
- откат к последней валидной версии;
- публикацию события о конфиг-изменении.

### 6.8 Event Publisher

Публикует runtime-события в UI и в audit-слой.

## 7. Разделение control plane и managed services

### 7.1 Control plane

В control plane входят:

- `frontend-shell`
- `control-api`
- `runtime-manager`
- `service-registry`
- `config-manager`
- `health-monitor`
- `scheduler`
- `event-publisher`

### 7.2 Managed services

Это отдельные рабочие модули, которыми control plane управляет, но которые не должны сливаться с ним в один процесс.

Примеры managed services:

- `market-data-service`
- `history-store-service`
- `news-connector-service`
- `sentiment-connector-service`
- `forecast-inference-service`
- `chief-agent-service`
- `briefing-worker`
- `replay-worker`
- `knowledge-ingest-worker`

## 8. Runtime state model

### 8.1 Canonical runtime states

Система имеет ровно шесть пользовательских runtime-состояний:

- `background_monitoring`
- `pre_session`
- `active_session`
- `paused`
- `review`
- `degraded`

### 8.2 Внутренние технические sub-states

Дополнительно runtime manager может использовать внутренние переходные sub-states:

- `booting`
- `reconfiguring`
- `recovering`
- `shutting_down`

Эти sub-states не считаются пользовательскими режимами, но должны отражаться в diagnostics.

### 8.3 Назначение состояний

`background_monitoring`
- работают фоновые сервисы;
- собирается контекст;
- heavy analysis не активирован на полном режиме.

`pre_session`
- активирован preflight;
- собирается briefing;
- пользователь подтверждает shortlist, модели и стратегию.

`active_session`
- работает боевой контур анализа;
- UI показывает ranked signals;
- разрешены предложения по смене пары и стратегии.

`paused`
- боевая аналитика ослаблена или приостановлена;
- контекст сохраняется;
- фоновый сбор не должен теряться.

`review`
- активная сессия завершена;
- система подтягивает итоги, summary и review.

`degraded`
- часть возможностей ограничена;
- система обязана явно показывать это в UI;
- восстановление возможно только после прохождения recovery-проверок.

### 8.4 Разрешённые переходы

Разрешены только такие переходы:

- `background_monitoring -> pre_session`
- `pre_session -> active_session`
- `pre_session -> background_monitoring`
- `active_session -> paused`
- `paused -> active_session`
- `active_session -> review`
- `review -> background_monitoring`
- `background_monitoring -> degraded`
- `pre_session -> degraded`
- `active_session -> degraded`
- `paused -> degraded`
- `review -> degraded`
- `degraded -> background_monitoring`
- `degraded -> pre_session`

Запрещены прямые переходы:

- `background_monitoring -> active_session`
- `active_session -> background_monitoring`
- `paused -> review`
- `review -> active_session`

Причина: каждое критичное движение должно проходить через управляемые шаги, а не через архитектурный `jmp 0xdeadbeef`.

## 9. Process model

### 9.1 Always-on services

Эти сервисы должны жить всё время, пока система запущена:

- `control-api`
- `runtime-manager`
- `service-registry`
- `config-manager`
- `health-monitor`
- `scheduler`
- `event-publisher`
- `audit-writer`

### 9.2 Background-critical managed services

Эти сервисы должны быть доступны во время рабочего окна или фонового мониторинга:

- `market-data-service`
- `history-store-service`
- `connector-manager`

### 9.3 On-demand services

Эти сервисы разрешено запускать по состоянию системы:

- `briefing-worker`
- `forecast-inference-service`
- `chief-agent-service`
- `replay-worker`
- `knowledge-ingest-worker`
- `model-import-worker`

## 10. Service lifecycle semantics

Каждый сервис должен иметь единый lifecycle:

- `stopped`
- `starting`
- `healthy`
- `degraded`
- `stale`
- `error`
- `stopping`

### 10.1 Операции управления сервисом

Control plane обязан поддерживать:

- `start`
- `stop`
- `restart`
- `health_check`
- `mark_degraded`
- `recover`

### 10.2 Правила операций

- `start` разрешён только если зависимости в допустимом состоянии
- `stop` запрещён для critical service во время `active_session`, кроме аварийного режима
- `restart` обязан записывать событие в audit
- `health_check` не должен менять состояние без явного результата
- `recover` разрешён только после успешной recheck-валидации

## 11. Control API surface

На уровне build-spec фиксируются resource groups.

### 11.1 Runtime

- `GET /runtime/state`
- `POST /runtime/transition`
- `GET /runtime/allowed-transitions`

### 11.2 Services

- `GET /services`
- `GET /services/{service_id}`
- `POST /services/{service_id}/start`
- `POST /services/{service_id}/stop`
- `POST /services/{service_id}/restart`
- `POST /services/{service_id}/health-check`

### 11.3 Health

- `GET /health/summary`
- `GET /health/dependencies`
- `GET /health/freshness`

### 11.4 Config

- `GET /configs`
- `GET /configs/{config_scope}`
- `POST /configs/{config_scope}/validate`
- `POST /configs/{config_scope}/apply`
- `POST /configs/{config_scope}/rollback`

### 11.5 Preflight

- `POST /preflight/run`
- `GET /preflight/latest`

### 11.6 Events

- `GET /events/stream` (`SSE`)
- `GET /alerts`

### 11.7 Models/Strategies placeholders

Эти группы могут быть реализованы как stub в `E1`, но их контракты должны быть предусмотрены:

- `GET /models/active`
- `GET /strategies/active`

## 12. Config system

### 12.1 Storage model

Конфиги должны жить как versionable structured files.

Выбор для `v1`:

- формат: `TOML`
- runtime validation: строгая schema validation
- применение: только через validated load path

### 12.2 Secrets policy

Секреты не должны храниться в обычных versioned config files.

Разрешённые источники секретов:

- `.env`
- OS environment
- local secret file вне Git-synced planning-директории

### 12.3 Config scopes

Обязательные конфиг-секции:

- `app.toml`
- `runtime.toml`
- `connectors.toml`
- `models.toml`
- `strategies.toml`
- `schedules.toml`
- `risk.toml`

### 12.4 Config behavior rules

- плохой конфиг не должен ломать рабочее состояние;
- система обязана сохранить последнюю валидную конфигурацию;
- UI обязан показать причину отказа применения;
- каждое успешное применение должно попадать в audit.

### 12.5 Что можно менять через UI

Через UI разрешено:

- active strategy profile
- active model assignment
- shortlist rules в пределах разрешённых диапазонов
- session schedule
- confidence thresholds
- risk thresholds из user-safe диапазона

Через UI не разрешено:

- пути к локальным секретам;
- внутренние service ids;
- storage backend type;
- system paths;
- low-level transport settings.

## 13. Linux runtime layout

Для локальной системы на Linux использовать XDG-friendly layout:

- config: `~/.config/clay-mission-control/`
- data: `~/.local/share/clay-mission-control/`
- state/logs: `~/.local/state/clay-mission-control/`
- cache: `~/.cache/clay-mission-control/`

Planning-документы и архитектурные артефакты продолжают жить отдельно в Obsidian/Git.

## 14. UI interactions required in E1

Даже в техническом виде UI должен уметь:

- показать runtime state;
- показать список сервисов;
- показать статусы `healthy / degraded / stale / stopped / error`;
- запустить preflight;
- инициировать разрешённый state transition;
- перезапустить не-critical service;
- показать последнее предупреждение;
- показать причину degraded mode;
- показать timestamp последнего успешного health-check.

## 15. Failure modes, которые E1 обязан учитывать

- invalid config
- critical service crash
- stale service heartbeat
- scheduler drift
- failed runtime transition
- partial dependency outage
- UI command timeout
- inconsistent service registry state

Для каждого такого класса сбоев система обязана:

- записать событие;
- показать alert;
- сохранить текущий безопасный режим;
- не скрывать деградацию.

## 16. Acceptance criteria

Эпик `E1` считается готовым, если выполняются все условия:

1. Система поднимает canonical runtime state и умеет его читать через API.
2. Все разрешённые переходы между состояниями валидируются централизованно.
3. Запрещённый переход отклоняется с ясной причиной и audit-event.
4. Service registry показывает состояние каждого зарегистрированного сервиса.
5. Control API умеет делать `start/stop/restart/health-check` для управляемых сервисов.
6. Invalid config не ломает текущую рабочую конфигурацию.
7. Каждое успешное конфиг-изменение фиксируется в audit.
8. UI получает поток событий о state changes и service health.
   Для `v1` этот поток реализуется через `SSE`, а не через обязательный browser-facing `WebSocket`.
9. Preflight можно запустить централизованно через control API.
10. Degraded mode может быть инициирован runtime manager и явно отражается в UI.
11. Critical service нельзя тихо остановить в `active_session`.
12. Локальные runtime paths соответствуют XDG layout.

## 17. Проверки и валидация

Обязательные проверки для `E1`:

- state transition contract tests
- config validation tests
- service registry state tests
- degraded mode entry tests
- health monitor stale detection tests
- UI-to-control API smoke test

## 18. Основные риски

- чрезмерно монолитный control API
- смешивание control plane и data plane
- “магические” переходы состояний вне runtime manager
- silent failures без audit trail
- слишком широкие UI-права на low-level конфиги

## 19. Out-of-scope улучшения на потом

- полноценная auth layer
- remote access
- distributed worker runtime
- automatic cloud fallback routing
- dynamic plugin loading

## 20. Артефакты, которые должны следовать сразу после E1 build-spec

- API contract spec for `control-api`
- config schema spec
- state transition test matrix
- service registry data model
- implementation plan for `E1`
