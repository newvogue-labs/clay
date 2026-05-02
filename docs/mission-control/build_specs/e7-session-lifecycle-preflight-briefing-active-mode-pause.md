# E7 Build Spec — Session Lifecycle: Preflight, Briefing, Active Mode, Pause

Дата: 2026-04-15
Эпик: `E7`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-002-config-validation-and-rollback-policy.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e3-trading-screen-and-live-signal-workspace.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e4-control-center-and-runtime-operations.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e6-signal-lifecycle-ranking-and-risk-control.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/runbooks/runbook-001-preflight-degraded-mode.md`

## 1. Цель эпика

Собрать `session lifecycle` для `CLAY Mission Control`, который:

- делает вход в торговую сессию дисциплинированным;
- связывает `preflight`, `briefing`, `active_session`, `pause`, `review` и `degraded` в одну понятную модель;
- не допускает unsafe переходы в `active_session`;
- показывает пользователю, что именно подтверждено, что ограничено и когда надо остановиться;
- делает session flow повторяемым, а не зависящим от настроения текущего демона в runtime 😼

## 2. Входит в scope

- hard `preflight` policy
- `pre-session briefing`
- session admission rules
- `active_session` state machine
- `pause / resume` semantics
- `degraded` re-entry restrictions
- dynamic pair replacement proposal flow
- session-facing UI/data contracts
- transport contracts для `preflight` progress и session events

## 3. Не входит в scope

- signal ranking internals
- model/provider registry internals
- full audit/review analytics
- trade execution workflow
- demo/live result linking
- knowledge-base workflows

## 4. Архитектурные допущения

- canonical runtime states берутся из `E1` и не переизобретаются в `E7`
- `preflight` использует service/data/config/model readiness из `E1`, `E2`, `E4`, `E5`, `E6`
- вход в `active_session` допускается только после валидного `preflight`
- `briefing` handoff обязан синхронизироваться с `E3 Trading Workspace`
- browser-facing progress и session events идут через `HTTP + SSE`
- degraded recovery требует повторного `preflight`, а не “ну вроде уже починилось”

## 5. Главный результат эпика

После завершения `E7` разработчик должен получить:

- канонический session lifecycle `v1`;
- ясный admission policy для `active_session`;
- структуру `briefing` как обязательного handoff-слоя;
- понятную модель pause/resume/stop behavior;
- acceptance criteria, по которым можно проверить, что сессия управляется безопасно и повторяемо.

## 6. Главные пользовательские сценарии

### A. Нормальный старт сессии

Пользователь:

- запускает `preflight`;
- видит результаты checks;
- получает `briefing`;
- подтверждает shortlist/strategy/session start;
- входит в `active_session`.

### B. Блокировка старта

Если есть hard blockers:

- market data stale;
- critical service crashed;
- chief model недоступна без допустимого fallback;
- config invalid;
- risk limits не загружены.

Система обязана:

- не пускать в `active_session`;
- объяснить причину;
- остаться в `pre_session` или уйти в `degraded`.

### C. Пауза активной сессии

Пользователь или система переводит session flow в `paused`.

Система обязана:

- сохранить контекст;
- остановить normal action flow;
- не притворяться, что live session идёт как обычно.

### D. Dynamic pair replacement

Во время активной сессии система может предложить заменить пару в shortlist.

Система обязана:

- показать сравнение текущей и новой пары;
- показать причину замены;
- не менять focus silently.

## 7. Session state model

### 7.1 Канонические runtime states

Из `E1`:

- `background_monitoring`
- `pre_session`
- `active_session`
- `paused`
- `review`
- `degraded`

### 7.2 Что `E7` добавляет

`E7` не добавляет новый runtime enum, а добавляет дисциплину:

- когда разрешён вход в состояние;
- какие checks обязательны;
- какие handoff data обязаны существовать;
- какие переходы требуют operator confirmation.

## 8. Hard preflight policy

### 8.1 Когда запускается

`Preflight` обязателен:

- перед каждой новой активной сессией;
- после ручной смены модели или стратегии перед входом в сессию;
- после recovery из `degraded`, если пользователь хочет снова войти в рабочий режим.

### 8.2 Обязательные check categories

#### Runtime checks

- `runtime-manager` доступен
- `control-api` доступен
- `service-registry` доступен
- `health-monitor` доступен
- `scheduler` доступен

#### Service checks

- required `always-on services` healthy
- required `background-critical services` в допустимом status
- ни один critical service не находится в `error`

#### Data checks

- market data не stale
- connector state не unsafe stale
- ingest freshness укладывается в допустимое окно

#### Session checks

- shortlist подтверждён
- active strategy назначена
- active model assignment валиден
- risk thresholds загружены
- user-safe config применён

#### Audit checks

- audit writer доступен
- результаты preflight могут быть записаны

### 8.3 Результаты preflight

Минимальные статусы:

- `pass`
- `soft_fail`
- `hard_fail`

### 8.4 Admission rule

Вход в `active_session` разрешён только при:

- `pass`, или
- `soft_fail`, если strict safety rules не нарушены и пользователь осознанно подтверждает продолжение.

`hard_fail` всегда блокирует вход.

## 9. Pre-session briefing policy

### 9.1 Обязательная структура briefing

Минимальные секции:

- shortlist
- market context
- sentiment summary
- active strategy
- risk alerts
- AI summary
- primary focus pair
- backup pairs

### 9.2 Роль briefing

`Briefing` не является декоративным экраном.

Он обязан:

- зафиксировать session context перед стартом;
- выдать `primary_focus_pair`;
- выдать `backup_pairs[]`;
- передать handoff в `Trading Workspace`;
- не заставлять пользователя заново собирать картину вручную после старта.

## 10. Session admission and start flow

### 10.1 Канонический start path

Нормальный `v1` path:

1. `background_monitoring`
2. `pre_session`
3. `preflight`
4. `briefing`
5. operator confirmation
6. `active_session`
7. workspace handoff

### 10.2 Что запрещено

Нельзя:

- переходить в `active_session` без успешного/условно допустимого `preflight`;
- silently пропускать `briefing`;
- открывать workspace с “какой-то парой” без ясного focus source.

## 11. Active session state machine

### 11.1 В активной сессии система обязана поддерживать

- live workspace updates
- risk/signal changes
- dynamic pair replacement proposals
- operator pause
- degraded incident handling

### 11.2 Разрешённые переходы

Минимально важные:

- `pre_session -> active_session`
- `active_session -> paused`
- `paused -> active_session`
- `active_session -> review`
- `active_session -> degraded`
- `paused -> degraded`
- `degraded -> pre_session`
- `degraded -> background_monitoring`

### 11.3 Что запрещено

Нельзя:

- `degraded -> active_session` без повторного `preflight`;
- resume в normal mode, если blocking condition не снят;
- silently продолжать session при critical degraded condition.

## 12. Pause / resume semantics

### 12.1 `paused`

При переходе в `paused` система обязана:

- остановить normal operator flow;
- сохранить session context;
- показать, что active streams не считаются normal active mode;
- не терять текущий focusPair/workspace context.

### 12.2 Resume

Возврат из `paused` в `active_session` допустим только если:

- blocking degraded condition отсутствует;
- critical services и data freshness снова допустимы;
- runtime manager разрешает переход.

### 12.3 Длительная пауза

Если pause слишком долгая:

- session может потребовать lightweight revalidation;
- stale context должен быть явно помечен;
- система не должна маскировать pause-resume как непрерывную live-сессию.

## 13. Dynamic pair replacement policy

### 13.1 Когда разрешено предлагать замену

Система может предложить pair replacement минимум при:

- исходная pair потеряла relevance;
- новый candidate существенно сильнее по ranking;
- risk posture текущей пары ухудшился;
- context shift изменил shortlist priorities.

### 13.2 Что должен видеть пользователь

Минимум:

- текущая pair
- предлагаемая pair
- краткое сравнение
- reason summary
- confidence/risk difference
- требуется ли подтверждение

### 13.3 Что запрещено

Нельзя:

- silently менять pair в active session;
- скрывать причину замены;
- делать вид, что replacement уже принято.

## 14. Degraded mode interaction with session lifecycle

### 14.1 Автоматический вход в degraded

Система обязана входить в `degraded`, если:

- chief model недоступна;
- critical API недоступен;
- market data stale;
- critical service упал;
- applied config invalid;
- обязательный safety check не выполнен.

### 14.2 Что происходит с активной сессией

В degraded during active session:

- confidence сигналов понижается;
- high-risk signals могут блокироваться;
- operator должен видеть, можно ли продолжать monitoring;
- система может рекомендовать stop или pause.

### 14.3 Recovery policy

Возврат из `degraded` допускается только если:

- причина устранена;
- critical services healthy;
- stale data восстановлены;
- config валиден;
- `preflight` повторно пройден.

## 15. UI-facing data contracts после `E7`

### 15.1 Preflight result contract

Минимальные поля:

- `preflight_id`
- `status`
- `started_at`
- `finished_at | null`
- `checks[]`
- `blocking_reasons[]`
- `soft_warnings[]`
- `can_enter_active_session`

### 15.2 Briefing contract

Минимальные поля:

- `briefing_id`
- `primary_focus_pair`
- `backup_pairs[]`
- `active_strategy`
- `risk_alerts[]`
- `ai_summary`
- `market_context_summary`
- `sentiment_summary`

### 15.3 Session state contract

Минимальные поля:

- `runtime_state`
- `session_id | null`
- `session_started_at | null`
- `pause_reason | null`
- `degraded_reason | null`
- `can_resume`
- `can_enter_active_session`

### 15.4 Pair replacement proposal contract

Минимальные поля:

- `proposal_id`
- `current_pair`
- `proposed_pair`
- `reason_summary`
- `confidence_diff`
- `risk_diff`
- `requires_confirmation`

## 16. Transport and interaction expectations

### 16.1 HTTP snapshot examples

- `GET /preflight/latest`
- `GET /briefing/current`
- `GET /session/state`
- `GET /session/pair-replacement/proposals`

### 16.2 HTTP command examples

- `POST /preflight/run`
- `POST /session/start`
- `POST /session/pause`
- `POST /session/resume`
- `POST /session/stop`
- `POST /session/pair-replacement/{proposalId}/accept`
- `POST /session/pair-replacement/{proposalId}/reject`

### 16.3 SSE stream examples

- `GET /preflight/stream`
- `GET /session/events/stream`
- `GET /briefing/stream`

### 16.4 Что нельзя

Нельзя:

- строить session discipline только как frontend wizard-state;
- poll’ить preflight progress вместо event stream без причины;
- разрешать unsafe state transitions в обход runtime manager.

## 17. Failure modes, которые `E7` обязан учитывать

### A. Hard preflight fail

Система обязана:

- заблокировать `active_session`;
- показать blocking reasons;
- сохранить trace в audit.

### B. Soft fail with conditional continuation

Система обязана:

- явно показать ограничения;
- потребовать operator awareness;
- не выдавать conditional admission за full-green state.

### C. Briefing handoff incomplete

Система обязана:

- не открывать workspace как будто всё готово;
- показать, что handoff incomplete;
- не выдумывать primary pair.

### D. Resume after degraded incident

Система обязана:

- не разрешать resume без revalidation;
- не скрывать degraded history.

### E. Pair replacement during unstable session

Система обязана:

- не применять replacement silently;
- показать risk and confidence delta;
- позволить reject.

## 18. Acceptance criteria

Эпик `E7` считается готовым, если выполняются все условия:

1. `Preflight` отделён от `briefing` и имеет чёткие PASS / SOFT FAIL / HARD FAIL semantics.
2. Вход в `active_session` без допустимого `preflight` невозможен.
3. `Briefing` даёт валидный handoff в `Trading Workspace`.
4. `paused`, `degraded`, `review` и active transitions остаются согласованы с `E1`.
5. Resume после degraded требует revalidation.
6. Dynamic pair replacement остаётся operator-confirmed flow.
7. UI-facing contracts позволяют показывать session state честно и без скрытых unsafe shortcuts.

## 19. Обязательные проверки для `E7`

- проверить hard preflight blocking;
- проверить soft-fail conditional continuation;
- проверить briefing payload completeness;
- проверить session start flow;
- проверить pause/resume flow;
- проверить degraded recovery flow;
- проверить pair replacement proposal visibility;
- проверить запрет `degraded -> active_session` без preflight;
- проверить, что workspace handoff не ломается после briefing.

## 20. Dependencies и границы с соседними эпиками

### 20.1 Зависимости

`E7` зависит минимум от:

- `E3` workspace contracts
- `E4` runtime/control operational view
- `E6` signal/risk semantics

### 20.2 Граница с `E6`

`E6` даёт signal/risk semantics.

`E7` не должен:

- переопределять signal schema;
- дублировать ranking logic;
- превращаться в signal engine.

### 20.3 Граница с `E8`

`E8` отвечает за demo trading integration и result tracking.

`E7` не описывает связь сигнала с реальной сделкой.

### 20.4 Граница с `E9`

`E9` отвечает за session review, feedback и audit analytics.

`E7` готовит session flow и raw state transitions, но не финальную review-аналитику.

## 21. Артефакты, которые должны следовать после `E7 build-spec`

Сразу после `E7` логично подготовить:

- `E7 implementation plan — Session Lifecycle`
- `E8 build-spec — Demo Trading Integration And Result Tracking`
- `E9 build-spec — Audit Trail, Feedback And Session Review`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E7`.
