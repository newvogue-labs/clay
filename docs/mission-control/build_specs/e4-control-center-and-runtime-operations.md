# E4 Build Spec — Control Center And Runtime Operations

Дата: 2026-04-15
Эпик: `E4`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-002-config-validation-and-rollback-policy.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/session-summary-2026-04-01.md`
- UI baseline: `/home/emma/Documents/Obsidian/CachyOS/Trading/clay-mission-control_ui_v15.zip`

## 1. Цель эпика

Собрать `Control Center` как операторский пульт `CLAY Mission Control`, который:

- показывает реальное состояние runtime и managed services;
- даёт понятный обзор деградации, ошибок, stale-состояний и ограничений;
- позволяет выполнять безопасные operator actions через control plane;
- показывает активную конфигурацию, модельные назначения и session/runtime context;
- остаётся системным экраном управления, а не дублем `Trading Workspace`.

`E4` строит не “ещё один dashboard с красивыми лампочками”, а рабочий экран, через который оператор понимает, что система реально может делать прямо сейчас, что у неё болит, и какие действия допустимы без превращения локального control plane в хаотичный shell-скрипт на кофеине 😼

## 2. Входит в scope

- `Control Center` как отдельный top-level экран
- `System Health` overview
- `Managed Services` / `service health` section
- `API / provider / connector status`
- `system resources` (`CPU`, `RAM`, `GPU`, `storage`) как operator-facing summary
- `runtime state` и `session status`
- `alerts / incidents / audit trail` section
- `active configuration` summary
- `safe config operations` для user-safe subset
- `runtime console` / operator action surface
- явные confirm/review flows для restart/stop/config apply
- `HTTP + SSE` transport contracts для snapshots и live updates

## 3. Не входит в scope

- signal ranking logic
- signal lifecycle internals
- `Trading Workspace` и signal decision UX
- полный `AI Console` interaction flow
- full model assignment policy internals
- hidden auto-recovery, которая меняет critical behavior без operator visibility
- raw infra admin layer уровня “делай что хочешь с процессами и надейся на чудо”

## 4. Архитектурные допущения

- `Control Center` живёт поверх `E1` control plane и не командует сервисами напрямую
- browser UI не обращается к managed services в обход `control-api`
- live browser updates идут через `SSE`, operator commands идут через `HTTP`
- `E2` freshness/health/incidents являются upstream foundation для части operational view
- `Control Center` должен показывать как runtime state, так и service/component state, не смешивая их в один мутный enum
- baseline UI layout опирается на approved `v15`

## 5. Главный результат эпика

После завершения `E4` разработчик должен получить:

- канонический operator screen для system/runtime control;
- понятную модель отображения статусов модулей и ограничений;
- ясную границу между observability, config actions и runtime operations;
- контракты live updates для health/alerts/status feeds;
- acceptance criteria, по которым можно проверить, что экран помогает управлять системой, а не создаёт ложное чувство контроля.

## 6. Главные пользовательские сценарии

### A. Быстрая проверка готовности системы

Пользователь открывает `Control Center` и сразу видит:

- текущий `runtime_state`;
- общую health-сводку;
- active/degraded/stale сервисы;
- открытые alerts/incidents;
- достаточно ли система готова к рабочей сессии.

### B. Триаж деградации

Пользователь получает degraded/incidents и должен быстро понять:

- что именно сломалось;
- это market-critical, context-only или model/provider problem;
- какие действия доступны:
  - restart;
  - retry;
  - перейти в defensive/restricted operation;
  - ничего не трогать и только наблюдать.

### C. Безопасная ручная операция

Пользователь хочет перезапустить сервис или применить допустимое config-изменение.

Система обязана:

- показать review/confirm;
- объяснить потенциальное влияние на active session;
- зафиксировать действие в audit;
- не выполнять silent dangerous mutation.

### D. Проверка активной конфигурации

Пользователь должен видеть:

- активную стратегию;
- active shortlist summary;
- model/provider assignments;
- risk-relevant restrictions;
- revision/consistency state конфигурации.

## 7. Логические компоненты E4

### 7.1 Control Center Shell

Экран-оболочка, которая:

- собирает operational панели;
- показывает global status и restrictions;
- принимает operator actions;
- не подменяет собой `Trading Workspace`.

### 7.2 System Health Overview

Отвечает за:

- общий статус системы;
- агрегированный health score / state;
- видимость degraded/restricted conditions;
- краткие ключевые incidents.

### 7.3 Managed Services Panel

Отвечает за:

- список сервисов и их статусы;
- latency/freshness/error context;
- operator actions типа `start`, `stop`, `restart`, `retry`;
- различение always-on и on-demand services.

### 7.4 Runtime And Session Status Panel

Отвечает за:

- показ canonical `runtime_state`;
- показ session-aware ограничений;
- объяснение, что именно сейчас разрешено или заблокировано;
- синхронность с `E1` state model.

### 7.5 Alerts / Audit Trail Panel

Отвечает за:

- активные alerts;
- recent incidents;
- operator action log;
- причины degraded/stale/error conditions.

### 7.6 Active Configuration Panel

Отвечает за:

- активную strategy summary;
- active shortlist summary;
- current config revision;
- safe-to-edit subset параметров.

### 7.7 Model / Provider Status Panel

Отвечает за:

- показ активных assignment’ов;
- provider availability;
- fallback-only markers;
- ограничения degraded fallback mode.

Важно:

- `E4` показывает и подтверждает operational/view layer;
- финальная role-model compatibility logic остаётся областью `E5`.

### 7.8 Runtime Console / Action Drawer

Отвечает за:

- confirm dialogs;
- action review cards;
- execution result feedback;
- объяснение эффекта operator action.

## 8. Отличие `Control Center` от `Trading Workspace`

`Trading Workspace` отвечает за:

- focused pair;
- signals;
- reasoning;
- risk around конкретный setup.

`Control Center` отвечает за:

- system/runtime readiness;
- service health;
- config and model status;
- operator actions над системой.

Следствие:

- `Control Center` не должен выглядеть как сигнал-экран с перекрашенными блоками;
- `Trading Workspace` не должен превращаться в service restart panel;
- различие между экранами должно быть логическим, а не только по заголовку.

## 9. Канонический layout `v1`

### 9.1 Верхний operational layer

Должен выражать:

- global runtime state;
- session status;
- health summary;
- major blocking/degraded state;
- последние критичные warnings.

### 9.2 Средний control layer

Должен включать:

- `System Health`
- `Managed Services`
- `Model / Provider Status`
- `Active Configuration`

### 9.3 Нижний supporting layer

Должен включать:

- `Recent Alerts`
- `Audit Trail`
- `Runtime Console`

### 9.4 Иерархия

Важно:

- `System Health` и `Managed Services` должны иметь больший вес, чем вспомогательные utility panels;
- demo/system utility actions не должны перетягивать внимание на себя;
- визуальный ритм должен соответствовать approved `v15`: плотный, информативный, без декоративного шума.

## 10. Слои состояния

Чтобы `Control Center` не склеил всё в один монолитный “status: probably fine”, нужно различать минимум четыре слоя состояния.

### 10.1 Runtime state

Канонические состояния из `E1`:

- `background_monitoring`
- `pre_session`
- `active_session`
- `paused`
- `review`
- `degraded`

### 10.2 Service state

Минимальные статусы сервисов:

- `healthy`
- `degraded`
- `stale`
- `stopped`
- `error`
- `disabled`

### 10.3 Provider / connector state

Минимальные статусы:

- `healthy`
- `rate_limited`
- `degraded`
- `error`
- `disabled`

### 10.4 Actionability state

Нужно отдельно показывать:

- `normal`
- `limited`
- `blocked`

То есть:

- сервис может быть `healthy`, но действие `blocked` из-за текущего runtime/session context;
- система может быть `degraded`, но часть operator actions оставаться допустимой;
- `stale` не должен silently мимикрировать под нормальный режим.

## 11. Operator actions policy

### 11.1 Допустимые действия

Минимальный безопасный набор:

- `start service`
- `stop service`
- `restart service`
- `retry failed operation`
- `apply safe config revision`
- `switch strategy` внутри разрешённого user-safe subset
- `update shortlist` внутри разрешённого user-safe subset
- `request model assignment change review`

### 11.2 Действия с обязательным confirm/review

Обязательный confirm/review нужен для:

- `stop` always-on service;
- `restart` service во время `active_session`;
- применения config revision;
- смены strategy mode;
- действий, которые могут перевести систему в `degraded`, `paused` или `restricted` behavior.

### 11.3 Что запрещено

Нельзя:

- silently выполнять dangerous actions;
- давать UI возможность менять restricted config fields без `ADR-002` правил;
- скрывать влияние операции на active session;
- делать destructive runtime actions “в один клик” без operator visibility.

## 12. Config operations boundary

### 12.1 Что относится к user-safe subset

В `E4` допускается показывать и управлять только тем, что архитектурно разрешено как user-safe:

- active strategy
- shortlist symbols
- confidence/risk-related safe thresholds
- schedule window
- notification preferences
- provider/model assignment request entrypoint

### 12.2 Что остаётся вне прямого редактирования

Не должно редактироваться напрямую из `Control Center`:

- restricted config fields;
- low-level storage/runtime internals;
- hidden fallback rules;
- provider compatibility logic;
- инженерные параметры, не предназначенные для operator control.

### 12.3 Review-card semantics

Перед apply пользователь должен видеть:

- какая revision сейчас активна;
- что именно меняется;
- validation status;
- rollback readiness;
- возможный impact на active session.

## 13. UI-facing data contracts после `E4`

### 13.1 Global health summary

Минимальные поля:

- `runtime_state`
- `overall_status`
- `actionability`
- `active_incident_count`
- `critical_incident_count`
- `last_status_refresh_at`
- `blocking_reason | null`

### 13.2 Service card contract

Минимальные поля:

- `service_id`
- `service_name`
- `service_kind`
- `lifecycle_class` (`always_on`, `background_critical`, `on_demand`)
- `status`
- `last_heartbeat_at`
- `last_error | null`
- `latency_ms | null`
- `freshness_status | null`
- `allowed_actions[]`

### 13.3 Connector / provider contract

Минимальные поля:

- `component_id`
- `component_type` (`provider`, `connector`, `api`)
- `display_name`
- `status`
- `rate_limit_state | null`
- `last_success_at | null`
- `fallback_only`
- `notes[]`

### 13.4 Alert / incident contract

Минимальные поля:

- `incident_id`
- `severity`
- `category`
- `title`
- `summary`
- `started_at`
- `resolved_at | null`
- `affected_components[]`
- `recommended_action | null`

### 13.5 Active configuration contract

Минимальные поля:

- `config_revision_id`
- `strategy_mode`
- `shortlist_symbols[]`
- `schedule_window`
- `risk_profile`
- `last_applied_at`
- `validation_state`
- `is_dirty`

### 13.6 Model assignment summary contract

Минимальные поля:

- `role_name`
- `provider_name`
- `model_name`
- `model_version`
- `availability_status`
- `fallback_only`
- `degraded_fallback_allowed`

### 13.7 Operator action result contract

Минимальные поля:

- `action_id`
- `action_type`
- `target_id`
- `status`
- `started_at`
- `finished_at | null`
- `audit_event_id | null`
- `message`

## 14. Data flow через экран

### 14.1 Upstream dependencies

`E4` читает и агрегирует:

- runtime state из `E1`
- service registry/supervisor status из `E1`
- config revision/validation state из `E1` + `ADR-002`
- ingest health/freshness/incidents из `E2`
- provider/model availability из `ADR-005`-совместимого слоя

### 14.2 Downstream effects

Operator-originated actions из `Control Center` идут дальше в:

- runtime manager
- service supervisor
- config manager
- audit trail
- future session/review layers

### 14.3 Что `E4` не вычисляет сам

`Control Center` не должен сам:

- рассчитывать signal confidence;
- принимать рыночные решения;
- ранжировать пары;
- вычислять provider compatibility;
- обходить `runtime-manager`.

## 15. Transport contract для `E4`

### 15.1 Snapshot path

Через `HTTP/JSON`:

- global control-center snapshot
- service list
- incident list
- active configuration
- model/provider summaries
- action review payloads

### 15.2 Live update path

Через `SSE`:

- runtime state changes
- service status updates
- incident open/resolve events
- connector/provider health changes
- config apply results

### 15.3 Что нельзя

Нельзя:

- строить browser UI вокруг raw process internals;
- заменять `HTTP + SSE` на full-time `WebSocket` без отдельного ADR;
- заставлять UI poll’ить всё подряд, как старый cron-job в панике.

## 16. HTTP / SSE surface expectations

### 16.1 HTTP snapshot examples

- `GET /control-center/overview`
- `GET /control-center/services`
- `GET /control-center/incidents`
- `GET /control-center/config`
- `GET /control-center/models`

### 16.2 HTTP command examples

- `POST /control-center/services/{serviceId}/restart`
- `POST /control-center/services/{serviceId}/stop`
- `POST /control-center/config/review`
- `POST /control-center/config/apply`
- `POST /control-center/strategy/change`

### 16.3 SSE stream examples

- `GET /control-center/stream`
- `GET /runtime/events/stream`
- `GET /incidents/stream`

Эти примеры фиксируют класс контракта, а не прибивают окончательные path names к полу.

## 17. Failure modes, которые `E4` обязан учитывать

### A. Сервис завис или потерял heartbeat

Экран обязан:

- показать stale/degraded status;
- не притворяться, что сервис healthy;
- дать оператору понятный action path.

### B. Connector/provider в `rate_limited`

Экран обязан:

- показать, что проблема не обязательно в ядре системы;
- обозначить scope ограничения;
- не смешивать это с runtime crash.

### C. Config revision invalid

Экран обязан:

- не применять revision silently;
- показать validation reason;
- предложить rollback или cancel.

### D. Runtime уже в `active_session`, а оператор хочет restart critical service

Экран обязан:

- показать impact warning;
- потребовать confirm;
- объяснить, что действие может изменить current session behavior.

### E. Model/provider fallback включён

Экран обязан:

- показать degraded semantics;
- не оставлять прежний вид normal/full-quality mode;
- зафиксировать visibility для audit.

### F. Alerts flood

Если incidents много, экран обязан:

- сохранить различимость `critical` vs `warning`;
- не превращать alert feed в бессмысленный лог;
- держать top-level summary читаемым.

## 18. Acceptance criteria

Эпик `E4` считается готовым, если выполняются все условия:

1. `Control Center` логически отличается от `Trading Workspace`.
2. Runtime state, service state и actionability не смешиваются в одну метку.
3. Оператор видит health/incidents/config/session status в одном рабочем экране.
4. Safe operator actions имеют review/confirm semantics там, где это требуется.
5. `HTTP + SSE` contracts спроектированы для snapshots и live updates.
6. `degraded`, `stale`, `stopped`, `error`, `rate_limited` имеют различимую UI-семантику.
7. Active configuration и model/provider summary видимы без скрытой магии.
8. UI не может silently применить restricted dangerous mutation.
9. Critical action during active session явно показывает impact.
10. Audit/incident visibility сохраняется как first-class часть экрана.

## 19. Обязательные проверки для `E4`

- проверить bootstrap snapshot `Control Center`;
- проверить live update runtime state через event stream;
- проверить различие service states и provider/connector states;
- проверить confirm/review flow для restart/stop/apply;
- проверить invalid config revision path;
- проверить degraded/fallback visibility;
- проверить, что alerts сохраняют приоритетность;
- проверить, что dangerous action не уходит без явного operator confirm;
- проверить, что `Control Center` не дублирует `Trading Workspace`.

## 20. Dependencies и границы с соседними эпиками

### 20.1 Зависимости

`E4` зависит минимум от:

- `E1` runtime/control plane foundation
- `E2` ingestion health/freshness foundation

### 20.2 Граница с `E3`

`E3` отвечает за analyst workspace.

`E4` не должен пытаться стать:

- signal screen;
- decision-support экраном по конкретной паре;
- местом, где живёт основной focusPair workflow.

### 20.3 Граница с `E5`

`E5` отвечает за role model, orchestration и final model-assignment logic.

`E4` показывает operator-facing assignment status и безопасный entrypoint в review/apply flow, но не определяет саму агентную архитектуру.

### 20.4 Граница с `E7`

`E7` отвечает за полный session lifecycle.

`E4` показывает runtime/session status и operational impact, но не определяет полную дисциплину preflight/briefing/pause transitions.

## 21. Артефакты, которые должны следовать после `E4 build-spec`

Сразу после `E4` логично подготовить:

- `E4 implementation plan — Control Center And Runtime Operations`
- `E5 build-spec — AI Roles, Orchestration And Model Assignment`
- `E7 build-spec — Session Lifecycle`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E4`.
