# E12 Build Spec — Reliability, Degraded Mode And Release Readiness

Дата: 2026-04-15
Эпик: `E12`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-002-config-validation-and-rollback-policy.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e7-session-lifecycle-preflight-briefing-active-mode-pause.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e8-demo-trading-integration-and-result-tracking.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e9-audit-trail-feedback-and-session-review.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e11-backtesting-replay-and-model-strategy-activation.md`

## 1. Цель эпика

Собрать `reliability and release-readiness layer` для `CLAY Mission Control`, который:

- определяет каноническое поведение `degraded mode`;
- задаёт честные правила для `local fallback`;
- фиксирует readiness criteria для эпиков, demo-stage и общей `v1` системы;
- вводит release gates, которые нельзя “на глазок пропустить” перед реальной эксплуатацией;
- связывает runtime incidents, fallback transitions, audit, review и operator visibility в один внятный operational policy.

`E12` нужен, чтобы система не жила в режиме “ну вроде работает, пока никто не моргнул”. Если этого слоя нет, то любой внешний сбой превращает продукт в импровизированный `bash`-скрипт с завышенной самооценкой 😼

## 2. Входит в scope

- canonical degraded mode entry policy
- degraded mode behavior across runtime, signals, UI, and review
- local fallback availability and limitation policy
- readiness criteria per critical subsystem
- readiness criteria for demo-stage usage
- release gates for `v1` progression
- operator-facing visibility of degraded and fallback state
- audit and review requirements for reliability incidents

## 3. Не входит в scope

- full enterprise incident management platform
- auto-remediation orchestration for every failure type
- high-availability cluster design
- automatic transition from demo-safe system to live capital trading
- pretending local fallback is a full replacement for cloud reasoning
- silently disabling risk controls to keep the UI looking healthy

## 4. Архитектурные допущения

- `E12` опирается на state model из `ADR-001`, config validation/rollback discipline из `ADR-002`, transport visibility из `ADR-003`, storage/audit baseline из `ADR-004` и model fallback policy из `ADR-005`
- `degraded` остаётся first-class runtime state, а не cosmetic badge в интерфейсе
- full mode и fallback mode обязаны иметь разные confidence semantics, review semantics и operator messaging
- demo-stage остаётся обязательным validation layer до любых разговоров о real-money expansion
- browser-facing reliability visibility идёт через `HTTP/JSON` snapshots и `SSE` incidents/status events
- readiness and release gates выражаются через проверяемые evidence-based criteria, а не через “ну мы уже столько документов написали, грех не запустить”

## 5. Главный результат эпика

После завершения `E12` разработчик должен получить:

- канонический `degraded mode policy`;
- ясную `local fallback policy`;
- readiness matrix для ключевых эпиков и `v1` системы;
- release gate checklist перед demo-hardening и будущим production consideration;
- acceptance criteria, по которым можно проверить, что CLAY умеет честно ограничивать себя в плохих условиях, а не притворяется всемогущим.

## 6. Главные пользовательские сценарии

### A. Внешний provider или API частично недоступен

Система:

- обнаруживает инцидент;
- переводит runtime в `degraded`, если это влияет на critical path;
- понижает confidence или блокирует часть сигналов по policy;
- явно показывает ограничения оператору;
- пишет incident в audit/review timeline.

### B. Включился local fallback

Пользователь:

- видит, что система работает в ограниченном режиме;
- понимает, какие возможности сохранены;
- понимает, что reasoning quality и scope уже не равны full mode.

Система обязана:

- не скрывать fallback activation;
- не сохранять прежний confidence semantics;
- отделять `fallback-supported` действия от `blocked-in-degraded` действий.

### C. Проверка готовности перед demo-stage

Оператор:

- смотрит readiness checklist;
- видит, какие subsystem gates закрыты;
- видит, какие критические пробелы ещё не закрыты.

Система обязана:

- не считать `demo-ready`, если нет preflight discipline, audit visibility, risk controls или result tracking;
- показывать конкретные причины неготовности.

### D. Подготовка к релизному milestone

Перед новым milestone команда:

- проверяет release gates;
- убеждается, что degraded/fallback behavior объясним и наблюдаем;
- проверяет, что demo evidence накоплена и review loop работает.

Система обязана:

- оставлять явный trail по readiness decisions;
- не подменять release gate красивым dashboard without proof.

## 7. Канонические сущности E12

### 7.1 Reliability incident

Минимальные поля:

- `incident_id`
- `started_at`
- `ended_at | null`
- `severity`
- `incident_type`
- `affected_scope[]`
- `root_cause_summary`
- `entered_degraded`
- `fallback_activated`
- `status`

### 7.2 Degraded state snapshot

Минимальные поля:

- `snapshot_id`
- `mode`
- `entered_at | null`
- `reason_codes[]`
- `blocked_features[]`
- `limited_features[]`
- `confidence_policy`
- `operator_message`

### 7.3 Fallback capability record

Минимальные поля:

- `capability_id`
- `fallback_type`
- `available_actions[]`
- `blocked_actions[]`
- `quality_limitations[]`
- `activation_rule`
- `recovery_rule`

### 7.4 Readiness check record

Минимальные поля:

- `check_id`
- `check_scope`
- `check_name`
- `status`
- `evidence_refs[]`
- `failure_reason | null`
- `checked_at`

### 7.5 Release gate decision

Минимальные поля:

- `gate_id`
- `release_stage`
- `gate_name`
- `status`
- `required_checks[]`
- `review_summary`
- `approved_by | null`
- `approved_at | null`

## 8. Degraded mode policy

### 8.1 Причины входа в degraded

Система обязана уметь входить в `degraded`, если происходит хотя бы одно из следующего:

- critical cloud model/provider outage;
- потеря essential external market/news dependency, влияющей на signal safety;
- config rollback failure to safe state;
- runtime integrity issue, при котором active mode уже нельзя считать trustworthy;
- repeated transport or service failure, из-за которого operator visibility становится неполной на critical path.

### 8.2 Что происходит при входе в degraded

Минимум:

- runtime state отмечается как `degraded`;
- UI показывает banner/status card с причиной и ограничениями;
- confidence semantics понижаются по policy;
- часть signal proposals может блокироваться;
- incident фиксируется в audit trail;
- review/history layer получает ссылку на degraded interval.

### 8.3 Что запрещено

Нельзя:

- входить в degraded silently;
- оставлять прежние confidence labels без поправки на degraded constraints;
- продолжать risky operator guidance как будто ничего не произошло;
- считать degraded merely cosmetic state.

## 9. Degraded behavior by subsystem

### 9.1 Trading workspace

В `degraded` trading workspace обязан:

- продолжать показывать last known trustworthy data с ясной маркировкой freshness;
- маркировать stale/missing inputs;
- показывать, какие signal classes now limited or blocked;
- не симулировать полноту reasoning при отсутствии upstream evidence.

### 9.2 Control center

`Control Center` обязан:

- показывать active incidents;
- показывать degraded reason codes;
- показывать fallback activation state;
- давать operator-safe actions только в пределах policy;
- не маскировать broken integrations как “temporarily unavailable but probably fine”.

### 9.3 Session lifecycle

Session layer обязан:

- блокировать `session start`, если readiness for active analysis уже не соблюдается;
- разрешать controlled pause/review/recovery transitions;
- требовать повторный `preflight`, если degraded incident затронул critical dependencies.

### 9.4 Review and audit

Review/history обязан:

- хранить degraded intervals как first-class evidence;
- связывать incidents с session outcomes, signal quality и demo results;
- позволять анализировать, стала ли degraded работа причиной missed/mismatched outcomes.

## 10. Local fallback policy

### 10.1 Когда fallback допустим

Local fallback допустим только как ограниченный режим, если:

- primary assignment or provider unavailable;
- fallback explicitly marked as compatible in policy;
- operator visibility remains intact;
- system can честно описать ограничения fallback.

### 10.2 Что fallback может делать в `v1`

Допустимо:

- давать simplified text assistance;
- поддерживать базовую сигнальную логику;
- помогать review/triage в reduced-confidence mode;
- сохранять continuity для non-critical operator workflows.

### 10.3 Что fallback не может обещать

Fallback не может:

- притворяться полноценной заменой `Chief Agent`;
- выдавать full-strength strategy synthesis;
- автоматически поднимать blocked high-risk actions;
- убирать degraded labeling ради “красоты интерфейса”.

### 10.4 UI-различие full mode vs fallback

Оператор обязан видеть:

- что активирован fallback;
- какой именно fallback используется;
- какие действия доступны;
- какие действия заблокированы;
- какие quality limitations действуют прямо сейчас.

## 11. Reliability visibility and audit policy

### 11.1 Что обязано быть видно в UI

Минимум:

- current runtime mode;
- active incidents;
- degraded/fallback banner;
- affected features;
- last successful refresh or provider success time;
- recovery status.

### 11.2 Что обязано фиксироваться в audit

Минимум:

- причина входа в degraded;
- affected assignments/providers;
- fallback activation and recovery events;
- blocked or downgraded actions;
- operator acknowledgements and confirmations;
- exit from degraded and post-incident summary.

### 11.3 Связь с review

Review screen обязан позволять ответить на вопросы:

- сколько времени система работала в degraded;
- как это повлияло на signals, demo outcomes и operator decisions;
- не была ли readiness/release decision принята на плохой evidence base.

## 12. Readiness criteria policy

### 12.1 Готовность отдельных эпиков

Ключевой эпик считается readiness-готовым только если:

- есть build-spec и implementation plan;
- есть реализуемые acceptance criteria;
- UI/API contracts не противоречат соседним эпикам;
- критические failure modes описаны;
- audit/review implications понятны.

### 12.2 Готовность общей `v1` системы

`v1` нельзя считать system-ready без:

- runtime foundation and control plane;
- data ingestion and local history;
- trading workspace and control center;
- AI assignment and fallback policy;
- signal/risk layer;
- session discipline;
- demo integration and result tracking;
- audit/review layer;
- reliability and degraded policy.

### 12.3 Demo-stage readiness

`demo-ready` допускается только если:

- preflight стабильно отсекает unsafe starts;
- ranked signals and risk controls работают объяснимо;
- demo results ingest/reconciliation работает честно;
- degraded mode visibility и fallback labeling работают;
- audit trail и review loop позволяют разобрать каждую сессию;
- есть накопление evidence по нескольким demo sessions, а не по одному удачному забегу.

### 12.4 Что не считается readiness evidence

Не считаются достаточным evidence:

- красивый UI без operational truth;
- одна успешная сессия;
- backtest/replay без demo validation;
- manual confidence without audit trail;
- скрытые fallback transitions.

## 13. Release gates policy

### 13.1 Базовые release gates для `v1`

Нельзя двигаться к следующему milestone без подтверждённых gate-пунктов:

- `preflight gate`
- `risk-control gate`
- `audit-trail gate`
- `demo-read integration gate`
- `degraded visibility gate`
- `review and feedback gate`

### 13.2 Смысл каждого gate

`preflight gate`:

- system blocks unsafe session start;
- critical dependency failures surfaced before active mode.

`risk-control gate`:

- risky signals can be downgraded or blocked;
- operator sees why risk action was taken.

`audit-trail gate`:

- critical actions, signals, degraded events and operator decisions are reconstructable.

`demo-read integration gate`:

- demo outcomes can be reconciled against signals and sessions.

`degraded visibility gate`:

- operator can immediately distinguish full mode, degraded mode and fallback mode.

`review and feedback gate`:

- session outcomes and operator feedback can inform later tuning and release decisions.

### 13.3 Что запрещено релизить

Нельзя релизить milestone, если:

- degraded/fallback incidents не видны в UI;
- preflight обходится вручную без системной дисциплины;
- audit не позволяет восстановить critical path;
- demo/review evidence отсутствует или fragmented;
- release decision не может быть объяснена через stored evidence.

## 14. Operational rollout policy

### 14.1 Порядок допуска

Рекомендуемый порядок:

1. planning-complete and contract-aligned state;
2. implementation with audit visibility;
3. controlled demo sessions;
4. multi-session review and incident analysis;
5. readiness decision;
6. только потом обсуждение расширения режима эксплуатации.

### 14.2 Роль demo-stage

Demo-stage обязателен как:

- safety buffer;
- operational learning phase;
- источник incident and recovery evidence;
- фильтр против преждевременной уверенности.

### 14.3 Переход дальше

Даже при хорошем demo-stage `E12` не даёт automatic permission на real-money launch.

`E12` даёт:

- disciplined readiness framework;
- объяснимые release gates;
- честную operational visibility.

Но финальное расширение режима должно происходить отдельным решением, а не “ну вроде график растёт, ship it”.

## 15. Acceptance criteria

Build-spec считается качественно собранным, если:

- описаны причины входа в `degraded`;
- описано поведение UI и runtime в degraded mode;
- описаны доступные и запрещённые обещания local fallback;
- readiness criteria разделены на epic-level, system-level и demo-level;
- release gates сформулированы как проверяемые условия;
- policy явно запрещает silent fallback, fake confidence и релиз без operational evidence.

## 16. Проверки консистентности

Перед переходом к implementation plan нужно отдельно проверить:

- согласован ли degraded state с `ADR-001`;
- согласован ли fallback policy с `ADR-005`;
- согласованы ли audit/review требования с `E9`;
- согласованы ли demo-readiness and result tracking expectations с `E8`;
- не превращает ли `E12` release readiness в implicit approval for real-money mode.

## 17. Зависимости

Напрямую завязан на:

- `E1` runtime/state/control foundation
- `E4` operator visibility
- `E5` model/provider routing and fallback policy
- `E6` confidence/risk semantics
- `E7` preflight and session discipline
- `E8` demo validation layer
- `E9` audit/review layer
- `E11` replay/validation evidence layer

## 18. Следующий артефакт

Следующий правильный шаг после этого build-spec:

- собрать `E12 implementation plan` в execution-grade формате;
- разложить reliability surfaces по backend/frontend contracts;
- определить readiness checklist assembly, incident timeline assembly и gate evaluation flow;
- только потом переходить к фактической реализации reliability layer.
