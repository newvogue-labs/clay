# ADR-003 — Transport Policy (HTTP / SSE / WebSocket)

Дата: 2026-03-30
Статус: accepted
Связанные эпики: `E1`, `E3`, `E4`, `E5`, `E6`, `E7`

## Контекст

`CLAY Mission Control` строится как:

- `local-first`
- `single-user`
- `web-first`
- с отдельным `control plane`
- с UI, который должен видеть состояние системы, preflight, degraded incidents, ranked signals и ответы `AI Console` в реальном времени

При этом система не является:

- многопользовательским облачным приложением;
- high-frequency trading terminal с raw market feed прямо в браузере;
- distributed collaboration platform, которой жизненно нужен сложный bidirectional realtime protocol.

Для `v1` нужно принять transport policy, которая:

- будет достаточно простой для локального single-PC сценария;
- хорошо сочетается с `FastAPI`;
- не создаст лишней operational complexity;
- не размоет границу между `control plane`, managed services и browser UI;
- оставит путь для future expansion, если когда-нибудь действительно понадобится более сложный bidirectional transport.

Если не зафиксировать это решение явно, то проект рискует начать жить в режиме:

- “давайте всё через `WebSocket`, потому что realtime звучит круто”;
- “давайте всё через polling, потому что так проще сейчас”;
- “давайте добавим `socket.io`, на всякий случай”.

Такой подход легко рождает сетевой винегрет и документную шизофрению уровня “одна спека пишет `SSE`, другая уже мечтает о `WebSocket`, а код потом страдает как обычно” 🐧

## Решение

Принять следующую transport policy для `v1`:

1. `HTTP/JSON` является каноническим transport для:
   - command operations;
   - CRUD/config operations;
   - status snapshots;
   - history/review fetches;
   - manual user actions.
2. `SSE` является каноническим transport по умолчанию для browser-facing server-to-client streaming:
   - runtime events;
   - service health changes;
   - preflight progress;
   - alerts;
   - signal updates;
   - AI text streaming.
3. `WebSocket` не является baseline transport для `v1`.
4. `WebSocket` допускается только при появлении явно обоснованного bidirectional сценария и отдельного superseding ADR или расширения этого ADR.
5. `socket.io` не используется в `v1`.
6. Raw exchange realtime streams не публикуются напрямую в browser UI; они живут в backend/ingestion layer, а UI получает только нормализованные system events или prepared views.

## Каноническое распределение transport-слоёв

### A. Browser command path

Использовать `HTTP/JSON`.

Примеры:

- `POST /runtime/transition`
- `POST /services/{service_id}/restart`
- `POST /configs/{config_scope}/apply`
- `POST /preflight/run`
- `POST /ai-console/messages`

### B. Browser streaming path

Использовать `SSE`.

Примеры:

- `GET /events/stream`
- `GET /signals/stream`
- `GET /ai-console/stream/{conversation_id}`
- `GET /preflight/stream/{run_id}`

### C. Browser snapshot/read path

Использовать `HTTP/JSON`.

Примеры:

- `GET /runtime/state`
- `GET /services`
- `GET /alerts`
- `GET /preflight/latest`
- `GET /session-review/{session_id}`

### D. Backend-to-external systems

Этот ADR регулирует прежде всего browser-facing transport.

Для backend integrations допускаются свои transport mechanisms:

- Binance WebSocket streams для ingestion;
- HTTP APIs для market/news/sentiment providers;
- provider-specific streaming APIs для cloud model calls.

Но browser не должен видеть их в сыром виде.

## Почему `SSE` по умолчанию, а не `WebSocket`

Для `v1` основной realtime-паттерн односторонний:

- сервер публикует события;
- UI их отображает;
- команды пользователя всё равно приходят как отдельные контролируемые действия.

Преимущества `SSE` в этом контексте:

- проще operationally;
- проще дебажить;
- лучше соответствует event-feed модели `Mission Control`;
- хорошо ложится на `FastAPI` и text/event streaming;
- не требует вводить постоянный bidirectional session channel там, где он не нужен.

## Почему `WebSocket` не запрещён навсегда

`WebSocket` может понадобиться позже, если появится реальный сценарий, где `HTTP + SSE` перестаёт быть достаточным.

Примеры возможных будущих оснований:

- интерактивный bidirectional инструментальный terminal с server-prompted elicitation;
- сложный collaborative mode;
- нестандартный transport для high-frequency UI interaction, который нельзя разумно моделировать через `HTTP + SSE`.

