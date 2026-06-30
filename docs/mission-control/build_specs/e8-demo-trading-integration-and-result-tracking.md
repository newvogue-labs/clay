> **STATUS: HISTORICAL PLANNING (заморожен).** Документ относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).

# E8 Build Spec — Demo Trading Integration And Result Tracking

Дата: 2026-04-15
Эпик: `E8`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e6-signal-lifecycle-ranking-and-risk-control.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e7-session-lifecycle-preflight-briefing-active-mode-pause.md`

## 1. Цель эпика

Собрать `demo trading integration` для `CLAY Mission Control`, который:

- превращает demo-stage в обязательную и измеримую фазу обкатки;
- связывает `signal -> operator decision -> demo trade -> result` в одну прослеживаемую цепочку;
- читает результаты из внешнего торгового контура в `read-only` режиме;
- позволяет честно увидеть, был ли сигнал исполнен, пропущен, исполнен поздно или исполнен не по сценарию;
- формирует основу для допуска к осторожному `live`-этапу только после накопления валидной demo-истории.

`E8` нужен не для того, чтобы “бот как-нибудь поторговал на минималках”, а для того, чтобы ранний `v1` перестал жить в мире красивых объяснений без проверки об реальную demo-практику. Иначе мы получим очень умный терминал, который стабильно побеждает только в собственной голове 😼

## 2. Входит в scope

- demo/test trading workflow policy
- manual execution with platform-side action by operator
- read-only result ingestion from demo trading account / export layer
- canonical linkage between signal, operator decision, and observed demo trade
- result states for executed / missed / late / mismatched trades
- demo-session and trade outcome tracking
- demo-stage success criteria for cautious `live` admission
- UI-facing contracts for trade/result visibility and review handoff

## 3. Не входит в scope

- hidden or automatic order placement
- live trading execution
- futures / leverage workflow
- exchange-agnostic broker abstraction for multiple venues
- full session review analytics layer
- tax/accounting/reporting workflow
- portfolio management suite

## 4. Архитектурные допущения

- `v1` остаётся `Binance Spot only`
- пользователь вручную исполняет сделки на стороне Binance demo/test account
- `CLAY Mission Control` в `E8` не отправляет торговые ордера
- система читает результаты в `read-only` режиме через допустимый API/export ingest pathway
- signal/risk semantics приходят из `E6`, session discipline из `E7`
- storage baseline для trade/result references остаётся в `PostgreSQL + TimescaleDB` согласно `ADR-004`
- browser-facing state и updates продолжают идти через `HTTP + SSE`

## 5. Главный результат эпика

После завершения `E8` разработчик должен получить:

- канонический `demo trading workflow v1`;
- понятную result-linking модель для сигналов и demo-сделок;
- чёткие статусы исполнения и расхождения с рекомендацией;
- минимальный набор success criteria для допуска к следующей стадии;
- acceptance criteria, по которым можно проверить, что система валидирует себя на demo-истории, а не на фантазии.

## 6. Главные пользовательские сценарии

### A. Нормальное исполнение по сигналу

Пользователь:

- получает сигнал;
- вручную открывает сделку в demo account;
- система позже считывает факт сделки;
- связывает её с сигналом и session context;
- показывает результат в review-friendly форме.

### B. Сигнал был пропущен

Пользователь:

- видит сигнал;
- не входит в сделку.

Система обязана:

- зафиксировать отсутствие исполнения;
- не придумывать trade-link задним числом;
- сохранить это как валидный outcome, а не как “ну ничего не произошло”.

### C. Вход с опозданием

Пользователь:

- входит позже оптимального окна;
- сделка всё ещё относится к тому же сетапу, но с отклонением по времени/цене.

Система обязана:

- отметить `late execution`;
- не смешивать такой outcome с clean execution;
- сохранить разницу между “сигнал плохой” и “исполнение позднее”.

### D. Вход не по тому сигналу

Пользователь:

- входит в другую пару;
- входит в ту же пару, но в противоположном контексте;
- или меняет параметры так, что связь с сигналом становится сомнительной.

Система обязана:

- показать mismatch;
- не засчитывать такую сделку как нормальное подтверждение сигнала;
- сохранить причину расхождения.

## 7. Канонические сущности E8

### 7.1 Demo trade candidate

Наблюдаемая запись из внешнего demo-контура.

Минимальные поля:

- `demo_trade_id`
- `source_account_id`
- `exchange`
- `market_type`
- `pair`
- `side`
- `executed_at`
- `entry_price`
- `size`
- `status`

### 7.2 Signal-trade link

Сущность, которая связывает сигнал и наблюдаемую сделку.

Минимальные поля:

- `link_id`
- `signal_id`
- `session_id`
- `demo_trade_id | null`
- `link_status`
- `match_confidence`
- `link_reason`
- `operator_decision_id | null`

### 7.3 Demo outcome record

Operator-facing сущность для результата.

Минимальные поля:

- `outcome_id`
- `signal_id`
- `session_id`
- `pair`
- `outcome_status`
- `executed_at | null`
- `entry_delta_summary | null`
- `exit_delta_summary | null`
- `pnl_value | null`
- `pnl_percent | null`
- `result_notes[]`

### 7.4 Demo stage summary

Сущность для допуска к следующей стадии.

Минимальные поля:

- `session_count`
- `qualified_session_count`
- `long_session_count`
- `executed_trade_count`
- `missed_signal_count`
- `mismatch_count`
- `stable_profit_flag`
- `major_drawdown_flag`
- `critical_technical_failure_flag`
- `cautious_live_ready`

## 8. Demo workflow policy

### 8.1 Базовый принцип

`E8` поддерживает только следующий `v1` workflow:

1. `CLAY` показывает сигнал и session context.
2. Пользователь сама принимает решение.
3. Пользователь вручную исполняет или не исполняет сделку в demo/test environment.
4. `CLAY` позже читает observed results в `read-only`.
5. Система связывает observed trade с сигналом и session.
6. Outcome попадает в tracking и далее в review pipeline.

### 8.2 Что обязательно

- решение пользователя остаётся явным;
- факт сделки должен приходить из наблюдаемого источника, а не из “кажется, мы бы вошли”;
- trade/result ingest обязан быть отделён от signal generation;
- demo result не должен silently менять signal history задним числом.

### 8.3 Что запрещено

Нельзя:

- отправлять ордера из `CLAY` в рамках `E8`;
- прикидываться auto-trading слоем под видом “удобной интеграции”;
- считать demo outcome валидным, если нет traceable связи с session/signal context.

## 9. Read-only integration policy

### 9.1 Допустимые способы чтения

Для `v1` допустимы:

- `read-only API` pull from demo account history;
- controlled import of exchange exports;
- periodic reconciliation job over observed demo results.

### 9.2 Обязательные свойства

- интеграция должна быть `read-only`;
- торговые credentials не должны давать права на order placement;
- каждое наблюдаемое trade event должно иметь source attribution;
- ingest должен быть идемпотентным и не дублировать одну и ту же сделку.

### 9.3 Что запрещено

Нельзя:

- смешивать read-only ingest с execution permissions;
- считать локально созданную запись “реальной сделкой” без внешнего источника;
- терять provenance imported trade/result record.

## 10. Signal / decision / trade linking policy

### 10.1 Зачем нужен link-layer

Без explicit linking система не сможет отличить:

- хороший сигнал без исполнения;
- плохой сигнал;
- позднее исполнение;
- чужую сделку, случайно похожую на нужную;
- техническую потерю данных.

### 10.2 Link inputs

При связывании должны учитываться минимум:

- `signal_id`
- `session_id`
- `pair`
- expected direction
- signal active window
- operator decision metadata
- observed `executed_at`
- observed side / entry price

### 10.3 Link status `v1`

Минимальные статусы:

- `matched`
- `missed`
- `late_matched`
- `mismatched`
- `unresolved`

### 10.4 Что запрещено

Нельзя:

- silently считать любую сделку по той же паре корректным match;
- связывать trade с сигналом без учёта времени и направления;
- стирать unresolved state только ради красивой статистики.

## 11. Outcome semantics

### 11.1 Минимальные outcome cases

Система обязана различать:

- сигнал исполнен в допустимом окне;
- сигнал исполнен поздно;
- сигнал не исполнен;
- исполнение не соответствует сигналу;
- результат ещё не может быть надёжно определён.

### 11.2 Почему это важно

`E8` измеряет не только качество сигнала, но и качество операторского взаимодействия с системой.

Поэтому outcome model не должен смешивать:

- плохой signal generation;
- плохой timing;
- operator hesitation;
- data reconciliation gaps;
- технический ingest failure.

### 11.3 PnL semantics

`v1` достаточно иметь:

- `pnl_value | null`
- `pnl_percent | null`
- coarse result label (`win`, `loss`, `flat`, `unknown`)

Но:

- PnL не является единственной метрикой качества;
- mismatch или late execution не должны прятаться за итоговым плюсом.

## 12. Demo-stage success criteria

### 12.1 Базовые критерии допуска

Для осторожного перехода к следующей стадии должны учитываться минимум:

- не менее `5` отдельных demo-сессий;
- среди них несколько длинных сессий около `7 часов`;
- стабильный плюс по серии;
- отсутствие крупных просадок;
- отсутствие критических технических сбоев.

### 12.2 Что значит `stable_profit_flag`

`Stable profit` в `v1` не должен означать одну удачную сессию на эйфории и кофеине.

Он обязан опираться на:

- серию сессий, а не на единичный трейд;
- отсутствие доминирования одной случайной сделки над остальными;
- отсутствие систематического скрытия miss/late/mismatch outcomes.

### 12.3 Что считать major drawdown

`Major drawdown` для `v1` должен быть определён как operator-visible порог, который:

- явно фиксируется в конфиге/policy;
- считается по demo-stage истории;
- блокирует premature optimism насчёт `live readiness`.

### 12.4 Что считать critical technical failure

Минимум:

- потеря связи signal-to-trade;
- потеря или дублирование imported trade records;
- неконсистентный session/result history;
- unsafe permission mix-up;
- критический сбой result reconciliation.

## 13. UI-facing contracts после `E8`

### 13.1 Demo trade card contract

Минимальные поля:

- `demo_trade_id`
- `pair`
- `side`
- `executed_at`
- `entry_price`
- `status`
- `source_label`

### 13.2 Signal-trade link contract

Минимальные поля:

- `signal_id`
- `session_id`
- `link_status`
- `demo_trade_id | null`
- `match_confidence`
- `link_reason`

### 13.3 Demo outcome contract

Минимальные поля:

- `outcome_id`
- `outcome_status`
- `result_label`
- `pnl_value | null`
- `pnl_percent | null`
- `late_execution_flag`
- `mismatch_flag`
- `notes[]`

### 13.4 Demo readiness summary contract

Минимальные поля:

- `session_count`
- `qualified_session_count`
- `long_session_count`
- `stable_profit_flag`
- `major_drawdown_flag`
- `critical_technical_failure_flag`
- `cautious_live_ready`
- `blocking_reasons[]`

## 14. Transport and interaction expectations

### 14.1 HTTP snapshot examples

- `GET /demo-trades/recent`
- `GET /demo-outcomes/recent`
- `GET /signals/{signalId}/demo-link`
- `GET /demo-stage/readiness`

### 14.2 HTTP command examples

- `POST /demo-results/reconcile`
- `POST /signals/{signalId}/demo-link/review`
- `POST /demo-outcomes/{outcomeId}/annotate`

### 14.3 SSE stream examples

- `GET /demo-results/stream`
- `GET /demo-stage/readiness/stream`

### 14.4 Что нельзя

Нельзя:

- строить demo-stage только как локальную таблицу без backend truth;
- подменять reconciliation живыми догадками UI;
- скрывать unresolved или mismatched outcomes из operator-facing слоя.

## 15. Failure modes, которые `E8` обязан учитывать

### A. Сделка есть, но link неочевиден

Система обязана:

- оставить `unresolved` или `mismatched` статус;
- показать причину сомнения;
- не натягивать match ради красивой статистики.

### B. Сигнал был, сделки не было

Система обязана:

- зафиксировать `missed`;
- не считать это техническим отсутствием данных без доказательств;
- сохранить trace для review.

### C. Сделка импортирована дважды

Система обязана:

- дедуплицировать ingest;
- сохранить source trace;
- не удваивать PnL и trade count.

### D. Permissions настроены unsafe

Система обязана:

- заблокировать integration activation;
- явно показать проблему;
- не работать в полу-unsafe режиме “ну вроде не нажмётся”.

### E. Read-only data stale

Система обязана:

- показать stale/result lag;
- не притворяться, что latest outcomes уже известны;
- не объявлять readiness на неполной базе.

## 16. Acceptance criteria

Эпик `E8` считается готовым, если выполняются все условия:

1. `Demo trading workflow` описан как manual execution + read-only result ingestion.
2. У системы есть канонический способ связать `signal`, `session`, `operator decision` и observed `demo trade`.
3. Outcome model различает `matched`, `missed`, `late`, `mismatched`, `unresolved`.
4. Система не требует auto-order placement и не скрывает, что execution ручной.
5. Demo-stage readiness summary умеет честно блокировать premature `live` optimism.
6. UI-facing contracts позволяют показать trade/result history и причины расхождений.
7. Failure modes вокруг stale data, duplicate trades, unresolved links и unsafe permissions описаны явно.

## 17. Обязательные проверки для `E8`

- проверить normal signal-to-demo-trade matching;
- проверить `missed` outcome;
- проверить `late_matched` outcome;
- проверить `mismatched` outcome;
- проверить `unresolved` case;
- проверить deduplication imported trade records;
- проверить stale result warning;
- проверить blocking readiness при critical technical failure;
- проверить, что system remains read-only и не описывает order placement.

## 18. Dependencies и границы с соседними эпиками

### 18.1 Зависимости

`E8` зависит минимум от:

- `E6` signal schema и risk semantics
- `E7` session lifecycle и admission discipline
- `ADR-004` storage baseline для sessions, signals и result references

### 18.2 Граница с `E7`

`E7` управляет session discipline.

`E8` не должен:

- переопределять session admission;
- заменять preflight / briefing logic;
- превращаться в runtime state manager.

### 18.3 Граница с `E9`

`E9` отвечает за audit trail, feedback и session review analytics.

`E8` готовит trade/result data и link semantics, но не финальную review-аналитику.

### 18.4 Граница с live stage

`E8` не означает live trading readiness по умолчанию.

Он только создаёт evidence layer, на котором можно принимать более осторожное решение.

## 19. Артефакты, которые должны следовать после `E8 build-spec`

Сразу после `E8` логично подготовить:

- `E8 implementation plan — Demo Trading Integration And Result Tracking`
- `E9 build-spec — Audit Trail, Feedback And Session Review`
- при необходимости отдельный runbook по `demo result reconciliation`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E8`.
