# ADR-004 — Storage Baseline And Phased Extensions

Дата: 2026-03-30
Статус: accepted
Связанные эпики: `E2`, `E8`, `E9`, `E10`, `E11`, `E12`

## Контекст

`CLAY Mission Control v1` должен:

- вести собственную локальную историческую базу;
- хранить market data, context data, signals, sessions, decisions, feedback и audit;
- поддерживать single-PC `local-first` сценарий;
- не зависеть от knowledge layer для раннего `v1`;
- не превращаться в маленький домашний дата-центр с тремя базами, четырьмя брокерами и кризисом идентичности.

Уже зафиксировано:

- storage baseline для `v1` = `PostgreSQL + TimescaleDB`;
- `pgvector` нужен только как `phase-later` для knowledge/retrieval;
- knowledge base не должна быть обязательным bottleneck для realtime-контура.

Теперь нужно явно решить:

- какая storage topology считается baseline;
- какие классы данных живут в БД;
- какие классы данных должны жить в файловой системе;
- какие данные относятся к `TimescaleDB` time-series слою;
- когда и как разрешено добавлять `pgvector`;
- какую retention-модель считать нормой для `v1`.

Без этого проект рискует быстро скатиться в хаос:

- market history в одной таблице без политики хранения;
- model artifacts в БД как BLOB-кирпичи;
- embeddings в раннем `v1`, хотя retrieval ещё не нужен;
- audit, signals и sessions вперемешку без логической границы.

## Решение

Принять следующую storage policy для `v1`:

1. В `v1` используется **один локальный PostgreSQL instance** как primary storage engine.
2. Внутри него `TimescaleDB` является обязательным extension для time-series и append-heavy данных.
3. `pgvector` **не входит в day-one baseline** и включается только с `E10`, когда knowledge layer становится реальной частью системы.
4. Для `v1` **не вводится отдельная vector DB**, отдельная TSDB или отдельный OLAP store.
5. Крупные бинарные артефакты и исходные документы не должны храниться в PostgreSQL как primary storage; для них используется локальная файловая система, а БД хранит metadata и references.
6. Storage-дизайн должен быть **phased**, то есть ранний `v1` не блокируется отсутствием research/retrieval слоя.

## Baseline storage topology

### Каноническая схема для `v1`

- `1 x local PostgreSQL database`
- `TimescaleDB` enabled in the same database
- structured schemas for logical separation
- filesystem-backed storage for bulky local artifacts

### Что это значит practically

- не заводить отдельный `Redis` как обязательный storage layer;
- не заводить отдельную `Milvus`, `Qdrant`, `Weaviate` или другую vector DB для `v1`;
- не разбивать локальную систему на несколько разных баз “на будущее”.

## Logical storage domains

Для `v1` storage разделяется на домены:

- `market`
- `context`
- `signals`
- `ops`
- `ml`
- `research` (`phase-later`)

Это логическое деление. Физически всё остаётся в одном PostgreSQL baseline.

## Что хранится в PostgreSQL baseline

### 1. `market`

Хранить:

- OHLCV bars
- aggregated volume data
- simplified order book summaries
- derived market features
- freshness timestamps

### 2. `context`

Хранить:

- news items metadata
- normalized news payload
- community sentiment snapshots
- source attribution
- timestamps and relevance markers

### 3. `signals`

Хранить:

- shortlist history
- generated signals
- signal explanations
- signal state changes
- sessions
- operator decisions
- feedback
- demo/live result references

### 4. `ops`

Хранить:

- runtime events
- alerts
- preflight runs
- degraded incidents
- config revision metadata
- config apply results
- audit trail

### 5. `ml`

Хранить:

- model registry metadata
- active model assignments
- model training metadata
- model evaluation summaries
- strategy history

### 6. `research` (`phase-later`)

Хранить:

- document metadata
- chunk metadata
- embedding references
- retrieval runs
- research/audit links

Но этот домен не должен блокировать ранние эпики `E2-E9`.

## Что НЕ хранится в PostgreSQL как primary artifact store

### Файловая система используется для:

- model binaries / exported forecast artifacts
- imported raw documents for knowledge base
- transcript/source files
- temporary ingestion files
- exports / manual backups

БД в этих сценариях хранит:

- metadata
- file path / artifact reference
- checksum
- provenance
- version / revision info

## TimescaleDB policy

### Обязательное применение

`TimescaleDB` обязателен для time-series и append-heavy слоёв:

- OHLCV bars
- volume data
- simplified order book summaries
- feature time-series
- signal state history
- runtime event history
- preflight/degraded event timelines

### Что это даёт

`Hypertables` позволяют хранить time-series данные как нормальные PostgreSQL tables с автоматическим разбиением по времени и более адекватной работой на больших объёмах time-based inserts/query patterns.

### Что не требуется прямо сейчас

Для раннего `v1` не нужно преждевременно вводить:

- отдельный cold-storage tier;
- сложную multi-node storage topology;
- специальные OLAP-витрины;
- нестандартную sharding-схему.

## pgvector policy

### Базовое правило