Но для `v1` ни один из уже утверждённых пользовательских сценариев этого не требует.

## Polling policy

Polling не является primary realtime transport.

Он допустим только как:

- bootstrap snapshot;
- reconnect fallback;
- explicit manual refresh;
- low-priority periodic refresh для несрочных экранов review/history.

Нельзя проектировать core live experience вокруг polling.

## Event model requirements

Все streamed события должны иметь единый envelope:

- `event_id`
- `event_type`
- `emitted_at`
- `source`
- `severity`
- `correlation_id`
- `payload`

Это нужно, чтобы:

- UI мог единообразно обрабатывать runtime, preflight, alert и signal events;
- audit и observability могли связывать события между собой;
- transport-слой не превращался в набор несогласованных ad-hoc payload'ов.

## AI Console policy

Для `AI Console` канонический паттерн `v1` такой:

1. пользователь отправляет сообщение или команду через `HTTP`;
2. backend создаёт request/run context;
3. ответ и промежуточные события идут в UI через `SSE`;
4. действия, меняющие состояние системы, по-прежнему проходят через подтверждаемые command endpoints.

То есть `AI Console` не получает право на скрытый bidirectional control channel только потому, что слово “chat” звучит модно.

## Preflight and runtime events policy

`Preflight` и runtime operations должны публиковать прогресс и результаты через `SSE`.

Это касается:

- переходов состояний;
- health changes;
- degraded incidents;
- config apply results;
- recovery progress.

UI не должен каждые несколько секунд дёргать API, чтобы выяснить, жив ли runtime-manager.

## Raw market data policy

Сырые exchange streams не должны публиковаться в UI напрямую.

Правильная схема для `v1`:

1. ingestion получает raw feeds в backend;
2. backend нормализует, агрегирует и валидирует данные;
3. UI получает:
   - snapshots;
   - prepared chart data;
   - signal-related events;
   - alerts и freshness markers.

Это защищает браузерный слой от лишней сложности и сохраняет разделение между market ingestion и operator UI.

## Consequences for E1 and later epics

### E1

- `GET /events/stream` должен проектироваться как `SSE` endpoint;
- UI-facing runtime event feed не требует `WebSocket`;
- preflight progress и degraded alerts должны быть совместимы с unified event stream.

### E2

- market data ingestion может использовать backend-level `WebSocket` to exchange, но это не browser transport.

### E3-E4

- trading workspace и control center получают snapshots через `HTTP` и live updates через `SSE`.

### E5-E7

- `AI Console`, signal lifecycle, preflight и runtime orchestration строятся вокруг `HTTP + SSE`.

## Рассмотренные альтернативы

### A. Всё через `WebSocket`

Отклонено.

Причины:

- слишком много bidirectional complexity для `v1`;
- хуже объяснимость transport boundary;
- выше риск начать тащить в браузер то, что должно жить в backend.

### B. Всё через polling

Отклонено.

Причины:

- хуже UX;
- лишняя нагрузка на control API;
- хуже подходит для preflight progress, alerts и AI streaming.

### C. `socket.io` поверх всего

Отклонено.

Причины:

- лишняя зависимость и abstraction layer;
- не даёт критичной пользы при уже достаточной схеме `HTTP + SSE`.

## Последствия

### Положительные

- transport policy становится простой и предсказуемой;
- browser-facing realtime не перегружается;
- легче писать build-spec и API contracts;
- проще дебажить event feeds;
- сохраняется чистая граница между control plane, ingestion и UI.

### Отрицательные

- если позже действительно понадобится богатый bidirectional protocol, придётся принимать новое решение;
- часть разработчиков может инстинктивно тянуться к `WebSocket`, потому что слово знакомое и блестит.

## Что теперь обязательно

- browser commands идут через `HTTP`;
- browser live streams идут через `SSE` по умолчанию;
- raw exchange streams не попадают прямо в UI;
- `socket.io` не включается в baseline `v1`;
- новые browser-facing `WebSocket` endpoints требуют отдельного явного обоснования.

## Что это не запрещает

- использовать `WebSocket` внутри backend integration layer;
- позже добавить новый ADR для конкретного bidirectional сценария;
- иметь polling как fallback или low-priority refresh mechanism.

Но базовый принцип остаётся:

для `v1` transport должен быть минимально достаточным, а не максимально модным.
