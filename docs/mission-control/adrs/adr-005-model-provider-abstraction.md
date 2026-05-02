# ADR-005 — Model Provider Abstraction

Дата: 2026-03-30
Статус: accepted
Связанные эпики: `E1`, `E5`, `E6`, `E7`, `E10`, `E12`

## Контекст

`CLAY Mission Control v1` строится вокруг нескольких классов интеллектуальных компонентов:

- `Chief Agent`
- `Market Scanner`
- `News/Sentiment Agent`
- `Forecast Model`
- минимальный локальный fallback

При этом уже зафиксировано:

- пользователь на старте хочет использовать бесплатные или условно-бесплатные облачные модели;
- самая сильная модель должна играть роль `Chief Agent`;
- роли моделей должны назначаться через панель;
- система должна переживать деградацию части внешних `API`;
- локальный fallback допускается, но не должен притворяться полноценной заменой сильной облачной reasoning-модели.

Если не ввести явную provider abstraction, система быстро начнёт гнить в нескольких местах:

- UI и config начнут хранить vendor-specific названия как бизнес-логику;
- роли агентов смешаются с конкретными API-провайдерами;
- смена модели будет означать редактирование кода, а не конфигурации;
- fallback и degraded mode станут импровизацией;
- audit не сможет честно ответить, какая именно модель и через какой provider приняла участие в генерации сигнала.

Для `v1` нужно принять решение, которое сохранит свободу выбора между бесплатными и платными моделями, не превращая систему в религиозную войну `vendor A vs vendor B` 😼

## Решение

Принять следующую model provider policy:

1. В системе вводится **provider abstraction layer** между внутренними AI-ролями и внешними model APIs.
2. Ни UI, ни orchestration-логика не должны быть жёстко привязаны к конкретному облачному вендору.
3. Модель в системе описывается как сущность `model version`, а provider — как отдельная сущность `provider`.
4. Назначение модели на роль происходит через **role assignment**, а не через прямую ссылку “роль = вендор”.
5. Для `v1` приоритет — **operator-controlled assignment**, а не silent auto-routing.
6. Автоматический fallback допускается только как ограниченный degraded behavior с явной индикацией в UI и audit.
7. `Forecast Model` рассматривается отдельно от text-heavy providers: её training/inference lifecycle не должен быть привязан к cloud chat provider abstraction.

## Канонические сущности

### 1. Provider

`Provider` — это интеграционный слой, который умеет:

- аутентифицироваться;
- отправлять запрос;
- принимать streaming/non-streaming ответ;
- нормализовать usage/latency/errors;
- сообщать supported capabilities.

Примеры типов provider:

- cloud chat/reasoning provider
- local lightweight model adapter
- forecast inference adapter

### 2. Model version

`Model version` — это конкретная доступная модель или артефакт, зарегистрированный в системе.

Она должна иметь metadata:

- `model_id`
- `provider_id`
- `display_name`
- `model_family`
- `version_label`
- `role_compatibility`
- `capabilities`
- `cost_tier`
- `latency_profile`
- `availability_class`
- `source`
- `notes`

### 3. Role assignment

`Role assignment` — это правило, какая модель сейчас исполняет одну из ролей:

- `chief_agent`
- `market_scanner`
- `news_sentiment_agent`
- `forecast_model`
- `local_fallback_text`

Именно assignment, а не provider, является канонической связью с рабочей ролью системы.

## Разделение ролей и провайдеров

### Что запрещено

- жёстко кодировать в логике: `Chief Agent = provider X`
- жёстко кодировать в UI: `если OpenAI, то это главный режим`
- считать, что все роли требуют одинаковых capability и одинакового transport

### Что обязательно

- роль описывается внутренним контрактом;
- provider описывается интеграционным контрактом;
- модель описывается как версия, совместимая с ролью;
- assignment связывает роль с конкретной model version.

## Capability model

Каждая model version должна быть описана через capability flags.

Минимальный набор для `v1`:

- `text_generation`
- `streaming_output`
- `structured_output`
- `reasoning_suitable`
- `summary_suitable`
- `classification_suitable`
- `tool_call_compatible`
- `local_runtime`
- `degraded_fallback_allowed`

Это нужно, чтобы система не пыталась назначить:

- слабую классификационную модель на роль `Chief Agent`;
- forecast artifact на роль text analyst;
- local fallback как будто это full-strength reasoning engine.

## Role requirements for v1

### `chief_agent`

Требует:

- `text_generation`
- `streaming_output`
- `structured_output`
- `reasoning_suitable`

Дополнительно желательно:

- `tool_call_compatible`

### `market_scanner`

Требует:

- `summary_suitable` или `classification_suitable`
- `structured_output`

### `news_sentiment_agent`

Требует:

- `summary_suitable`
- `classification_suitable`

### `forecast_model`

Это отдельный класс.

