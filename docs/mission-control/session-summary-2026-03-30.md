# CLAY Mission Control — Session Summary

Дата: 2026-03-30
Статус: pause point before `E3 build-spec`

## 1. Текущий этап

Проект находится **только в planning/documentation phase**.

Важно:

- реализация кода не начинается;
- execution choice пока не выбирается;
- задача текущего этапа — собрать полный и согласованный пакет документации.

## 2. Что уже сделано

### 2.1 Организация проектовой папки

Все ключевые planning-документы перенесены в:

- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control`

Имена файлов приведены к короткой и предсказуемой схеме.

### 2.2 Master-docs

Готовы:

- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/index.md`

### 2.3 Принятые ADR

Приняты и синхронизированы:

- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-002-config-validation-and-rollback-policy.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`

### 2.4 Build-spec'и

Готовы:

- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e1-runtime-foundation-control-plane.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e2-data-ingestion-and-local-historical-store.md`

### 2.5 Дополнительные planning-артефакты

Готовы:

- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/runbooks/runbook-001-preflight-degraded-mode.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/implementation_plans/e1-runtime-foundation-control-plane-implementation-plan.md`

Важно:

- `implementation plan` существует как артефакт planning-фазы;
- это **не означает старт реализации**.

## 3. Зафиксированные продуктовые решения v1

Ключевые решения:

- `local-first`
- `single-user`
- `web-first`
- `Binance Spot only`
- `3–5` рабочих пар
- `Intraday active`, с fallback в `Intraday slow`
- анализ каждые `10–15 минут`
- горизонт сигнала `30–90 минут`
- market data: `OHLCV + volume + simplified order book`
- внешний контекст: `crypto news + community sentiment`
- сделки исполняются вручную в `Binance`
- CLAY выдаёт сигналы, объяснения, риск и системный статус
- жёсткий `preflight`
- `degraded mode`
- минимальный локальный fallback
- полный `audit trail`

## 4. Зафиксированные технические решения

### Tech stack baseline

- `Vite + React 19 + TypeScript`
- `FastAPI + Python 3.12+`
- `PostgreSQL + TimescaleDB`
- `APScheduler`
- `SSE` как базовый browser-facing realtime transport
- `WebSocket` не baseline для browser UI
- `pgvector` только позже, с `E10`
- model provider layer должен быть сменным

### Storage baseline

- один локальный `PostgreSQL` instance;
- `TimescaleDB` обязателен;
- крупные артефакты и исходные документы живут в файловой системе, а не как primary blobs в БД.

## 5. Что уже решено по интерфейсу CLAY

### 5.1 Внешние окна пользователя

Во время работы предполагаются **2 физических окна**:

1. `Binance` в браузере — для графика биржи, стакана, формы ордера и ручного исполнения сделки.
2. `CLAY Mission Control` — для аналитики, сигналов, контроля системы и работы с ИИ.

### 5.2 Внутренняя структура CLAY

Внутри CLAY не отдельные внешние окна, а **одна app shell-оболочка** с постоянным левым sidebar.

Предварительно зафиксированы внутренние экраны:

- `Overview`
- `Trading Workspace`
- `Control Center`
- `AI Console`
- `Session Review`
- `Knowledge / Research`
- `Settings`

Главные боевые экраны:

- `Trading Workspace`
- `Control Center`

### 5.3 Важная граница UX

CLAY **не должен дублировать Binance terminal**.

Что нельзя превращать в центр интерфейса CLAY:

- большой `order form`
- полноразмерный exchange-style `order book`
- UI, имитирующий второй Binance

CLAY должен быть:

- decision-support workspace;
- mission control shell;
- analyst console.

## 6. Что обсуждалось по визуальному направлению

### 6.1 Что уже понравилось пользователю

Пользователь отдельно отметил, что по стилю ему в целом подходит:

- `Cryptocurrency Trading Terminal`

### 6.2 Дополнительные стилевые референсы, которые пользователь прислал

Пользователь попросил учитывать как стилевые референсы:

- https://stock.adobe.com/ru/images/infographic-dashboard-template-with-flat-design-graphs-and-pie-charts-online-statistics-and-data-analytics-information-graphics-elements-for-ui-ux-design-modern-style-web-elements-stock-vector/258136981
- https://www.behance.net/gallery/244308545/SAAS-Landing-Page-AI-Powered-SEO-Management-Software
- https://www.behance.net/gallery/238788443/Scalepro-Modern-SaaS-Web-Design
- https://www.behance.net/gallery/245015647/Crypto-Trading-Dashboard-UXUI-Design
- https://www.behance.net/gallery/231927099/CryptoVue-Modern-Crypto-Trading-Dashboard-UI
- https://www.behance.net/gallery/108625439/Trade-Withe-Me-signals-for-trading
- https://www.behance.net/gallery/243719385/Business-Analytics-Dashboard-UIUX

### 6.3 Визуальные источники, на которые уже опирались

- `/home/emma/Downloads/Trading Terminal.webp`
- `/home/emma/Downloads/2026-03-30_20-25.png`

Последний особенно важен как reference для **общей shell-структуры**:

- левый sidebar;
- переключение между внутренними экранами;
- overview/settings/control logic.

## 7. Где именно остановились

Мы остановились на **ключевом вопросе для `E3 build-spec`**:

> Для главного торгового экрана что важнее как дефолтный режим фокуса:
> одна выбранная пара крупно в центре, а остальные как контекст вокруг,
> или сразу несколько пар почти одинаково заметны на одном экране?

Это главный незакрытый UX-вопрос перед сборкой `E3`.

## 8. Предварительная позиция, которую уже наметили

Предварительный вектор такой:

- `OpenClaw-like sidebar shell`
- внутри `Trading Workspace` не дублировать `Binance`
- график, explanation, risk и context должны быть важнее “биржевой формы ордера”
- ranked signals, shortlist, chart, explanation и risk/context должны стать главными панелями

Но **окончательный layout не утверждён**.

## 9. Что сделать завтра

Рекомендованный следующий порядок:

1. Посмотреть и отобрать варианты макетов / референсов.
   Пользователь планирует принести новые варианты экранов и shell-layout, чтобы согласовать каркас интерфейса перед `E3 build-spec`.
2. Ответить на ключевой layout-вопрос:
   - `single focused pair`
   - или `multi-panel multi-pair radar`
3. После этого собрать `E3 build-spec`.
4. Затем идти в `E4 build-spec`.

## 10. Что важно не забыть завтра

- не свалиться в “второй Binance inside CLAY”;
- не перегрузить `Trading Workspace` одинаково громкими панелями;
- сначала утвердить **каркас окна**, а уже потом стилистику, кнопки, индикаторы и polishing;
- `Control Center` и `Trading Workspace` должны быть разными по логике, даже если живут в одной оболочке.

## 11. Короткий resume-тезис

Фундамент проекта уже собран:

- docs organized
- tech stack accepted
- ADR baseline accepted
- `E1` и `E2` build-spec готовы

Следующий реальный узел — не backend и не код, а **утверждение skeleton layout для `Trading Workspace`**, от которого зависит весь `E3`.
