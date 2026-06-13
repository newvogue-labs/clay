# CLAY Mission Control v1 — Execution Backlog

Дата: 2026-03-30
Основа: `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
Статус: decomposition for implementation

## 1. Почему этот формат лучше жёсткого монолитного ТЗ

Для `CLAY Mission Control v1` лучше использовать не один бетонный документ “сделать всё”, а трехслойную схему:

1. `Engineering Blueprint`
   Главный документ с архитектурой, границами, режимами работы и общими решениями.

2. `Execution Backlog`
   Эпики, задачи и подзадачи, из которых реально собирается система.

3. `Per-Epic Build Spec`
   Короткая рабочая спецификация перед реализацией конкретного эпика: экраны, API, data contracts, acceptance criteria.

Почему это лучше:

- сохраняется манёвренность;
- не приходится переписывать целиком всё ТЗ при каждом уточнении;
- можно строить систему по частям;
- проще контролировать зависимости;
- проще подключать ИИ-агентов и разработчиков по отдельным кускам;
- меньше риск построить “идеально описанного монстра”, которого больно реализовывать.

## 2. Правила декомпозиции

### Epic

Крупный функциональный блок системы.

### Task

Конкретный результат внутри эпика.

### Subtask

Минимальная рабочая единица, после которой можно проверить результат.

### Done для задачи

Задача считается завершенной, если:

- реализован нужный пользовательский сценарий или системный механизм;
- поведение подтверждено в UI или через сервисный интерфейс;
- история и ошибки учитываются;
- конфигурируемость не сломана;
- есть базовая проверка результата.

## 3. Главная стратегия реализации

Рекомендуемый порядок:

1. Сначала собрать фундамент: runtime, storage, config, services.
2. Потом построить наблюдаемость и control center.
3. Потом подключить market data и shortlist engine.
4. Потом построить trading screen и signal pipeline.
5. Потом подключить AI layer.
6. Потом добавить session briefing, review, audit и feedback.
7. Потом knowledge base, replay и расширения.

## 4. Реестр эпиков

- `E0` Product framing and source of truth
- `E1` Runtime foundation and local control plane
- `E2` Data ingestion and local historical store
- `E3` Trading screen and live signal workspace
- `E4` Control center and runtime operations
- `E5` AI roles, orchestration and model assignment
- `E6` Signal lifecycle, ranking and risk-control
- `E7` Session lifecycle: preflight, briefing, active mode, pause
- `E8` Demo trading integration and result tracking
- `E9` Audit trail, feedback and session review
- `E10` Knowledge base and research layer
- `E11` Backtesting, replay and model/strategy activation
- `E12` Reliability, degraded mode and release readiness
- `E13` Exchange abstraction and multi-exchange portability (Wave E, после Wave D) — см. [ADR-008](adrs/adr-008-exchange-abstraction-and-multi-exchange-portability.md)

---

## E0. Product Framing And Source Of Truth

**Цель:** зафиксировать, какие документы являются истиной для разработки, чтобы дальше не потеряться в красивых идеях и старых версиях.

### Task E0.1: Зафиксировать набор мастер-документов

- [ ] Определить `Engineering Blueprint` как главный архитектурный документ.
- [ ] Определить этот `Execution Backlog` как главный документ по последовательности работ.
- [ ] Определить `tech-stack-v1.md` как канонический документ по стеку и baseline toolchain.
- [ ] Ввести правило: крупные изменения архитектуры сначала правятся в blueprint, потом в backlog.

### Task E0.1a: Зафиксировать канонический tech stack

- [ ] Убрать из stack-решений формулировки вида `или`, если они относятся к baseline `v1`.
- [ ] Явно разделить `day-one baseline`, `phase-later` и `not selected`.
- [ ] Зафиксировать transport policy отдельно от выбора UI / backend framework.
- [ ] Зафиксировать storage baseline отдельно от knowledge-layer expansion.

### Task E0.2: Ввести структуру уточнений

- [ ] Создать шаблон `Per-Epic Build Spec`.
- [ ] Определить обязательные поля для каждого build spec:
  - цель эпика;
  - пользовательские сценарии;
  - экраны и взаимодействия;
  - backend responsibilities;
  - data contracts;
  - acceptance criteria;
  - out-of-scope.

### Task E0.3: Зафиксировать границы v1

- [ ] Явно вынести в отдельный раздел `v1 in`.
- [ ] Явно вынести в отдельный раздел `v1 out`.
- [ ] Запретить расползание `v1` в auto-execution, multi-user и futures.
- [ ] Запретить расползание baseline-стека в premature infra choices, не нужные раннему `v1`.

**Dependencies:** нет  
**Deliverable:** стабильный набор planning-артефактов

---

## E1. Runtime Foundation And Local Control Plane

**Цель:** собрать локальный фундамент системы, который живет на ПК пользователя и управляет остальными модулями.

### Task E1.1: Спроектировать runtime-модель

- [ ] Разделить модули на `always-on services` и `on-demand services`.
- [ ] Зафиксировать состояния системы:
  - background monitoring;
  - pre-session;
  - active session;
  - paused;
  - degraded;
  - review.
- [ ] Описать допустимые переходы между состояниями.

### Task E1.2: Спроектировать backend control API

- [ ] Определить backend как центральный control layer.
- [ ] Разбить его ответственности:
  - UI API;
  - service control;
  - config management;
  - status aggregation;
  - event publication.
- [ ] Определить границу между UI и фоновыми сервисами.

### Task E1.3: Спроектировать config system

- [ ] Ввести структурированные конфиги под капотом.
- [ ] Разделить конфиги на:
  - global app config;
  - connectors config;
  - models config;
  - strategy profiles;
  - session schedules;
  - risk thresholds.
- [ ] Определить, что можно менять через UI, а что только через инженерный слой.

### Task E1.4: Спроектировать process control

- [ ] Зафиксировать список процессов, которые должны стартовать как сервисы.
- [ ] Зафиксировать список процессов, которые запускаются по требованию.
- [ ] Описать операции:
  - start;
  - stop;
  - restart;
  - health check;
  - crash state.

**Dependencies:** `E0`  
**Deliverable:** runtime architecture и control plane design

---

## E2. Data Ingestion And Local Historical Store

**Цель:** обеспечить системе собственную локальную историческую базу и стабильный сбор данных.

### Task E2.1: Спроектировать market data ingestion

- [ ] Описать источники `Binance Spot` для v1.
- [ ] Зафиксировать, какие потоки обязательны:
  - OHLCV;
  - volume;
  - simplified order book.
- [ ] Описать refresh/update стратегию для `5m`, `15m`, `1h`.

### Task E2.2: Спроектировать external context ingestion

- [ ] Описать слой `news connectors`.
- [ ] Описать слой `community sentiment connectors`.
- [ ] Зафиксировать интерфейс сменных коннекторов.

### Task E2.3: Спроектировать local data storage

- [ ] Разделить хранилище на:
  - time-series market data;
  - external context data;
  - derived features;
  - signals;
  - sessions;
  - decisions;
  - feedback;
  - model registry;
  - strategy history.
- [ ] Определить retention-политику для разных типов данных.

### Task E2.4: Спроектировать data freshness rules

- [ ] Зафиксировать, когда данные считаются stale.
- [ ] Описать, как stale data влияет на сигналы.
- [ ] Описать поведение preflight при stale data.

### Task E2.5: Спроектировать shortlist inputs

- [ ] Зафиксировать, какие данные участвуют в выборе shortlist.
- [ ] Вынести критерии:
  - ликвидность;
  - объём;
  - волатильность.

**Dependencies:** `E1`  
**Deliverable:** схема ingest + schema local historical store

---

## E3. Trading Screen And Live Signal Workspace

**Цель:** спроектировать основной торговый экран как рабочий интерфейс ручной торговли.

### Task E3.1: Описать layout trading screen

- [ ] Разделить экран на главные зоны:
  - shortlist/active pairs;
  - ranked signals;
  - selected pair chart;
  - signal explanation;
  - news/sentiment panel;
  - risk panel;
  - update timer.

### Task E3.2: Описать ranked signals UX

- [ ] Определить, как выглядит карточка сигнала.
- [ ] Зафиксировать обязательные поля карточки.
- [ ] Описать, как меняется карточка при weakening/invalidation.

### Task E3.3: Описать pair focus workflow

- [ ] Определить поведение при выборе пары пользователем.
- [ ] Описать, как меняются:
  - график;
  - новости;
  - sentiment;
  - explanation;
  - strategy context.

### Task E3.4: Описать live state behavior

- [ ] Описать поведение экрана в:
  - normal mode;
  - degraded mode;
  - defensive mode;
  - paused session.

**Dependencies:** `E2`  
**Deliverable:** UX/spec trading screen

---

## E4. Control Center And Runtime Operations

**Цель:** спроектировать операторский центр как пульт управления системой.

### Task E4.1: Описать layout control center

- [ ] Выделить блоки:
  - services health;
  - API status;
  - system resources;
  - active models;
  - active strategy;
  - session status;
  - alerts.

### Task E4.2: Описать operations workflow

- [ ] Зафиксировать, какие модули можно стартовать и останавливать вручную.
- [ ] Зафиксировать, для каких действий нужен confirm dialog.
- [ ] Описать последствия restart/stop для active session.

### Task E4.3: Описать config operations

- [ ] Описать UI для смены:
  - стратегии;
  - shortlist пар;
  - active models;
  - confidence thresholds;
  - schedule window.

### Task E4.4: Описать status semantics

- [ ] Ввести единые статусы:
  - healthy;
  - degraded;
  - stale;
  - stopped;
  - error.
- [ ] Описать, как они показываются в UI.

**Dependencies:** `E1`, `E2`  
**Deliverable:** UX/spec control center

---

## E5. AI Roles, Orchestration And Model Assignment

**Цель:** закрепить роли ИИ и правила их взаимодействия.

### Task E5.1: Описать AI role model

- [ ] Зафиксировать роли:
  - Chief Agent;
  - Market Scanner;
  - News/Sentiment Agent;
  - Forecast Model.
- [ ] Для каждой роли определить:
  - входы;
  - выходы;
  - допустимые действия;
  - ограничения.

### Task E5.2: Описать orchestration flow

- [ ] Определить порядок обработки данных между ролями.
- [ ] Описать, где именно происходит финальная синтезация сигнала.
- [ ] Описать, кто отвечает за explanation layer.

### Task E5.3: Описать conflict handling

- [ ] Зафиксировать, что финальное решение принимает `Chief Agent`.
- [ ] Описать обязательный вывод конфликта в UI.
- [ ] Описать правило снижения confidence при конфликте.

### Task E5.4: Описать model assignment UI

- [ ] Зафиксировать сценарий смены модели через панель.
- [ ] Описать review-card перед активацией новой модели.
- [ ] Описать запрет silent switching.

### Task E5.5: Описать model registry

- [ ] Ввести сущность `model version`.
- [ ] Ввести поля:
  - id;
  - role compatibility;
  - training date;
  - source;
  - metrics summary;
  - notes;
  - activation status.

**Dependencies:** `E1`, `E2`  
**Deliverable:** AI orchestration spec

### E5-DEPLOY5. AI Model Layer (deployment increment)

- **5a:** LLM adapter (httpx, OpenAI-compat) + LiteLLM podman gateway + CLAY_LLM_BASE_URL + smoke (no external) + fix 2 pre-existing fails
- **5b:** chief-agent live (run_agent + async job ai-agent-cycle + persist ops + kill-switch TUN-down 0-leak)
- **5c:** subagents (market-scanner live; news-sentiment на demo per ADR-012)
- **5d:** forecast quant (dataset из market.market_bars → train → local inference; absorbs ML-track)
- **5e:** validation_lab A/B + governed activation (model_assignment)
- **cross-cut:** data-exfil policy + geo-allowlist (never-US) + egress-аудит + kill-switch на шлюз

Refs: ADR-005, ADR-009..012; build_specs/deploy5-ai-model-layer.md  
Dependencies: E1, E2, E5

**Backlog (обновлено 2026-06-13 после docs-консолидации):**

Закрыто:
- [x] **Governance (закрыто 5b-iii.4b):** placeholder `openai-gpt-5.4` удалён; chief-agent → `minimax-m3`.
- [x] **Gemini full-cycle smoke (закрыто 5b-iii.5c):** заменён на Flash Lite (RPD 500 vs 20).
- [x] **Kill-switch 3.5e (закрыто):** миграция якоря с uid 1000 на uid 945 (clay).
- [x] **5c.4 multi-role smoke (закрыто):** 4 роли, 3 cloud-провайдера, per-role isolation proven.
- [x] **FOOTGUN A (закрыт 4d6da5a):** `database_url` required, негатив-тест.
- [x] **FOOTGUN D (закрыт c82acd5):** reasoning_content fallback.
- [x] **FOOTGUN F (закрыт c0a53f5):** SSE heartbeat + shared stream helper.
- [x] **clay_timescaledb restart-policy:** restart=always + podman-restart + linger.
- [x] **5c.5 consumer→signal_engine:** закрыто (5c.5.1 subagent→chief + 5c.5.2 smoke).

Текущие приоритеты (в порядке выполнения):
1. **Provider-pool (stateful, схема `ops`)** — следующий код-слайс после docs-консолидации.
2. **Retention/индекс `ai_agent_runs`** — рост ~1150 строк/день@300s×4; `list_latest_agent_runs` без LIMIT.
3. **FOOTGUN E** — `LiteLLMModelClient` захватывать HTTP status + body в error (пустая 400 при гео/transient).
4. **Расширение ролей:** risk-manager → bull/bear || devils-advocate лайт → расклейка news/sentiment → regime-detector + reflection → onchain/macro/liquidity.
5. **UI-трек Фазы 1–3** (observability → run-now → чат-окно + промпты в DB) — после фикса SSE/publisher.
6. **Хвосты:** замена тестовых ключей (TokenRouter + Gemini) — Emma; решение о постоянном включении флагов (300s, 4 роли) — Emma; DNS metadata-leak для uid clay — опционально.

---

## E6. Signal Lifecycle, Ranking And Risk-Control

**Цель:** сделать signal engine объяснимым, ранжируемым и безопасным.

### Task E6.1: Описать signal schema

- [ ] Зафиксировать поля сигнала.
- [ ] Разделить signal summary и expanded explanation.
- [ ] Описать обязательные причины сигнала.

### Task E6.2: Описать ranking logic

- [ ] Зафиксировать, какие факторы влияют на приоритет сигнала.
- [ ] Описать, как ranking учитывает confidence и risk.
- [ ] Описать, как shortlist и ranked signals взаимодействуют.

### Task E6.3: Описать dynamic signal lifecycle

- [ ] Описать правила weakening.
- [ ] Описать правила invalidation.
- [ ] Описать max TTL.

### Task E6.4: Описать risk engine

- [ ] Зафиксировать risk triggers:
  - stale data;
  - market overheating;
  - model conflict;
  - low data quality;
  - repeated poor signals;
  - API degradation.
- [ ] Описать response actions:
  - warning only;
  - lower confidence;
  - block signal;
  - switch to defensive.

### Task E6.5: Описать strategy mode switching

- [ ] Зафиксировать режимы:
  - Trend-following;
  - Momentum;
  - Defensive.
- [ ] Описать сценарий, когда система может предложить смену режима.
- [ ] Описать подтверждение пользователя.

**Dependencies:** `E3`, `E5`  
**Deliverable:** signal/risk specification

---

## E7. Session Lifecycle: Preflight, Briefing, Active Mode, Pause

**Цель:** сделать работу сессии дисциплинированной и повторяемой.

### Task E7.1: Описать hard preflight

- [ ] Зафиксировать обязательные проверки:
  - data freshness;
  - API availability;
  - active model loaded;
  - shortlist confirmed;
  - strategy confirmed;
  - risk limits active.
- [ ] Описать, что именно блокирует старт.

### Task E7.2: Описать pre-session briefing

- [ ] Зафиксировать структуру briefing:
  - shortlist;
  - market context;
  - sentiment summary;
  - active strategy;
  - risk alerts;
  - AI summary.

### Task E7.3: Описать active session state machine

- [ ] Описать запуск сессии.
- [ ] Описать переход в pause.
- [ ] Описать возврат из pause.
- [ ] Описать завершение сессии.

### Task E7.4: Описать dynamic pair replacement

- [ ] Зафиксировать, когда система может предложить заменить пару.
- [ ] Описать сравнение старой и новой пары.
- [ ] Описать пользовательское подтверждение.

**Dependencies:** `E3`, `E4`, `E6`  
**Deliverable:** session lifecycle spec

---

## E8. Demo Trading Integration And Result Tracking

**Цель:** встроить demo-обкатку как обязательный этап развития системы.

### Task E8.1: Описать Binance demo workflow

- [ ] Зафиксировать сценарий ручной торговли в demo.
- [ ] Описать связь между сигналом, действием пользователя и сделкой.
- [ ] Зафиксировать read-only чтение результатов.

### Task E8.2: Описать trade/result linking

- [ ] Определить, как сигнал связывается с реальной demo-сделкой.
- [ ] Описать случаи:
  - пользователь вошла;
  - пользователь не вошла;
  - вошла не по тому сигналу;
  - вошла позже.

### Task E8.3: Описать success criteria для demo stage

- [ ] Зафиксировать метрики допуска к live.
- [ ] Описать, как считается “стабильный плюс”.
- [ ] Описать, что считается крупной просадкой или критическим техническим сбоем.

**Dependencies:** `E6`, `E7`  
**Deliverable:** demo validation spec

---

## E9. Audit Trail, Feedback And Session Review

**Цель:** обеспечить полную объяснимость и обучаемость системы на собственной истории.

### Task E9.1: Описать audit event model

- [ ] Зафиксировать, какие события пишутся всегда.
- [ ] Ввести поля:
  - timestamp;
  - actor;
  - module;
  - event type;
  - object id;
  - explanation;
  - severity.

### Task E9.2: Описать feedback workflow

- [ ] Зафиксировать форму обратной связи по сигналу.
- [ ] Описать обязательные и необязательные поля.
- [ ] Описать, как feedback связывается с signal history.

### Task E9.3: Описать session review screen

- [ ] Описать метрики review.
- [ ] Описать фильтры:
  - by pair;
  - by strategy;
  - by time;
  - by model version;
  - by confidence band.

### Task E9.4: Описать AI-assisted review

- [ ] Зафиксировать, какие выводы может делать `Chief Agent` по итогам сессии.
- [ ] Запретить скрытые изменения стратегии без подтверждения.

**Dependencies:** `E6`, `E8`  
**Deliverable:** audit/review specification

---

## E10. Knowledge Base And Research Layer

**Цель:** встроить knowledge layer без торможения realtime-логики.

### Task E10.1: Описать knowledge base scope for v1

- [ ] Разделить `v1 now` и `future expansion`.
- [ ] В `v1 now` включить:
  - заметки;
  - правила стратегий;
  - чеклисты;
  - личные наблюдения.

### Task E10.2: Описать ingestion policy

- [ ] Описать, как материалы попадают в knowledge layer.
- [ ] Описать теги, категории и приоритеты.
- [ ] Зафиксировать, что мусорный контент не должен влиять на торговый слой.

### Task E10.3: Описать retrieval policy

- [ ] Зафиксировать, в каких сценариях knowledge base разрешено использовать.
- [ ] Зафиксировать, что realtime signal path не должен зависеть от retrieval как обязательного шага.

**Dependencies:** `E1`, `E9`  
**Deliverable:** knowledge/research spec

---

## E11. Backtesting, Replay And Model/Strategy Activation

**Цель:** дать системе механизм осмысленной проверки идей до их активации.

### Task E11.1: Описать backtesting scope

- [ ] Зафиксировать базовый набор метрик.
- [ ] Зафиксировать набор сценариев:
  - strategy replay;
  - model comparison;
  - signal quality on history.

### Task E11.2: Описать replay workflow

- [ ] Описать, как пользователь выбирает исторический период.
- [ ] Описать, как показываются сигналы на replay.
- [ ] Описать связь replay с review screen.

### Task E11.3: Описать activation review workflow

- [ ] Зафиксировать review-card перед активацией новой модели/стратегии.
- [ ] Описать обязательные данные review-card.
- [ ] Описать подтверждение пользователя.

**Dependencies:** `E5`, `E6`, `E9`  
**Deliverable:** validation and activation spec

---

## E12. Reliability, Degraded Mode And Release Readiness

**Цель:** подготовить систему к реальной живой эксплуатации без магического мышления.

### Task E12.1: Описать degraded mode behavior

- [ ] Зафиксировать причины входа в degraded mode.
- [ ] Описать поведение UI в degraded mode.
- [ ] Описать, какие функции становятся ограниченными.

### Task E12.2: Описать local fallback behavior

- [ ] Описать, что именно доступно при локальном fallback.
- [ ] Зафиксировать ограничения fallback.
- [ ] Описать, как пользователь видит разницу между full mode и fallback.

### Task E12.3: Описать readiness criteria

- [ ] Зафиксировать критерии готовности отдельных эпиков.
- [ ] Зафиксировать критерии готовности общей v1-системы.
- [ ] Зафиксировать критерии readiness для demo stage.

### Task E12.4: Описать release gates

- [ ] Определить, что нельзя релизить без:
  - preflight;
  - risk controls;
  - audit trail;
  - demo-read integration;
  - degraded mode visibility.

**Dependencies:** `E1`–`E11`  
**Deliverable:** release readiness checklist

---

## E13. Exchange Abstraction And Multi-Exchange Portability

**Цель:** абстракция источника рыночных данных — см. [ADR-008](adrs/adr-008-exchange-abstraction-and-multi-exchange-portability.md).

Декомпозиция планируется после завершения Wave D (live rehearsal Binance, текущий эпик). ADR-008 содержит предварительные слайсы E0–E6.

**Dependencies:** `E2`, `Wave D`  
**Deliverable:** multi-exchange ingestion spec

---

## 5. Приоритеты на ближайшую декомпозицию

Сразу после этого backlog лучше всего детализировать в таком порядке:

1. `E1` Runtime foundation and local control plane
2. `E2` Data ingestion and local historical store
3. `E4` Control center and runtime operations
4. `E3` Trading screen and live signal workspace
5. `E5` AI roles, orchestration and model assignment
6. `E6` Signal lifecycle, ranking and risk-control
7. `E7` Session lifecycle

Текущий AI-трек (2026-06-13): см. E5-DEPLOY5 «Backlog» выше — provider-pool → retention → FOOTGUN E → расширение ролей → UI-трек.

Именно эти эпики дают первую рабочую “ось” системы.

## 6. Как использовать этот документ дальше

Следующий шаг не “реализовать всё сразу”, а пройти по каждому приоритетному эпику и для него сделать отдельный `Per-Epic Build Spec`.

Правильный рабочий цикл:

1. Выбрать эпик.
2. Собрать по нему build spec.
3. Декомпозировать задачи в технические шаги.
4. Только потом переходить к реализации.

## 7. Рекомендуемый следующий шаг

Начать с эпика `E1`:

- runtime foundation;
- control plane;
- config system;
- process model.

Без него всё остальное легко превращается в красивый набор экранов без хребта.
