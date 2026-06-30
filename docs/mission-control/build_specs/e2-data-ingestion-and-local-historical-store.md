> **STATUS: HISTORICAL PLANNING (заморожен).** Документ относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).

# E2 Build Spec — Data Ingestion And Local Historical Store

Дата: 2026-03-30
Эпик: `E2`
Статус: build-spec
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/runbooks/runbook-001-preflight-degraded-mode.md`

## 1. Цель эпика

Собрать ingest- и storage-контур `v1`, который:

- стабильно получает рыночные данные для `Binance Spot`;
- собирает внешний контекст из `news` и `community sentiment` источников;
- ведёт собственную локальную историческую базу;
- умеет определять freshness/staleness данных;
- даёт foundation для shortlist, signal pipeline, preflight и session review;
- не тащит knowledge layer в hot path раньше времени.

Этот эпик строит не “график в UI”, а хребет данных, без которого дальнейшая аналитика будет как shell script без входного файла: громкая, но бесполезная 😼

## 2. Входит в scope

- `Binance Spot` market data ingestion
- external context ingestion:
  - news connectors
  - community sentiment connectors
- local historical store
- data normalization layer
- freshness tracking
- retention policy
- shortlist input preparation
- ingest health and ingest error semantics
- contracts для downstream consumers:
  - shortlist engine
  - signal pipeline
  - preflight
  - review/audit

## 3. Не входит в scope

- signal generation
- signal ranking
- strategy switching logic
- `Chief Agent` orchestration
- knowledge base ingestion
- embeddings / semantic retrieval
- auto-execution
- full backtesting engine

## 4. Архитектурные допущения

- рынок `v1`: `Binance Spot only`
- рабочие пары: `3–5`, но ingest-layer должен поддерживать список watchlist шире активного shortlist
- таймфреймы `v1`: `5m`, `15m`, `1h`
- market data hot path не должен зависеть от новостей или community sources
- browser UI не получает raw exchange streams напрямую
- storage baseline: `PostgreSQL + TimescaleDB`
- `pgvector` и knowledge-specific расширения не являются блокером `E2`

## 5. Главный результат эпика

После завершения `E2` разработчик должен получить:

- стабильно работающий market ingestion для `Binance Spot`;
- слой сменных external context connectors;
- локальную схему хранения market/context/history данных;
- систему freshness markers и stale detection;
- понятный контракт для shortlist inputs;
- основу для health/preflight checks по данным.

## 6. Логические компоненты E2

### 6.1 Market Data Service

Отвечает за:

- получение market streams и snapshots;
- нормализацию market payload;
- запись в local historical store;
- обновление freshness markers;
- публикацию ingest health events.

### 6.2 Context Connector Manager

Отвечает за:

- запуск news connectors;
- запуск sentiment connectors;
- унифицированный lifecycle внешних контекстных источников;
- статус, ошибки, freshness и rate-limit состояние коннекторов.

### 6.3 History Store Service

Отвечает за:

- запись нормализованных market/context данных;
- retention jobs;
- storage-facing read models для downstream слоёв;
- запись metadata о происхождении данных.

### 6.4 Freshness Evaluator

Отвечает за:

- вычисление stale/not-stale состояния;
- раздельные freshness markers для:
  - market bars
  - order book summaries
  - news context
  - community sentiment
- публикацию data health signals в runtime/control plane.

### 6.5 Shortlist Input Builder

Отвечает за:

- подготовку агрегатов для shortlist engine;
- сводные показатели ликвидности, объёма и волатильности;
- подготовку candidate universe.

## 7. Источники данных v1

### 7.1 Market sources

Для `v1` каноническим источником рынка является `Binance Spot`.

Обязательные потоки:

- `OHLCV bars`
- `aggregated volume`
- `simplified order book summaries`

### 7.2 External context sources

Для `v1` обязательны два класса внешних источников:

- `crypto news`
- `community sentiment`

Конкретные провайдеры не прибиваются к полу в этом build-spec. Здесь фиксируется контракт слоя, а не окончательный список API-ключей.

## 8. Market data ingestion policy

### 8.1 Что обязательно ingest-ить

#### Bars

Для каждого наблюдаемого symbol:

- `open`
- `high`
- `low`
- `close`
- `volume`
- `quote_volume`, если доступно
- `bar_open_time`
- `bar_close_time`
- `timeframe`
- `source`

#### Simplified order book summary

`v1` не требует полного хранения каждого raw order book tick.

Нужно хранить summary-срезы, достаточные для intraday decision support:

- best bid
- best ask
- spread
- top-of-book depth summary
- imbalance summary
- snapshot timestamp

#### Freshness metadata

Для каждого symbol/timeframe/source:

- last received at
- last persisted at
- last successful normalize at
- stale flag

### 8.2 Таймфреймы и update strategy

#### `5m`

- основной короткий слой для точки входа;
- bar close должен быстро попадать в storage и downstream summary.

#### `15m`

- основной рабочий intraday слой;
- считается главным decision timeframe для `v1`.

#### `1h`

- старший контекст;
- используется для общего направления и shortlist context.

### 8.3 Ingestion model

Правильная схема:

1. raw exchange data приходит в backend ingest layer;
2. data normalizer приводит его к canonical schema;
3. normalized records пишутся в local store;
4. freshness evaluator обновляет markers;
5. downstream слои читают уже storage-backed или normalized views.

UI не должен ходить за raw exchange data напрямую.

## 9. External context ingestion policy

### 9.1 News connectors

Каждый news connector должен уметь:

- fetch new items;
- нормализовать headline/body/summary/source fields;
- назначать timestamps;
- сохранять provenance;
- сообщать freshness and error state.

### 9.2 Community sentiment connectors

Каждый sentiment connector должен уметь:

- собирать signal snapshots по symbol/topic;
- нормализовать sentiment label/score/source;
- сохранять timestamp, source and aggregation scope;
- сообщать freshness and rate-limit state.

### 9.3 Сменные коннекторы

Слой external context ingestion обязан строиться через connector interface.

Минимальный контракт коннектора:

- `connector_id`
- `connector_type`
- `source_name`
- `enabled`
- `supports_symbols`
- `fetch()`
- `normalize()`
- `health_check()`
- `freshness_status()`

Это нужно, чтобы позже можно было заменить или добавить источники без перекройки всей ingest-логики.

## 10. Local storage model

### 10.1 Market domain

Хранить:

- `market_bars`
- `orderbook_summaries`
- `market_features` (`phase-ready`, даже если часть фич появится позже)
- `market_freshness_status`

### 10.2 Context domain

Хранить:

- `news_items`
- `news_symbol_links`
- `sentiment_snapshots`
- `context_freshness_status`

### 10.3 Ops domain

Хранить:

- `ingest_runs`
- `connector_status_history`
- `source_health_events`

### 10.4 Shortlist-supporting aggregates

Хранить или материализовывать:

- symbol liquidity metrics
- rolling volume metrics
- rolling volatility metrics
- shortlist candidate summaries

### 10.5 Domain boundaries

`E2` не обязан создавать все review/signal/final AI tables, но обязан спроектировать storage так, чтобы следующие эпики могли без боли опереться на:

- symbol history
- context history
- freshness history
- shortlist history inputs

## 11. Retention policy

Каноническая retention policy берётся из `ADR-004` и должна быть применена в `E2`.

### Обязательные сроки

- `OHLCV` и aggregated volume: `24 месяца`
- simplified order book summaries: `30 дней`
- derived features: `180 дней`
- news and sentiment snapshots: `180 дней`
- ingest health / connector status history: хранить минимум `180 дней`

Для `signals`, `sessions`, `feedback`, `audit` и `model history` retention управляется следующими эпиками и не является scope `E2`, но storage design должен учитывать их будущее существование.

## 12. Freshness and stale rules

### 12.1 Каноническое правило

Система должна различать:

- `fresh`
- `degraded`
- `stale`
- `unknown`

для каждого ключевого data stream.

### 12.2 Market stale semantics

Market data считаются `stale`, если:

- последняя обязательная запись отсутствует дольше допустимого окна для данного timeframe;
- ingest не может подтвердить последнюю успешную нормализованную запись;
- order book summary не обновлялся дольше допустимого порога.

### 12.3 Context stale semantics

News/sentiment могут стать `stale`, но их staleness не всегда должна блокировать рынок полностью.

Нужно разделять:

- `critical market freshness`
- `non-critical context freshness`

### 12.4 Влияние на систему

#### Если stale market data

- preflight не проходит;
- normal active trading mode блокируется;
- signal pipeline обязан либо блокироваться, либо работать только в ограниченном monitoring mode.

#### Если stale context data

- система может остаться в `degraded`;
- confidence и explanation quality могут понижаться;
- market-only operation допустима только если это не нарушает строгие safety rules.

## 13. Shortlist input policy

Shortlist engine в `v1` должен опираться на:

- ликвидность
- объём
- волатильность

`E2` обязан подготовить storage-backed inputs для этих критериев.

### Что именно нужно уметь получить

Для candidate universe:

- rolling volume score
- rolling volatility score
- liquidity summary
- availability/freshness flag

### Что пока не является обязательным shortlist criterion

- embeddings/research relevance
- сложные AI-derived composite ranks
- on-chain data

## 14. Health and error semantics

Каждый ingest source и connector должен иметь единые статусы:

- `healthy`
- `degraded`
- `stale`
- `rate_limited`
- `error`
- `disabled`

Ошибки должны быть разделены минимум на классы:

- auth/config error
- upstream availability error
- parse/normalize error
- storage write error
- freshness timeout

## 15. API / service-facing contracts needed after E2

### Control / health layer

- health summary по ingestion services
- freshness summary по market/context sources
- ingest incident feed

### Downstream read surfaces

- latest bars by symbol/timeframe
- latest order book summary by symbol
- latest news/sentiment context by symbol
- shortlist metrics by symbol

Это не значит, что весь query API нужно реализовать здесь полностью. Но контракты должны быть спроектированы.

## 16. Failure modes, которые E2 обязан учитывать

- Binance stream interruption
- snapshot/stream mismatch
- stale bars
- stale order book summary
- news connector outage
- sentiment connector outage
- source rate limiting
- malformed upstream payload
- duplicate persistence
- storage lag
- retention job failure

Для каждого класса сбоев система обязана:

- фиксировать incident;
- обновлять source health state;
- не подменять silently stale состояние нормальным;
- сохранять объяснимый статус для preflight и runtime.

## 17. Acceptance criteria

Эпик `E2` считается готовым, если выполняются все условия:

1. `Binance Spot` market data ingest спроектирован как backend-only ingestion layer.
2. Для `5m`, `15m`, `1h` описан canonical ingestion/update path.
3. В storage определены таблицы/домены для market, context и ingest ops.
4. External context connectors имеют сменный интерфейс.
5. Retention policy для market/context/ingest data явно зафиксирована.
6. Freshness semantics описаны отдельно для market и context data.
7. `stale market data` явно блокируют normal active trading flow.
8. Shortlist inputs по ликвидности, объёму и волатильности описаны как storage-backed contract.
9. Storage design не зависит от `pgvector` или knowledge layer.
10. Ingest health и source incidents могут быть отданы в control plane и preflight.

## 18. Проверки и валидация

Обязательные проверки для `E2`:

- schema validation tests для normalized market/context payload
- duplicate handling tests
- freshness calculation tests
- stale detection tests
- retention policy tests
- connector contract tests
- storage write/read contract tests

## 19. Out-of-scope улучшения на потом

- on-chain ingestion
- full depth order book archival
- tick-by-tick trade archival
- semantic enrichment of news via knowledge layer
- auto-ranking universe beyond liquidity/volume/volatility
- multi-exchange federation
