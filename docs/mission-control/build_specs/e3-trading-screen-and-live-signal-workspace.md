# E3 Build Spec — Trading Screen And Live Signal Workspace

Дата: 2026-04-01
Эпик: `E3`
Статус: build-spec draft v2
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/runbooks/runbook-001-preflight-degraded-mode.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/session-summary-2026-04-01.md`
- UI baseline: `/home/emma/Downloads/clay-mission-control_ui_v15`

## 1. Цель эпика

Собрать основной рабочий экран `CLAY Mission Control`, который:

- даёт оператору один главный фокус внимания;
- показывает live-сигналы и shortlist/monitoring context;
- объясняет, почему система считает текущий setup рабочим или нерабочим;
- показывает risk posture и внешний контекст;
- остаётся analyst-first интерфейсом;
- не превращается во второй `Binance terminal`.

`E3` строит не “биржевой экран с красивыми кнопками”, а центральное decision-support workspace, в котором оператор видит:

- какая пара сейчас в фокусе;
- есть ли активный сигнал;
- насколько сигнал доверенный;
- что происходит с риском;
- что изменилось во внешнем контексте;
- можно ли действовать, продолжать мониторинг или нужно уходить в defensive/degraded behavior.

## 2. Входит в scope

- `Trading Workspace` как главный боевой экран
- `single focused pair` как канонический baseline `v1`
- `Active Signals` zone
- `Monitoring Pool` zone
- `focused pair header`
- `Analyst Situation Map`
- `AI Reasoning & Context`
- `Risk Assessment`
- `News & Sentiment`
- `freshness / update timer`
- `Preflight / Briefing -> Trading Workspace` handoff
- явные UI states:
  - `active`
  - `no_active_signal`
  - `degraded`
  - `defensive`
  - `paused`
  - `invalidated`
- UI-facing data contracts для live updates и snapshots
- operator actions, допустимые в рамках ручной торговли

## 3. Не входит в scope

- `Control Center` как отдельный операторский пульт
- полный signal engine internals
- полноценный signal ranking algorithm
- full `Chief Agent` orchestration logic
- full session lifecycle orchestration вне handoff в workspace
- auto-execution
- order form
- exchange-style full order book terminal
- futures / leveraged execution
- backtesting / replay
- full audit/review layer

> Уточнение (S-EXEC-3c): явный, операторски подтверждаемый override execution-режима ВХОДИТ в scope E3 как operator action. Out of scope остаётся только silent/auto-override и ввод ордера (п. 69–72).

## 4. Архитектурные допущения

- `CLAY` = `local-first`, `single-user`, `web-first`
- пользователь работает минимум с двумя окнами:
  - `Binance` для реального chart/order/execution
  - `CLAY` для аналитики и контроля
- `v1` рынок: `Binance Spot only`
- рабочий shortlist `v1`: `3–5` пар
- transport policy для browser UI:
  - `HTTP/JSON` для snapshots и actions
  - `SSE` для live updates
- browser UI не получает raw exchange streams напрямую
- `Trading Workspace` живёт поверх prepared views и system events, а не поверх raw market feed
- baseline UI layout зафиксирован по `v15`

## 5. Главный результат эпика

После завершения `E3` разработчик должен получить:

- канонический главный рабочий экран CLAY;
- зафиксированную структуру `focused pair + context around it`;
- ясную модель связи между `focusPair`, `selectedSignal`, `shortlist` и `Monitoring Pool`;
- описанные состояния экрана при наличии/отсутствии сигнала;
- понятный контракт live updates для UI;
- acceptance criteria, по которым можно проверить, что экран analyst-first, а не exchange clone.

## 6.1 Главные пользовательские сценарии

`E3` должен поддерживать минимум следующие рабочие сценарии:

### A. Вход в сессию после briefing

Пользователь:

- проходит `Preflight / Briefing`;
- получает `primary focus pair` и `backup pairs`;
- попадает сразу в готовый `Trading Workspace`.

Система:

- открывает нужную пару;
- показывает signal/reasoning/risk/context без повторной ручной сборки экрана;
- сохраняет backup pairs как monitoring context.

### B. Переключение между активными сигналами

Пользователь:

- видит несколько live signal cards;
- выбирает другую карточку.

Система:

- синхронно меняет focused pair;
- меняет situation map;
- меняет reasoning/risk/news context;
- не оставляет stale данные от предыдущего setup.

### C. Переход в monitoring mode для пары без сигнала

Пользователь:

- выбирает пару из `Monitoring Pool`, у которой нет active signal.

Система:

- переводит экран в `no_active_signal`;
- показывает monitoring context;
- не делает вид, что новая пара уже имеет actionable setup.

### D. Работа во время ограничений

Пользователь:

- получает degraded/paused/defensive condition;
- должен быстро понять, можно ли продолжать работу.

Система:

- явно объясняет ограничение;
- не скрывает снижение качества сигнала;
- не маскирует ограниченный режим под normal mode.

## 7. Логические компоненты E3

### 6.1 Trading Workspace Shell

Экран-оболочка, которая:

- получает focused pair;
- получает signal context;
- получает runtime/session state;
- собирает основные decision-support панели;
- не содержит торговой формы исполнения.

### 6.2 Active Signals Panel

Панель высокоприоритетных live-событий.

Отвечает за:

- показ активных сигналов по shortlist;
- выбор сигнала пользователем;
- передачу фокуса в центральную рабочую область;
- явное отображение `active / weakening / invalidated` состояния карточек.

### 6.3 Monitoring Pool Panel

Панель расширенного контекста по shortlist/watchlist.

Отвечает за:

- мониторинг пар без обязательного наличия активного сигнала;
- показ `backup / focus / watch` роли;
- показ volatility/change/freshness context;
- смену `focusPair`, даже если для пары ещё нет сигнала.

### 6.4 Focused Pair Context Header

Верхний блок текущей пары.

Отвечает за:

- показывать текущую пару;
- показывать направление bias;
- показывать текущий state focused setup;
- показывать update/freshness context;
- показывать secondary external jump в `Binance`.

### 6.5 Analyst Situation Map

Главная центральная decision-support визуализация.

Отвечает за:

- показать entry zone;
- показать target / stop / invalidation;
- показать predicted path / directional bias;
- показать краткий price context;
- остаться analyst-style картой ситуации, а не chart terminal.

### 6.6 AI Reasoning & Context

Блок объяснения сигнала.

Отвечает за:

- показать short explanation;
- показать why-now context;
- показать technical confluence;
- показать sentiment / contextual notes;
- явно менять содержание при `no_active_signal`.

### 6.7 Risk Assessment

Блок риск-контекста.

Отвечает за:

- показать risk posture;
- показать sizing recommendation;
- показать limit/defensive implications;
- в degraded/paused/invalidated состояниях менять разрешённость действий.

### 6.8 News & Sentiment

Внешний контекстный блок.

Отвечает за:

- показывать краткие новости;
- показывать market-moving context;
- быть вспомогательным, а не доминирующим блоком.

## 8. Граница между CLAY и Binance

### 8.1 Что остаётся в CLAY

В `Trading Workspace` остаются:

- сигнал;
- reasoning;
- risk;
- context;
- monitoring;
- session-aware operator guidance.

### 8.2 Что остаётся вне CLAY

В `Binance` остаются:

- полный биржевой chart;
- форма ручного ввода ордера;
- full order book / стакан;
- реальное исполнение сделки.

### 8.3 Следствие для дизайна E3

`Trading Workspace` не должен:

- визуально имитировать полноценный exchange terminal;
- дублировать core execution widgets;
- делать `Execute on Binance` главным смыслом экрана.

`Execute on Binance` допустим только как secondary external jump.

## 9. Канонический layout `v1`

### 7.1 Базовый режим

Канонический baseline `v1`:

- **одна выбранная пара в центре**

Это означает:

- один dominant focus region;
- shortlist и monitoring живут рядом как context;
- screen hierarchy подчинена главной паре, а не распределена равномерно между всеми парами.

### 7.2 Secondary / optional mode

Допускается optional `hybrid/radar mode`, где:

- одна пара всё равно остаётся dominant;
- остальные пары видны как компактный radar/context strip.

Но это не должен быть основной режим мышления интерфейса.

### 7.3 Обязательные зоны экрана

На одном рабочем экране должны быть выражены:

- `Active Signals`
- `Monitoring Pool`
- `Focused Pair Header`
- `Analyst Situation Map`
- `AI Reasoning & Context`
- `Risk Assessment`
- `News & Sentiment`
- `Update / Freshness Context`

## 10. Pair focus и signal focus workflow

### 8.1 Канонические сущности

Экран опирается минимум на четыре сущности:

- `focusPair`
- `selectedSignal`
- `shortlist`
- `monitoringPool`

### 8.2 Правила синхронизации

#### A. Если пользователь выбирает active signal

Система обязана синхронно обновить:

- `focusPair`
- `selectedSignal`
- header
- situation map
- reasoning
- risk
- news/sentiment context

#### B. Если пользователь выбирает пару из `Monitoring Pool`

Система обязана:

- сменить `focusPair`, даже если у пары нет сигнала;
- не тянуть stale analytics от предыдущей пары;
- перевести workspace либо в signal mode, либо в `no_active_signal mode`.

#### C. Если `focusPair` задаётся после `Briefing`

Система обязана:

- открыть workspace на primary focus pair;
- отметить backup pairs в shortlist/monitoring;
- не требовать повторного ручного выбора пары сразу после старта.

## 11. Ranked signals UX

### 9.1 Карточка сигнала обязана содержать

Минимальный набор:

- `pair`
- `direction`
- `state`
- `confidence`
- `timeframe`
- `entry zone` или краткий entry summary
- `target` или expected move
- `stop` или invalidation summary
- `last update`
- optional `rank`, если ranking уже доступен upstream

### 9.2 Signal states

Карточка сигнала обязана явно отличать:

- `active`
- `weakening`
- `invalidated`

Нельзя оставлять weakening/invalidation только в глубине expanded view.

## 12. Слои состояния: runtime vs workspace vs signal

Чтобы не смешать разные типы состояния в один комок уровня “всё enum, а дальше бог разберёт”, `E3` обязан разделять три слоя:

### 12.1 Runtime state

Этот слой приходит из `E1` runtime model и остаётся каноническим системным состоянием:

- `background_monitoring`
- `pre_session`
- `active_session`
- `paused`
- `review`
- `degraded`

`Trading Workspace` не должен придумывать свой независимый runtime state machine.

### 12.2 Workspace posture

Это локальный рабочий режим экрана внутри допустимого runtime state.

Минимальные posture-состояния:

- `normal`
- `monitoring_only`
- `defensive`
- `restricted_by_degraded`

`Defensive` в рамках `E3` трактуется как workspace/risk posture, а не как отдельный канонический runtime state поверх `E1`.

### 12.3 Signal state

Это состояние конкретного сигнала/сетапа:

- `active`
- `weakening`
- `invalidated`
- `absent` (`no_active_signal` для текущей пары)

`Invalidated` в `E3` трактуется как состояние focused setup/signal, а не как системный runtime-state всей панели.

## 13. `No active signal` behavior

### 10.1 Когда возникает

Состояние включается, если:

- `focusPair` выбрана;
- но для неё сейчас нет active signal.

### 10.2 Что должен видеть пользователь

Экран должен показывать:

- что пара находится в monitoring mode;
- что signal generation ещё не подтвердила setup;
- neutral/non-actionable risk posture;
- краткий monitoring context вместо stale explanation.

### 10.3 Что запрещено

Нельзя:

- показывать reasoning от предыдущей пары;
- оставлять старый target/stop/invalidation как будто они относятся к новой паре;
- визуально делать вид, что экран “сломался”.

## 14. Поведение экрана по состояниям

### 14.1 Runtime: `active_session`

Нормальный рабочий режим.

Экран показывает:

- active signal, если он есть;
- monitoring mode, если сигнала нет;
- все основные decision-support панели без скрытых ограничений.

### 14.2 Runtime: `degraded`

Экран обязан:

- явно показать degraded banner/state;
- объяснить, что именно ограничено;
- понизить видимую уверенность системы;
- не выдавать видимость normal full-confidence mode.

### 14.3 Workspace posture: `defensive`

Экран обязан:

- показать defensive/risk-reduction posture;
- усилить риск-блок как primary warning layer;
- дать понять, что сигналы и рекомендации работают в более жёстком safety режиме.

### 14.4 Runtime: `paused`

Экран обязан:

- показывать, что active streams поставлены на паузу;
- явно блокировать нормальный action flow;
- сохранить контекст, но не делать вид, что live session продолжается.

### 14.5 Signal state: `invalidated`

Экран обязан:

- явно показать, что текущий setup больше не рабочий;
- сохранить причину invalidation;
- убрать ambiguity между “сигнал ослаб” и “сигнал отменён”.

## 15. `Preflight / Briefing -> Trading Workspace` handoff

### 12.1 Обязательный результат briefing

`Briefing` должен выдавать минимум:

- `primary_focus_pair`
- `backup_pairs[]`
- `active_strategy`
- `active_model_context`
- краткий session posture

### 12.2 При входе в workspace

Система обязана:

- открыть `primary_focus_pair`;
- пометить backup candidates;
- показать рабочее состояние без повторной ручной сборки контекста оператором.

## 16. UI-facing data contracts после `E3`

### 13.1 Focus pair contract

Минимальные поля:

- `symbol`
- `display_name`
- `is_focused`
- `role` (`primary`, `backup`, `monitoring`)
- `last_price`
- `pct_change_24h`
- `volatility`
- `last_scan_at`
- `active_signal_id | null`
- `focus_source` (`briefing`, `signal_click`, `monitoring_click`, `system_recommendation`)

### 13.2 Signal summary contract

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

### 13.3 Expanded reasoning contract

Минимальные поля:

- `signal_id`
- `headline_explanation`
- `why_now`
- `technical_confluence[]`
- `contextual_factors[]`
- `confidence_notes`

### 13.4 Risk snapshot contract

Минимальные поля:

- `pair`
- `risk_posture`
- `max_drawdown_estimate`
- `position_size_hint`
- `risk_reward_hint`
- `defensive_constraints[]`
- `actionability` (`normal`, `reduced`, `blocked`)

### 13.5 News / sentiment contract

Минимальные поля:

- `item_id`
- `source`
- `published_at`
- `title`
- `relevance`
- `directional_hint`
- `affected_pairs[]`

### 13.6 Freshness / live metadata

Минимальные поля:

- `last_signal_refresh_at`
- `last_market_refresh_at`
- `is_signal_stale`
- `is_market_context_stale`
- `next_update_eta`

### 16.7 Workspace state contract

Минимальные поля:

- `runtime_state`
- `workspace_posture`
- `focused_signal_state`
- `can_open_binance`
- `can_log_decision`
- `blocking_reason | null`
- `execution_override_expires_at | null` — ISO 8601 UTC, момент истечения override; `null` означает отсутствие активного override (см. ADR-025, ADR-001 addendum 2026-06-28).
- `server_time` — ISO 8601 UTC, серверное время на момент сборки snapshot; клиент использует для компенсации часового дрейфа при расчёте countdown.

### 16.8 Operator action: execution override (header badge + modal)

- Override-badge-кнопка в command-strip header trading-workspace видна при
  `execution_override_state ∈ {pending, confirmed}` (НЕ в workspace-state-banner —
  тот компонент orphan и не монтируется).
- `confirmed`: бейдж показывает countdown `mm:ss` от `execution_override_expires_at`
  с поправкой на `server_time` offset; тик 1 с; на нуле — refetch (без локального снятия).
- Клик открывает модалку: `pending` → Confirm/Revoke; `confirmed` → countdown + Revoke.
- Действия → `POST /workspace/trading/override/{confirm,revoke}`, затем refetch.
  Confirm активирует override на TTL = 1 час (backend, ADR-025 Override expiry).
- Явный, операторски подтверждаемый override (не silent override; п. 69–72 out of scope).
- A11y: role="dialog", aria-modal, focus trap, ESC + backdrop на закрытие, возврат фокуса.

## 17. Data flow через экран

### 17.1 Upstream dependencies

`E3` читает результаты предыдущих эпиков/слоёв:

- runtime state из `E1`
- market/context freshness из `E2`
- shortlist inputs из `E2`
- signal summaries из downstream signal layer
- reasoning/risk/context bundle из AI/signal pipeline

### 17.2 Downstream consumers

Сам `E3` не должен быть последней остановкой данных.

Он должен отдавать operator-originated действия дальше в:

- audit / feedback layer
- session review layer
- future decision logging / trade-result tracking

### 17.3 Что E3 не вычисляет сам

`Trading Workspace` не должен сам:

- ранжировать рынок;
- принимать финальное агентное решение;
- вычислять signal confidence;
- строить ingest/freshness;
- исполнять сделку.

Он получает подготовленный decision-support context и показывает его оператору.

## 18. Transport contract для `E3`

### 18.1 Snapshot path

Через `HTTP/JSON`:

- workspace bootstrap snapshot
- current shortlist / monitoring pool
- current focused pair context
- current active signals list
- latest reasoning / risk / news bundle

### 18.2 Live update path

Через `SSE`:

- signal state changes
- ranking changes
- focus-relevant data refreshes
- degraded / defensive / invalidated events
- freshness warnings

### 18.3 Что нельзя

Нельзя:

- тянуть raw exchange stream прямо в browser UI;
- строить экран вокруг direct exchange socket semantics;
- смешивать transport policies без отдельного оправдания.

## 19. HTTP / SSE surface expectations

### 19.1 HTTP snapshot examples

Канонические snapshot-style операции после `E3`:

- `GET /workspace/trading`
- `GET /workspace/trading/focus`
- `GET /workspace/trading/signals`
- `GET /workspace/trading/monitoring-pool`

### 19.2 HTTP command examples

Канонические operator actions:

- `POST /workspace/trading/focus`
- `POST /workspace/trading/layout-mode`
- `POST /workspace/trading/log-observation`
- `POST /workspace/trading/open-external-context`

### 19.3 SSE stream examples

- `GET /workspace/trading/stream`
- `GET /signals/stream`
- `GET /runtime/events/stream`

Эти примеры фиксируют класс контракта, а не прибивают окончательные path names к полу.

## 20. Operator actions в рамках `E3`

Допустимые действия:

- выбрать active signal
- выбрать monitored pair
- переключить layout mode (`single` / `hybrid`)
- открыть external execution context (`Binance`)
- записать observation / decision note
- увидеть предупреждение / limitation state

Не входят в `E3`:

- ввод ордера;
- hidden auto-execution;
- silent system override критичных safety ограничений.

## 21. Failure modes, которые `E3` обязан учитывать

### A. Нет активного сигнала для выбранной пары

Экран переходит в monitoring mode.

### B. Stale signal data

Экран обязан понизить доверие и явно показать stale status.

### C. Stale market context

Экран обязан ограничить actionability и показать freshness problem.

### D. Runtime перешёл в `degraded`

Экран обязан поменять state treatment и объяснить ограничение.

### E. Briefing handoff incomplete

Экран не должен silently показывать “какую-то” пару как будто она primary focus без ясного источника.

### F. Monitoring Pool item stale

Если monitoring item stale:

- это должно быть видно;
- stale monitoring pair не должна silently выглядеть как свежий live candidate.

### G. Signal/risk mismatch

Если signal summary и risk snapshot относятся к разным revision/version:

- UI должен предпочесть целостность и показать warning/reduced actionability,
- а не склеивать несовместимые куски как патченный initramfs после плохого апдейта.

## 22. Acceptance criteria

Эпик `E3` считается готовым, если выполняются все условия:

- `Trading Workspace` строится вокруг одной главной пары;
- shortlist/context не конкурирует по визуальному весу с focused pair;
- экран не выглядит как второй `Binance`;
- выбор active signal синхронно обновляет весь рабочий контекст;
- выбор monitored pair без сигнала корректно переводит экран в `no_active_signal`;
- `degraded`, `defensive`, `paused`, `invalidated` имеют явную и различимую UI-семантику;
- `Briefing` корректно передаёт initial focus в workspace;
- live updates проектируются как `HTTP + SSE`, а не как raw exchange UI stream;
- risk/explanation/context остаются первичными по отношению к terminal-like mechanics.

## 23. Обязательные проверки для `E3`

- проверить bootstrap snapshot экрана;
- проверить live update сигнала через event stream;
- проверить переключение `focusPair` при выборе active signal;
- проверить переключение `focusPair` при выборе monitoring pair без сигнала;
- проверить `no active signal` state;
- проверить `degraded`, `defensive`, `paused`, `invalidated`;
- проверить handoff из `Briefing`;
- проверить, что `Execute on Binance` остаётся secondary action;
- проверить, что chart area остаётся analyst-style situation map.

## 24. Dependencies и границы с соседними эпиками

### 24.1 Зависимости

`E3` зависит минимум от:

- `E1` runtime state/control plane
- `E2` ingestion/storage/freshness foundation

### 24.2 Граница с `E4`

`E4` отвечает за операторский центр управления системой.

`E3` не должен пытаться стать:

- пультом рестартов сервисов;
- dashboard health orchestration;
- конфиг-центром всей системы.

### 24.3 Граница с `E6`

`E6` отвечает за signal schema, ranking и lifecycle internals.

`E3` потребляет их как UI-facing contract, но не определяет final ranking logic.

### 24.4 Граница с `E7`

`E7` отвечает за полный session lifecycle.

`E3` фиксирует только handoff в workspace и поведение экрана внутри сессии.

## 25. Артефакты, которые должны следовать после `E3 build-spec`

Сразу после `E3` логично подготовить:

- `E4 build-spec — Control Center And Runtime Operations`
- `E6 build-spec — Signal Lifecycle, Ranking And Risk-Control`
- `E7 build-spec — Session Lifecycle`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E3`.
