# E6 Build Spec — Signal Lifecycle, Ranking And Risk-Control

Дата: 2026-04-15
Эпик: `E6`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e3-trading-screen-and-live-signal-workspace.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e5-ai-roles-orchestration-and-model-assignment.md`

## 1. Цель эпика

Собрать `signal engine` для `CLAY Mission Control`, который:

- делает сигналы объяснимыми и структурированными;
- умеет ранжировать кандидаты без чёрной магии;
- отслеживает lifecycle сигнала от `active` до `weakening` и `invalidated`;
- связывает confidence, risk posture и data quality;
- умеет ограничивать или блокировать actionability в unsafe conditions.

`E6` строит не “таблицу BUY/SELL с красивыми процентами”, а дисциплинированный слой, который объясняет, почему сигнал существует, насколько ему можно доверять, как он деградирует и когда его надо честно убить, а не тащить дальше как зомби-процесс 😼

## 2. Входит в scope

- canonical signal schema
- разделение `signal summary` и `expanded explanation`
- ranking logic и ranking inputs
- signal lifecycle states и transitions
- weakening / invalidation / expiry semantics
- confidence model для operator-facing слоя
- risk-control triggers и response actions
- strategy mode switching proposal semantics
- UI-facing risk and signal contracts для `E3`

## 3. Не входит в scope

- raw ingestion/storage logic
- полный `Trading Workspace` UI
- full session lifecycle / preflight discipline
- full backtesting framework
- execution / order placement
- knowledge/RAG logic
- hidden auto-execution под видом “умного risk engine”

## 4. Архитектурные допущения

- `E6` опирается на `E3` workspace contracts и `E5` AI orchestration foundation
- confidence и ranking не должны вычисляться только на одном источнике
- stale/degraded/runtime limitations обязаны влиять на actionability сигнала
- risk engine должен быть explainable и operator-visible
- signal layer публикует snapshots через `HTTP`, live changes через `SSE`
- UI не должен сам вычислять signal confidence или risk decisions

## 5. Главный результат эпика

После завершения `E6` разработчик должен получить:

- каноническую signal schema для `v1`;
- понятный ranking model для shortlist candidates;
- lifecycle semantics `active / weakening / invalidated / expired / absent`;
- risk-control policy, которая умеет warning/reduce/block/defensive;
- acceptance criteria, по которым можно проверить, что сигналы объяснимы, ограничиваемы и не маскируют unsafe conditions.

## 6. Главные пользовательские сценарии

### A. Появление нового сильного сигнала

Система:

- получает candidate input;
- оценивает confidence и risk;
- помещает сигнал в ranking;
- публикует structured summary в `Trading Workspace`.

### B. Ослабление сигнала

Система видит ухудшение:

- market structure;
- context alignment;
- freshness;
- confidence.

Она обязана:

- перевести сигнал в `weakening`;
- показать причину;
- не делать вид, что signal всё ещё untouched.

### C. Инвалидация сигнала

Если нарушены critical conditions:

- setup invalidated;
- stale market context;
- severe conflict;
- blocking risk trigger.

Система обязана:

- перевести сигнал в `invalidated`;
- сохранить invalidation reason;
- снизить или убрать actionability.

### D. Смена strategy mode

Если рынок или risk posture меняются, система может предложить:

- перейти в `Trend-following`;
- перейти в `Momentum`;
- перейти в `Defensive`.

Но:

- это proposal, а не hidden silent switch;
- пользователь должен видеть причину и impact.

## 7. Канонические сущности E6

### 7.1 Signal summary

Краткая operator-facing сущность.

Минимальные поля:

- `signal_id`
- `pair`
- `direction`
- `state`
- `confidence`
- `timeframe`
- `entry_summary`
- `target_summary`
- `stop_summary`
- `last_updated_at`
- `rank | null`
- `invalidation_reason | null`

### 7.2 Expanded signal explanation

Развёрнутый слой объяснения.

Минимальные поля:

- `signal_id`
- `headline_explanation`
- `why_now`
- `technical_confluence[]`
- `contextual_factors[]`
- `confidence_notes`
- `risk_notes[]`
- `conflict_summary | null`

### 7.3 Risk snapshot

Минимальные поля:

- `pair`
- `risk_posture`
- `max_drawdown_estimate`
- `position_size_hint`
- `risk_reward_hint`
- `defensive_constraints[]`
- `actionability`

### 7.4 Signal revision

Нужна для:

- traceability;
- avoiding mismatch between signal/risk/explanation bundles;
- audit / later review.

## 8. Signal schema policy

### 8.1 Базовое правило

`Signal summary` и `expanded explanation` обязаны быть разделены.

Это нужно, чтобы:

- ranked list оставался компактным;
- explainability не пряталась в сыром blob;
- UI и audit могли работать с разными слоями сигнала.

### 8.2 Обязательные семантические элементы

Каждый signal summary обязан выражать:

- направление (`long`, `short`, `hold` не обязателен как ranked actionable signal)
- confidence
- entry zone / entry summary
- target / expected move
- stop / invalidation summary
- current state
- freshness/update context

### 8.3 Что запрещено

Нельзя:

- отдавать rank без объяснимой причины существования сигнала;
- хранить только красивый prose-текст без structured fields;
- выдавать high-confidence signal без risk-visible semantics.

## 9. Ranking logic `v1`

### 9.1 Основные ranking inputs

Ranking обязан учитывать минимум:

- market structure quality
- forecast contribution
- external context alignment
- liquidity/volume/volatility suitability
- confidence level
- risk posture
- freshness quality
- conflict penalty

### 9.2 Каноническая логика

`v1` не требует сверхсложной математики, но требует ясной логики:

- сильный setup без acceptable risk не должен просто побеждать ranking;
- сигнал с сильным конфликтом не должен оставаться топ-кандидатом как ни в чём не бывало;
- stale или degraded inputs обязаны понижать ranking или блокировать signal.

### 9.3 Связь с shortlist

- shortlist определяет candidate universe;
- ranking упорядочивает actionable signals внутри этого universe;
- shortlist и ranking не являются одной и той же сущностью.

## 10. Confidence model

### 10.1 Базовое правило

Confidence — это не “насколько красиво модель написала explanation”.

Confidence обязан быть функцией минимум от:

- market setup quality;
- agreement/conflict между ролями;
- freshness/data quality;
- current risk posture;
- degraded/fallback state.

### 10.2 Confidence downgrade triggers

Confidence должен снижаться минимум при:

- role conflict;
- stale signal inputs;
- stale market context;
- fallback-only reasoning path;
- reduced provider availability;
- repeated weakening conditions.

### 10.3 Что запрещено

Нельзя:

- сохранять прежний confidence при degraded fallback;
- оставлять high confidence при explicit conflict;
- маскировать low-data-quality под “уверенный сигнал”.

## 11. Signal lifecycle policy

### 11.1 Основные состояния

Минимальные states:

- `active`
- `weakening`
- `invalidated`
- `expired`
- `absent`

### 11.2 `active`

Сигнал считается `active`, если:

- setup ещё валиден;
- risk engine не перевёл его в blocked state;
- data freshness достаточна;
- conflicts не убили confidence below actionable threshold.

### 11.3 `weakening`

Сигнал должен перейти в `weakening`, если:

- исходный setup ещё не invalidated;
- но confidence/risk/freshness/context quality заметно ухудшились;
- actionability понижается, но не всегда падает в ноль.

### 11.4 `invalidated`

Сигнал должен перейти в `invalidated`, если:

- нарушен critical setup condition;
- market data stale beyond hard threshold;
- risk trigger блокирует сигнал;
- signal/risk bundle потерял целостность;
- severe conflict делает signal non-actionable.

### 11.5 `expired`

Сигнал должен истекать, если:

- TTL окна прошёл;
- signal больше не релевантен текущей intraday ситуации;
- он не должен продолжать жить как будто сейчас ещё актуален.

## 12. Risk-control policy

### 12.1 Основные risk triggers

Минимально учитывать:

- stale data
- market overheating
- model conflict
- low data quality
- repeated poor signals
- API/provider degradation
- excessive volatility
- defensive session posture

### 12.2 Response actions

Risk engine обязан поддерживать минимум:

- `warning_only`
- `lower_confidence`
- `block_signal`
- `switch_to_defensive`

### 12.3 Actionability semantics

UI-facing actionability:

- `normal`
- `reduced`
- `blocked`

Это должно позволять:

- сохранить видимость сигнала при ограничении;
- но не делать вид, что оператору разрешено действовать как обычно.

## 13. Strategy mode switching semantics

### 13.1 Режимы `v1`

- `Trend-following`
- `Momentum`
- `Defensive`

### 13.2 Когда система может предложить switch

Минимально при:

- regime shift;
- repeated signal degradation;
- conflict-heavy environment;
- overheating / excessive volatility;
- defensive risk posture.

### 13.3 Что запрещено

Нельзя:

- silently менять strategy mode;
- маскировать strategy change как обычный signal update;
- переключать режим без operator-visible reason.

## 14. UI-facing data contracts после `E6`

### 14.1 Ranked signal card

Минимальные поля:

- `signal_id`
- `pair`
- `direction`
- `state`
- `confidence`
- `timeframe`
- `entry_summary`
- `target_summary`
- `stop_summary`
- `rank`
- `last_updated_at`
- `actionability`

### 14.2 Expanded signal explanation

Минимальные поля:

- `signal_id`
- `headline_explanation`
- `why_now`
- `technical_confluence[]`
- `contextual_factors[]`
- `confidence_notes`
- `risk_notes[]`
- `conflict_summary | null`

### 14.3 Risk action contract

Минимальные поля:

- `risk_trigger_id`
- `trigger_type`
- `severity`
- `response_action`
- `summary`
- `affects_signal_ids[]`

### 14.4 Strategy proposal contract

Минимальные поля:

- `proposal_id`
- `current_mode`
- `proposed_mode`
- `reason_summary`
- `confidence_impact`
- `requires_confirmation`

## 15. Transport and interaction expectations

### 15.1 HTTP snapshot examples

- `GET /signals`
- `GET /signals/{signalId}`
- `GET /signals/ranking`
- `GET /risk/active`
- `GET /strategy/proposals`

### 15.2 HTTP command examples

- `POST /signals/{signalId}/acknowledge`
- `POST /strategy/proposals/{proposalId}/accept`
- `POST /strategy/proposals/{proposalId}/reject`

### 15.3 SSE stream examples

- `GET /signals/stream`
- `GET /risk/events/stream`
- `GET /strategy/events/stream`

### 15.4 Что нельзя

Нельзя:

- вычислять ranking прямо в браузере;
- держать signal lifecycle только как UI-состояние без backend truth;
- публиковать raw exchange noise как browser-facing signal stream.

## 16. Failure modes, которые `E6` обязан учитывать

### A. Signal/risk mismatch

Если signal summary и risk snapshot относятся к разным revision/version:

- система должна предпочесть целостность;
- actionability обязана снижаться или блокироваться;
- mismatch не должен silently склеиваться.

### B. Conflict-heavy environment

Если конфликты системные:

- confidence overall должен снижаться;
- ranking должен учитывать conflict penalty;
- UI обязан видеть structured conflict notes.

### C. Stale data

Если stale market data:

- signal может быть blocked или invalidated;
- normal trading flow не должен продолжаться как обычно.

Если stale context data:

- degraded/reduced mode допустим;
- но это должно быть явно видно.

### D. Repeated poor signals

Если система накопила серию слабых/плохих сигналов:

- risk engine может усилить defensive bias;
- confidence thresholds должны ужесточаться;
- proposal на strategy mode switch может стать обязательным.

### E. Forecast input absent

Система обязана:

- явно показать reduced completeness;
- не маскировать отсутствие forecast contribution.

## 17. Acceptance criteria

Эпик `E6` считается готовым, если выполняются все условия:

1. Signal summary и expanded explanation логически разделены.
2. Ranking учитывает не только alpha-like strength, но и risk/conflict/freshness.
3. `active`, `weakening`, `invalidated`, `expired`, `absent` имеют явную семантику.
4. Risk triggers могут warning/reduce/block/defensive, а не только “подсвечивать красным”.
5. Confidence visibly снижается при conflict, stale data и fallback limitations.
6. Strategy mode switch остаётся operator-visible proposal.
7. UI-facing contracts позволяют `E3` честно показывать signal и risk layers.

## 18. Обязательные проверки для `E6`

- проверить signal schema coverage;
- проверить ranking behavior при high risk;
- проверить weakening transition;
- проверить invalidation transition;
- проверить TTL/expiry semantics;
- проверить stale-data blocking behavior;
- проверить conflict penalty in confidence and ranking;
- проверить strategy proposal visibility;
- проверить mismatch protection между signal/risk revisions.

## 19. Dependencies и границы с соседними эпиками

### 19.1 Зависимости

`E6` зависит минимум от:

- `E3` workspace contracts
- `E5` AI orchestration semantics

### 19.2 Граница с `E5`

`E5` отвечает за role model, provider abstraction и orchestration.

`E6` не должен:

- переопределять provider policy;
- превращаться в model registry screen;
- смешивать AI assignment logic с signal lifecycle policy.

### 19.3 Граница с `E7`

`E7` отвечает за preflight, briefing, active session, pause и session discipline.

`E6` даёт сигналы и risk semantics, но не определяет всю session choreography.

### 19.4 Граница с `E8`

`E8` отвечает за demo trading linking и result tracking.

`E6` не должен описывать trade execution workflow.

## 20. Артефакты, которые должны следовать после `E6 build-spec`

Сразу после `E6` логично подготовить:

- `E6 implementation plan — Signal Lifecycle, Ranking And Risk-Control`
- `E7 build-spec — Session Lifecycle`
- `E8 build-spec — Demo Trading Integration And Result Tracking`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E6`.
