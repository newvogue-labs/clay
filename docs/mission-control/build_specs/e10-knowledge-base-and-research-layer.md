# E10 Build Spec — Knowledge Base And Research Layer

Дата: 2026-04-15
Эпик: `E10`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e9-audit-trail-feedback-and-session-review.md`

## 1. Цель эпика

Собрать `knowledge / research layer` для `CLAY Mission Control`, который:

- даёт системе нормальное место для заметок, правил стратегий, чеклистов и research-материалов;
- помогает review, research и настройке без торможения realtime-контура;
- вводит controlled retrieval только там, где он реально нужен;
- не превращает весь `v1` в RAG-стартап, который сначала индексирует вселенную, а потом забывает про торговлю;
- готовит базу для будущего расширения knowledge workflows без day-one перегруза.

`E10` нужен не для того, чтобы CLAY внезапно стал библиотекарем-оракулом, а чтобы знание, правила и наблюдения перестали жить в разрозненных заметках и начали работать как дисциплинированный вспомогательный слой. И да, без обязательного вызова эмбеддингов перед каждым чихом сигнального движка 😼

## 2. Входит в scope

- `knowledge base light mode` for `v1`
- canonical scope for notes, strategy rules, checklists, and user observations
- phased expansion path for PDFs, books, transcripts, curated research
- ingestion policy for knowledge materials
- metadata/tag/category/priority policy
- retrieval policy for allowed research scenarios
- UI-facing contracts for knowledge and research screen
- storage and extension policy for `pgvector` activation in `E10`

## 3. Не входит в scope

- making knowledge retrieval mandatory for every signal
- full autonomous research agent ecosystem
- heavy document ETL pipeline for all file types on day one
- full enterprise document management
- replacing review/history evidence with knowledge summaries
- mandatory online/cloud document sync

## 4. Архитектурные допущения

- `E10` зависит от уже собранного review/history слоя `E9`
- knowledge screen существует в `v1`, но не входит в hot path торговых сигналов
- `pgvector` становится обязательным только при реальном включении retrieval workflows в `E10`
- baseline storage остаётся phased: bulky source artifacts живут в filesystem, metadata and references живут в database
- browser-facing knowledge/research interactions идут через `HTTP/JSON`, live updates могут использовать `SSE` при необходимости
- retrieval результаты должны быть explainable and source-linked

## 5. Главный результат эпика

После завершения `E10` разработчик должен получить:

- канонический scope для `knowledge base v1`;
- ясную ingestion policy;
- retrieval policy с жёсткими границами применения;
- phased extension path от light mode к richer research;
- acceptance criteria, по которым можно проверить, что knowledge layer полезен, но не душит runtime.

## 6. Главные пользовательские сценарии

### A. Работа с личными заметками и правилами

Пользователь:

- сохраняет заметки;
- хранит правила стратегий;
- собирает чеклисты;
- ведёт личные наблюдения.

Система обязана:

- хранить это в структурированном виде;
- позволять искать и фильтровать;
- не смешивать рабочие знания с мусорным контентом.

### B. Research перед review или настройкой

Пользователь:

- открывает knowledge/research screen;
- ищет правила, прошлые observations или curated notes;
- использует их для review, research и strategy tuning.

Система обязана:

- возвращать source-linked результаты;
- показывать приоритет и релевантность;
- не маскировать personal notes под “объективную рыночную истину”.

### C. Retrieval для research-сценария

Если knowledge layer уже расширен:

- можно искать по semantic chunks;
- можно подтягивать связанные материалы;
- можно связывать research и audit/review context.

Но:

- retrieval не должен быть обязательным шагом перед каждым сигналом;
- отсутствие retrieval не должно ломать активную торговую сессию.

### D. Future expansion content

Позже knowledge layer может включать:

- PDF;
- books;
- transcripts;
- curated research.

Система обязана:

- явно отделять `v1 now` от `future expansion`;
- не тянуть весь этот объём в ранний bootstrap без нужды.

## 7. Канонические сущности E10

### 7.1 Knowledge item

Минимальные поля:

- `knowledge_id`
- `title`
- `content_type`
- `category`
- `tags[]`
- `priority`
- `source_type`
- `created_at`
- `updated_at`
- `status`

### 7.2 Knowledge source artifact

Минимальные поля:

- `artifact_id`
- `knowledge_id`
- `file_path | null`
- `checksum | null`
- `source_uri | null`
- `source_label`
- `ingested_at`

### 7.3 Retrieval result

Минимальные поля:

- `retrieval_id`
- `knowledge_id`
- `match_type`
- `score`
- `excerpt`
- `source_label`
- `reason_summary`

### 7.4 Research note link

Минимальные поля:

- `link_id`
- `knowledge_id`
- `target_type`
- `target_id`
- `link_reason`

## 8. Scope policy: `v1 now` vs `future expansion`

### 8.1 Что входит в `v1 now`

- personal notes
- strategy rules
- checklists
- user observations

### 8.2 Что относится к `future expansion`

- PDF
- books
- transcripts
- curated research corpora

### 8.3 Базовое правило

`E10` обязан чётко разделять:

- то, что реально нужно для раннего `v1`;
- то, что можно подключать позже без блокировки текущего продукта.

### 8.4 Что запрещено

Нельзя:

- притаскивать future-expansion content как hard requirement для раннего `v1`;
- считать knowledge completeness prerequisite for demo-stage usage;
- превращать scope в “индексируем всё подряд, а потом разберёмся”.

## 9. Ingestion policy

### 9.1 Как материалы попадают в knowledge layer

Для `v1` допустимы:

- manual note creation
- structured import of local markdown/text materials
- controlled attachment of strategy docs/checklists

### 9.2 Обязательная metadata discipline

Каждый knowledge item обязан иметь минимум:

- category
- tags
- priority
- source attribution
- update timestamp

### 9.3 Garbage-control policy

Мусорный, нерелевантный или непроверенный контент:

- не должен silently влиять на торговый слой;
- должен быть отделим по status/category;
- не должен подмешиваться в retrieval как равноценное знание.

## 10. Retrieval policy

### 10.1 Где retrieval разрешён

Минимально допустимые сценарии:

- research before strategy adjustment
- review support
- explanation support for knowledge/research screen
- future replay/backtesting enrichment

### 10.2 Где retrieval не должен быть обязательным

- realtime signal hot path
- session admission
- degraded recovery
- basic workspace operation

### 10.3 Базовое правило

Knowledge retrieval может помогать, но не должен быть hard blocker для:

- live workspace updates
- preflight/session flow
- core signal ranking

### 10.4 Что запрещено

Нельзя:

- делать retrieval mandatory перед каждым сигналом;
- скрывать отсутствие knowledge hit под видом “уверенного вывода”;
- возвращать result без source attribution и reason summary.

## 11. `pgvector` and storage policy

### 11.1 Когда `pgvector` включается

С `E10` `pgvector` становится обязательным только если:

- реально активирован semantic retrieval;
- knowledge layer использует embedding-backed search;
- research linking требует vector similarity.

### 11.2 Что хранится в database

- knowledge metadata
- chunk metadata
- retrieval metadata
- links to review/audit artifacts

### 11.3 Что хранится в filesystem

- bulky source artifacts
- imported raw documents
- larger local reference materials

### 11.4 Что запрещено

Нельзя:

- хранить всё подряд как giant blobs inside primary tables;
- делать `pgvector` prerequisite для ранних эпиков `E1-E9`;
- проектировать storage так, будто research layer важнее торгового ядра.

## 12. UI-facing contracts после `E10`

### 12.1 Knowledge item card contract

Минимальные поля:

- `knowledge_id`
- `title`
- `category`
- `tags[]`
- `priority`
- `updated_at`
- `source_label`

### 12.2 Retrieval result contract

Минимальные поля:

- `knowledge_id`
- `match_type`
- `score`
- `excerpt`
- `source_label`
- `reason_summary`

### 12.3 Knowledge search response contract

Минимальные поля:

- `query`
- `items[]`
- `retrieval_used`
- `total_hits`

### 12.4 Research link contract

Минимальные поля:

- `link_id`
- `target_type`
- `target_id`
- `knowledge_id`
- `link_reason`

## 13. Transport and interaction expectations

### 13.1 HTTP snapshot examples

- `GET /knowledge/items`
- `GET /knowledge/items/{knowledgeId}`
- `GET /knowledge/search?q=...`
- `GET /research/links/{targetType}/{targetId}`

### 13.2 HTTP command examples

- `POST /knowledge/items`
- `POST /knowledge/import`
- `POST /knowledge/retrieval/run`

### 13.3 SSE stream examples

- `GET /knowledge/events/stream`

### 13.4 Что нельзя

Нельзя:

- строить knowledge layer только как raw file browser;
- смешивать ingestion progress, retrieval results и trading signals в один stream без границ;
- маскировать retrieval misses как successful research hits.

## 14. Failure modes, которые `E10` обязан учитывать

### A. Retrieval ничего не нашёл

Система обязана:

- честно показать no-hit result;
- не придумывать ответов “по мотивам”;
- не блокировать при этом основную работу системы.

### B. В knowledge попал мусорный контент

Система обязана:

- позволять понизить его статус/priority;
- не смешивать его с trusted operational knowledge;
- не подсовывать его как топовый hit без объяснения.

### C. Источник большой и тяжёлый

Система обязана:

- не тянуть bulky artifact в hot path;
- хранить source reference отдельно;
- не ломать local bootstrap.

### D. Research layer недоступен

Система обязана:

- деградировать gracefully;
- не ломать signal/session/review контуры;
- явно показать ограничение knowledge workflows.

## 15. Acceptance criteria

Эпик `E10` считается готовым, если выполняются все условия:

1. `Knowledge base v1` имеет чётко отделённый `v1 now` scope и `future expansion`.
2. Ingestion policy задаёт category/tag/priority/source discipline.
3. Retrieval policy явно запрещает knowledge layer как mandatory realtime bottleneck.
4. `pgvector` activation привязана к реальному включению retrieval workflows, а не к абстрактному “на будущее”.
5. UI-facing contracts позволяют построить knowledge/research screen без ad-hoc blob parsing.
6. Failure modes around no-hit, garbage content, bulky artifacts and research unavailability описаны явно.
7. Knowledge layer помогает review/research, но не подменяет signal engine или session discipline.

## 16. Обязательные проверки для `E10`

- проверить разделение `v1 now` и `future expansion`;
- проверить metadata discipline для imported knowledge items;
- проверить no-hit retrieval scenario;
- проверить source attribution в retrieval results;
- проверить, что signal/session flow survives при knowledge-layer outage;
- проверить, что retrieval не обязателен для core realtime path;
- проверить garbage-content isolation policy;
- проверить, что bulky sources не лезут в primary hot path.

## 17. Dependencies и границы с соседними эпиками

### 17.1 Зависимости

`E10` зависит минимум от:

- `E9` review/history layer
- `ADR-004` phased storage policy

### 17.2 Граница с `E9`

`E9` отвечает за review/history evidence.

`E10` не должен:

- заменять audit/history knowledge summaries;
- делать review dependent on retrieval availability;
- скрывать raw evidence behind research snippets.

### 17.3 Граница с `E11`

`E11` отвечает за replay/backtesting/activation workflows.

`E10` может supply supporting knowledge, но не заменяет validation engine.

### 17.4 Граница с core trading path

Knowledge layer является support layer.

Он не должен становиться обязательным gate для:

- ranking
- preflight
- session start
- demo result reconciliation

## 18. Артефакты, которые должны следовать после `E10 build-spec`

Сразу после `E10` логично подготовить:

- `E10 implementation plan — Knowledge Base And Research Layer`
- `E11 build-spec — Backtesting, Replay And Model/Strategy Activation`
- при необходимости отдельный runbook по `knowledge ingest and retrieval hygiene`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E10`.
