# E9 Build Spec — Audit Trail, Feedback And Session Review

Дата: 2026-04-15
Эпик: `E9`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e6-signal-lifecycle-ranking-and-risk-control.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e8-demo-trading-integration-and-result-tracking.md`

## 1. Цель эпика

Собрать `audit / review layer` для `CLAY Mission Control`, который:

- сохраняет объяснимую историю действий, решений, сигналов и сбоев;
- позволяет пользователю оставлять рабочий feedback по сигналам и сессиям;
- даёт `session review` по реальным данным, а не по памяти после тяжёлого торгового дня;
- позволяет `Chief Agent` помогать с post-session synthesis без скрытого переписывания стратегии;
- превращает историю системы в обучаемый контур, а не в кладбище JSON-файлов.

`E9` нужен, чтобы CLAY умел не только говорить “вот сейчас мне кажется красиво”, но и честно отвечать, что именно произошло, кто это решил, что сработало, что не сработало и почему. Иначе audit будет как `/var/log/*` после плохого weekend-upgrade: вроде всё где-то есть, но трогать страшно 😼

## 2. Входит в scope

- canonical audit event model
- persistent audit trail policy for signals, sessions, operators, AI roles, config and degraded incidents
- feedback workflow for signal/session outcomes
- `session review` screen semantics
- review filters and slicing policy
- AI-assisted review summary policy
- UI-facing contracts for audit/history/review surfaces

## 3. Не входит в scope

- raw market ingestion/storage internals
- live trade execution
- knowledge-base retrieval layer
- full replay/backtesting engine
- autonomous strategy mutation
- external compliance/regulatory reporting

## 4. Архитектурные допущения

- `E9` опирается на `E6` signal semantics и `E8` demo result linking
- `E9` использует storage policy из `ADR-004`, где signals/sessions/decisions/feedback/audit являются отдельной ценностью и не исчезают автоматически
- browser-facing review/history остаются на `HTTP/JSON`, realtime additions допускаются через `SSE`
- `Chief Agent` может делать review synthesis, но не может silently менять strategy/model assignment
- audit обязан связывать события через `correlation_id` и traceable object references
- review слой не должен зависеть от knowledge/RAG как hard blocker раннего `v1`

## 5. Главный результат эпика

После завершения `E9` разработчик должен получить:

- канонический audit event model `v1`;
- понятный feedback workflow;
- review screen semantics для завершённой сессии;
- управляемый AI-assisted review без hidden autonomy;
- acceptance criteria, по которым можно проверить, что история системы объяснима и пригодна для обучения.

## 6. Главные пользовательские сценарии

### A. Review после demo-сессии

Пользователь:

- завершает сессию;
- открывает review screen;
- видит сигналы, решения, demo outcomes и ключевые ошибки;
- понимает, что было хорошим execution, что было missed, а что было mismatch.

### B. Feedback по сигналу

Пользователь должна иметь возможность отметить:

- вошла / не вошла;
- почему отклонила;
- был ли сигнал полезным;
- доверяла ли объяснению.

Система обязана:

- сохранить feedback в связке с signal history;
- не терять связь с session context;
- сделать feedback доступным для будущего review.

### C. Incident review

Если в сессии был degraded/fallback/critical incident, review обязан показать:

- когда это произошло;
- что именно сломалось;
- как это повлияло на actionability и confidence;
- продолжалась ли сессия после инцидента.

### D. AI-assisted review summary

`Chief Agent` может:

- собрать summary по сессии;
- выделить recurring mistakes;
- предложить review notes или ideas for caution.

Но:

- не может silently менять стратегию;
- не может скрывать неудобные outcomes;
- не может выдавать suggestion за уже принятое решение.

## 7. Канонические сущности E9

### 7.1 Audit event

Минимальные поля:

- `event_id`
- `timestamp`
- `actor`
- `module`
- `event_type`
- `object_id`
- `severity`
- `correlation_id`
- `explanation`
- `payload`

### 7.2 Feedback record

Минимальные поля:

- `feedback_id`
- `signal_id`
- `session_id`
- `submitted_at`
- `entry_decision`
- `rejection_reason | null`
- `signal_usefulness`
- `trusted_explanation`
- `freeform_note | null`

### 7.3 Session review summary

Минимальные поля:

- `session_id`
- `started_at`
- `ended_at`
- `primary_focus_pair`
- `strategy_used`
- `model_assignment_snapshot`
- `signal_count`
- `executed_count`
- `missed_count`
- `mismatch_count`
- `degraded_incident_count`
- `review_summary`

### 7.4 AI review suggestion

Минимальные поля:

- `suggestion_id`
- `session_id`
- `author_role`
- `summary`
- `strengths[]`
- `weaknesses[]`
- `proposed_followups[]`
- `requires_confirmation`

## 8. Audit event model policy

### 8.1 Что пишется всегда

Минимально обязательные события:

- signal creation/update/invalidation
- operator decisions
- session start/pause/resume/stop/review
- preflight results
- degraded/fallback incidents
- strategy changes
- model assignment changes
- AI console commands
- demo trade links and result reconciliation
- feedback submission

### 8.2 Базовое правило

Audit event обязан быть достаточно структурированным, чтобы:

- его можно было искать;
- его можно было фильтровать;
- его можно было связать с соседними событиями;
- он оставался полезным без ручной археологии по логам.

### 8.3 Что запрещено

Нельзя:

- писать только prose без структурных полей;
- смешивать разные event types в одном бесформенном blob;
- терять `correlation_id`, если событие относится к signal/session chain.

## 9. Feedback workflow policy

### 9.1 Обязательные поля

Минимум:

- `entry_decision`
- `signal_usefulness`
- `trusted_explanation`

### 9.2 Необязательные поля

Допустимо:

- `rejection_reason`
- `freeform_note`
- manual review tags

### 9.3 Правило связи

Feedback обязан связываться минимум с:

- `signal_id`
- `session_id`
- relevant demo outcome, если он уже существует

### 9.4 Что запрещено

Нельзя:

- хранить feedback отдельно от signal history;
- делать feedback purely freeform without usable structure;
- silently редактировать feedback post-hoc без trace.

## 10. Session review screen policy

### 10.1 Что должен показывать review screen

Минимум:

- session timeline
- shortlist / signal history
- operator decisions
- demo outcomes
- degraded incidents
- strategy/model snapshot
- captured feedback
- AI-assisted summary

### 10.2 Основные review metrics

Минимально важные:

- number of signals
- number of executed trades
- number of missed signals
- number of mismatches
- late execution count
- confidence band distribution
- incident count
- session-level outcome summary

### 10.3 Что запрещено

Нельзя:

- строить review только как список логов без synthesis;
- показывать только итоговый PnL;
- скрывать mismatch, miss или degraded history ради “красивого” отчёта.

## 11. Review filtering policy

### 11.1 Обязательные фильтры

- by pair
- by strategy
- by time
- by model version
- by confidence band

### 11.2 Допустимые дополнительные фильтры

- by outcome status
- by degraded incident presence
- by feedback usefulness rating

### 11.3 Что важно

Фильтры должны работать по structured fields, а не по хрупкому full-text угадыванию.

## 12. AI-assisted review policy

### 12.1 Что разрешено `Chief Agent`

`Chief Agent` может:

- собрать concise post-session summary;
- отметить recurring patterns;
- выделить suspicious mismatches;
- предложить follow-up review questions;
- предложить operator-reviewed improvement ideas.

### 12.2 Что запрещено

Нельзя:

- silently менять strategy mode;
- silently менять active model;
- скрывать плохие outcomes в summary;
- выдавать recommendation за уже применённое изменение.

### 12.3 Review-card discipline

Любая AI recommendation, выходящая за рамки описания истории, должна:

- оформляться как review card;
- иметь explanation;
- быть operator-visible;
- требовать подтверждение перед дальнейшим действием.

## 13. UI-facing contracts после `E9`

### 13.1 Audit event contract

Минимальные поля:

- `event_id`
- `timestamp`
- `event_type`
- `actor`
- `module`
- `severity`
- `correlation_id`
- `summary`

### 13.2 Feedback card contract

Минимальные поля:

- `feedback_id`
- `signal_id`
- `entry_decision`
- `signal_usefulness`
- `trusted_explanation`
- `rejection_reason | null`
- `freeform_note | null`

### 13.3 Session review contract

Минимальные поля:

- `session_id`
- `timeline_items[]`
- `signal_items[]`
- `decision_items[]`
- `demo_outcomes[]`
- `incident_items[]`
- `feedback_items[]`
- `ai_review_summary | null`

### 13.4 AI review card contract

Минимальные поля:

- `suggestion_id`
- `summary`
- `strengths[]`
- `weaknesses[]`
- `proposed_followups[]`
- `requires_confirmation`

## 14. Transport and interaction expectations

### 14.1 HTTP snapshot examples

- `GET /audit/events`
- `GET /session-review/{session_id}`
- `GET /signals/{signalId}/feedback`
- `GET /review/ai-summaries/{session_id}`

### 14.2 HTTP command examples

- `POST /signals/{signalId}/feedback`
- `POST /session-review/{session_id}/annotate`
- `POST /review/ai-summaries/{session_id}/acknowledge`

### 14.3 SSE stream examples

- `GET /audit/events/stream`
- `GET /session-review/{session_id}/stream`

### 14.4 Что нельзя

Нельзя:

- строить review/history целиком на polling;
- публиковать browser-facing raw internal logs без нормализации;
- смешивать interactive commands и history fetches в один мутный transport pattern.

## 15. Failure modes, которые `E9` обязан учитывать

### A. Есть события, но нет связки между ними

Система обязана:

- показывать missing correlation;
- не изображать complete history;
- оставлять trace для incident analysis.

### B. Feedback отвязан от сигнала

Система обязана:

- не принимать orphaned feedback как полноценный record;
- требовать link to signal/session;
- явно помечать unresolved state.

### C. AI review скрывает неудобные итоги

Система обязана:

- не подменять raw review data AI summary;
- показывать summary как дополнительный слой, а не единственную правду;
- сохранять operator access к base evidence.

### D. Review screen не показывает degraded incident

Система обязана:

- считать это review integrity bug;
- не выдавать такую review картину за полную;
- позволять trace back к audit events.

## 16. Acceptance criteria

Эпик `E9` считается готовым, если выполняются все условия:

1. У системы есть канонический audit event model с обязательными полями и correlation semantics.
2. Feedback workflow связывается с signal/session history и не живёт отдельно.
3. Session review показывает signals, decisions, demo outcomes, incidents и feedback в одной связанной картине.
4. Обязательные review filters покрывают pair, strategy, time, model version и confidence band.
5. `Chief Agent` может помогать в review, но не может silently менять стратегию или модель.
6. UI-facing contracts позволяют строить review/history экраны без ad-hoc parsing.
7. Failure modes вокруг missing correlation, orphaned feedback и misleading AI review описаны явно.

## 17. Обязательные проверки для `E9`

- проверить, что critical audit events всегда записываются;
- проверить correlation between signal, session, decision and outcome chains;
- проверить feedback submit/link flow;
- проверить review filters по pair/strategy/time/model/confidence;
- проверить visibility degraded incidents in review;
- проверить, что AI summary не скрывает raw evidence;
- проверить, что AI recommendations остаются review-card flow;
- проверить, что review/history можно получать через `HTTP`, а не только через realtime transport.

## 18. Dependencies и границы с соседними эпиками

### 18.1 Зависимости

`E9` зависит минимум от:

- `E6` signal and confidence semantics
- `E8` demo outcomes and link status
- `ADR-004` storage policy for sessions, decisions, feedback and audit

### 18.2 Граница с `E8`

`E8` поставляет demo evidence layer.

`E9` не должен:

- переопределять demo result linking;
- превращаться в exchange integration module;
- скрывать distinction between matched/missed/mismatched outcomes.

### 18.3 Граница с `E10`

`E10` отвечает за knowledge base and research layer.

`E9` не должен делать retrieval hard dependency для review/history.

### 18.4 Граница с live improvement loop

`E9` может выявлять идеи для улучшения.

Но он не должен сам запускать hidden self-modification системы.

## 19. Артефакты, которые должны следовать после `E9 build-spec`

Сразу после `E9` логично подготовить:

- `E9 implementation plan — Audit Trail, Feedback And Session Review`
- `E10 build-spec — Knowledge Base And Research Layer`
- при необходимости отдельный runbook по `session review and audit integrity`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E9`.