Он не обязан проходить через тот же provider contract, что и chat/reasoning models.
Для него главное:

- inference artifact availability
- local compatibility
- version metadata
- evaluation metadata

## Provider adapter contract

Каждый provider adapter обязан нормализовать:

- request id
- model id
- response payload
- finish reason
- token/usage summary, если провайдер его отдаёт
- latency
- error category
- rate-limit or availability signal

Это нужно, чтобы orchestration и audit работали на едином контракте, а не читали vendor-specific формы как археологи JSON-цивилизаций.

## Request routing policy

### Базовое правило для v1

Routing по provider/model не должен быть скрытой магией.

Для `v1` нормой считается:

1. роль имеет активный assignment;
2. assignment указывает конкретную model version;
3. model version знает свой provider;
4. orchestration вызывает provider adapter через нормализованный интерфейс.

### Что допускается

Ограниченный routing по условию:

- `full mode`
- `degraded mode`
- `fallback available`

Но это не должно означать silent dynamic marketplace между моделями.

## Config model

`models.toml` и связанные конфиги должны разделять:

- provider definitions
- model registry entries
- role assignments
- fallback policy

Пример логического разделения:

- `providers[]`
- `models[]`
- `role_assignments[]`
- `fallback_rules`

Это согласуется с `ADR-002`: cross-scope validation должна проверять, что role assignment указывает только на существующую model version и совместимого provider.

## UI policy

В `Control Center` пользователь должен видеть:

- активную модель на каждой роли;
- какой provider используется;
- версию модели;
- статус доступности;
- является ли assignment fallback-only;
- какие ограничения есть у fallback mode.

При смене model assignment UI обязан:

- показывать review-card;
- показывать роль;
- показывать provider;
- показывать capability summary;
- запрещать silent switching.

## Fallback and degraded policy

### Базовое правило

Fallback — это не “автоматически всё равно как-нибудь заменим”.

Fallback — это управляемое ограниченное поведение.

### Для `v1`

- если `chief_agent` недоступен, система может перейти на fallback assignment только если он явно совместим с ролью и помечен `degraded_fallback_allowed`;
- UI обязан показать, что reasoning quality снижена;
- audit обязан зафиксировать:
  - исходный assignment;
  - fallback assignment;
  - причину переключения;
  - время начала и окончания degraded mode.

### Что запрещено

- silently заменить сильную модель на слабую и оставить прежний confidence semantics;
- считать local fallback полной заменой `Chief Agent`.

## Secrets and provider credentials

Provider credentials не должны храниться в versioned `models.toml`.

Разрешено:

- environment variables
- `.env`
- отдельные local secret paths вне Git-synced planning area

Provider config в runtime storage может хранить:

- provider id
- endpoint metadata
- timeout/retry policy
- enabled/disabled state

Но не raw secrets.

## Audit requirements

Для каждого model invocation и каждого role assignment change нужно иметь возможность узнать:

- какая роль была задействована;
- какая model version использовалась;
- какой provider был вызван;
- был ли это full mode или degraded/fallback mode;
- какой был latency и finish status;
- была ли ошибка provider-side;
- был ли assignment изменён вручную или автоматически по fallback policy.

## Рассмотренные альтернативы

### A. Hardcode provider per role

Отклонено.

Причины:

- ломает гибкость;
- мешает использовать бесплатные модели по ситуации;
- делает смену моделей слишком дорогой архитектурно.

### B. One giant “AI provider” abstraction without role model

Отклонено.

Причины:

- слишком грубо;
- не выражает реальные различия между `Chief Agent`, scanner, sentiment и forecast.

### C. Fully automatic provider marketplace from day one

Отклонено для `v1`.

Причины:

- лишняя сложность;
- труднее объяснять пользователю;
- выше риск silent behavior drift.

## Последствия

### Положительные

- система остаётся независимой от одного вендора;
- проще использовать бесплатные и смешанные provider combinations;
- легче строить model assignment UI;
- fallback и degraded mode получают внятную архитектурную форму;
- audit и session review будут понимать, кто именно участвовал в сигнале.

### Отрицательные

- provider layer требует явного adapter contract;
- model registry и assignment logic становятся отдельным объектом проектирования.

## Что теперь обязательно

- роли, provider'ы и model version'ы должны быть раздельными сущностями;
- assignment является канонической связью роли с моделью;
- provider credentials не хранятся в versioned config;
- fallback routing не должен быть silent;
- `Forecast Model` не должен насильно втискиваться в contract cloud chat provider'ов.

## Что это не запрещает

- позже добавить более умный provider selection policy;
- позже добавить capability scoring;
- позже добавить richer local model layer;
- позже расширить routing policy с учётом реальной стоимости, latency и reliability.

Но базовый принцип остаётся:

внутренние роли системы важнее названий вендоров, а provider layer должен быть заменяемым, а не священным.