`pgvector` не является обязательной зависимостью раннего `v1`.

### Когда он включается

`pgvector` становится обязательным только при реальном включении:

- `E10 Knowledge Base And Research Layer`
- retrieval workflows
- semantic chunk search
- embedding-backed research linking

### Почему он не нужен раньше

- ранний `v1` уже может работать как торгово-аналитическая система без vector search;
- knowledge base в `v1` изначально ограничена и не должна лезть в hot path;
- лишний extension не должен усложнять локальный bootstrap раньше, чем от него появится польза.

### Что запрещено

- нельзя делать `pgvector` hard blocker для `E2` local historical store;
- нельзя проектировать базовую market/signal storage схему так, как будто vector retrieval уже обязателен.

## Retention policy for v1

### Ретеншн по классам данных

#### Market bars

- `OHLCV` и aggregated volume:
  - хранить `24 месяца`

#### Simplified order book summaries

- хранить `30 дней`

#### Derived features

- хранить `180 дней`

#### External context data

- news items и sentiment snapshots:
  - хранить `180 дней`

#### Signals / sessions / decisions / feedback

- хранить `без автоматического удаления` в `v1`

#### Audit / runtime events / preflight history

- хранить `без автоматического удаления` в `v1`, пока пользователь явно не включит archival/purge workflow

#### Model registry / strategy history

- хранить `без автоматического удаления`

#### Research chunks / embeddings

- после включения `E10` хранить `без автоматического удаления`, пока не появится отдельная archive policy

### Почему такие сроки

- market bars полезны для review и локального replay на разумном горизонте;
- order book summaries имеют самую высокую цену хранения при меньшей долгосрочной ценности;
- derived features и external context полезны для post-session analysis, но не обязаны жить вечно;
- signals, decisions, feedback и audit являются наиболее ценной объяснительной историей системы и не должны исчезать автоматически в раннем `v1`.

## Storage classes by implementation phase

### Phase A — Early v1 baseline

Обязательно:

- `PostgreSQL`
- `TimescaleDB`
- market / context / signals / ops / ml domains
- filesystem artifact storage

Не обязательно:

- `pgvector`
- semantic retrieval
- document chunk embeddings

### Phase B — Review and expansion

Допускается:

- richer retention jobs
- archive/export workflows
- storage tuning for heavy ingest

### Phase C — Knowledge layer

Добавляется:

- `pgvector`
- research schema expansion
- chunk + embedding lifecycle
- retrieval metadata

## Freshness and storage interaction

Storage не должен быть просто “кладбищем данных”.

Он обязан поддерживать:

- latest-known freshness markers;
- timestamps последней успешной записи;
- возможность определить stale source;
- связь между data freshness и signal admissibility.

То есть storage design должен помогать `preflight`, `risk-control` и `degraded mode`, а не существовать отдельно в философском вакууме.

## Backup and export boundary

Для `v1` не требуется enterprise-grade backup topology.

Но storage policy должна предусматривать:

- возможность локального SQL dump / export;
- возможность экспортировать audit/history отдельно;
- явное разделение между runtime DB и planning docs в Obsidian/Git.

Плановые документы не заменяют runtime backup.

## Рассмотренные альтернативы

### A. Separate vector DB from day one

Отклонено.

Причины:

- knowledge layer ещё не является обязательным runtime-слоем;
- лишняя инфраструктурная сложность;
- слабая польза для раннего `v1`.

### B. SQLite baseline instead of PostgreSQL

Отклонено.

Причины:

- слабее fit для time-series + audit + concurrent service access;
- хуже соответствует уже принятому stack baseline.

### C. Separate TSDB plus separate relational DB

Отклонено для `v1`.

Причины:

- оверкилл для single-PC сценария;
- больше operational surface area;
- сложнее сопровождать локально.

### D. Store model artifacts and source docs directly in DB

Отклонено.

Причины:

- локальная БД не должна быть primary binary archive;
- хуже управляемость и переносимость крупных артефактов.

## Последствия

### Положительные

- storage baseline остаётся достаточно мощным, но не перегруженным;
- `E2` можно строить без блокировки на knowledge layer;
- `E10` получает понятную фазу расширения;
- легче проектировать retention и freshness rules;
- проще держать локальную систему управляемой.

### Отрицательные

- потребуется дисциплина по разделению DB metadata и filesystem artifacts;
- позже понадобится аккуратная миграция при включении `pgvector`.

## Что теперь обязательно

- `PostgreSQL + TimescaleDB` считаются storage baseline `v1`;
- `pgvector` не блокирует ранний `v1`;
- raw bulky artifacts живут в filesystem, а не как primary blobs в БД;
- retention policy должна быть частью storage design, а не послесловием;
- data freshness markers должны проектироваться как часть storage contracts.

## Что это не запрещает

- позже включить `pgvector`;
- позже добавить archive jobs;
- позже усилить backup/export workflows;
- позже оптимизировать hypertable policies по реальным ingest patterns.

Но базовый принцип остаётся:

storage должен расти по фазам, а не приезжать в `v1` целиком как самосвал будущих хотелок.
