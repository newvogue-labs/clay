# E5 Build Spec — AI Roles, Orchestration And Model Assignment

Дата: 2026-04-15
Эпик: `E5`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-003-transport-policy-http-sse-websocket.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e3-trading-screen-and-live-signal-workspace.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e4-control-center-and-runtime-operations.md`

## 1. Цель эпика

Собрать `AI layer` для `CLAY Mission Control`, который:

- явно разделяет AI-роли и provider/model assignments;
- оркестрирует market/context/forecast inputs в объяснимый итоговый output;
- поддерживает operator-controlled model switching через review flow;
- переживает degraded/fallback mode без silent магии;
- оставляет audit trail по тому, какая роль и какая модель реально участвовали в анализе.

`E5` строит не “чатик с четырьмя умными названиями”, а дисциплинированную систему ролей и маршрутов, где модели не прыгают между обязанностями как случайные процессы после `kill -9` 😼

## 2. Входит в scope

- role model для:
  - `chief_agent`
  - `market_scanner`
  - `news_sentiment_agent`
  - `forecast_model`
  - `local_fallback_text`
- provider abstraction layer
- `model version` registry semantics
- `role assignment` semantics
- orchestration flow между ролями
- conflict handling и confidence downgrade policy
- degraded/fallback routing policy
- operator-facing model assignment review flow
- audit requirements для invocations и assignment changes

## 3. Не входит в scope

- финальная ranking logic сигналов
- signal TTL / weakening / invalidation internals
- full risk engine policy
- knowledge/RAG retrieval pipeline
- auto-routing marketplace между провайдерами
- hidden self-modifying agent behavior
- training pipeline forecast models как MLOps-платформа

## 4. Архитектурные допущения

- `E5` опирается на provider abstraction из `ADR-005`
- роли не жёстко зашиваются на конкретного вендора
- operator-controlled assignment остаётся нормой `v1`
- `Forecast Model` живёт как отдельный класс от text-heavy providers
- orchestration работает поверх prepared inputs из предыдущих слоёв, а не поверх raw exchange/browser data
- browser-facing live UX остаётся через `HTTP + SSE`, а не через vendor-specific streaming chaos

## 5. Главный результат эпика

После завершения `E5` разработчик должен получить:

- канонический role model для AI-компонентов системы;
- ясную модель orchestration flow и точки финальной синтезации;
- контракты model registry / provider / role assignment;
- правила degraded fallback и conflict handling;
- acceptance criteria, по которым можно проверить, что AI-layer управляемый, объяснимый и не превращается в black box-цирк.

## 6. Главные пользовательские сценарии

### A. Нормальный рабочий анализ

Система:

- получает shortlist/market/context inputs;
- вызывает нужные роли по фиксированному orchestration flow;
- собирает итог через `Chief Agent`;
- отдаёт summary, explanation и confidence в operator-facing слои.

### B. Смена модели на роли

Пользователь хочет сменить модель на роли, например для `chief_agent`.

Система обязана:

- показать review-card;
- показать provider/model/version/capabilities;
- показать ограничения и compatibility;
- не применять change silently.

### C. Конфликт между ролями

Например:

- `Market Scanner` видит сильный setup;
- `News/Sentiment Agent` даёт негативный контекст;
- `Forecast Model` не поддерживает уверенное направление.

Система обязана:

- не скрывать конфликт;
- снизить итоговую уверенность;
- сохранить conflict trace для UI и audit.

### D. Degraded fallback

Если сильная text model недоступна:

- система может включить ограниченный fallback;
- UI обязан явно показать degraded semantics;
- audit обязан зафиксировать переход и его причину.

## 7. Канонические сущности E5

### 7.1 Provider

Интеграционный слой, который:

- аутентифицируется;
- отправляет запрос;
- нормализует ответ;
- нормализует latency/errors/usage;
- сообщает capability and availability state.

### 7.2 Model version

Конкретная модель или артефакт, зарегистрированный в системе.

Минимальные metadata:

- `model_id`
- `provider_id`
- `display_name`
- `model_family`
- `version_label`
- `role_compatibility[]`
- `capabilities[]`
- `cost_tier`
- `latency_profile`
- `availability_class`
- `source`
- `notes`

### 7.3 Role assignment

Связь между ролью и активной model version.

Именно assignment, а не provider, является канонической operational связью.

### 7.4 Invocation record

Запись об одном вызове роли/модели.

Нужна для:

- audit;
- error/debugging;
- degraded tracing;
- later evaluation.

## 8. Ролевой состав `v1`

### 8.1 `chief_agent`

Отвечает за:

- финальную синтезацию сигнала;
- итоговое explanation layer;
- отображение конфликтов;
- confidence downgrade при конфликте;
- briefing summary;
- рекомендации по смене strategy mode.

Требует capabilities:

- `text_generation`
- `streaming_output`
- `structured_output`
- `reasoning_suitable`

### 8.2 `market_scanner`

Отвечает за:

- обзор рынка;
- shortlist proposals;
- оценку market dynamics;
- структурированный market summary.

Требует capabilities:

- `structured_output`
- `summary_suitable` или `classification_suitable`

### 8.3 `news_sentiment_agent`

Отвечает за:

- summarization внешнего фона;
- sentiment interpretation;
- контекстные flags по активам;
- передачу contextual factors в signal synthesis.

Требует capabilities:

- `summary_suitable`
- `classification_suitable`

### 8.4 `forecast_model`

Отвечает за:

- directional forecast;
- magnitude contribution;
- numeric confidence input;
- evaluation-linked inference metadata.

Важно:

- не обязан идти через тот же contract, что cloud chat/reasoning providers;
- остаётся отдельным inference class.

### 8.5 `local_fallback_text`

Отвечает только за:

- ограниченный degraded explanation/support path;
- не притворяется full-strength `chief_agent`;
- не должен сохранять прежний confidence semantics.

## 9. Orchestration flow `v1`

### 9.1 Input foundation

В `E5` upstream inputs считаются уже подготовленными:

- shortlist and market summary
- news/sentiment summary
- forecast artifact output
- runtime/degraded context
- active strategy and config context

### 9.2 Канонический порядок обработки

Нормальный `v1` flow:

1. `Market Scanner` формирует shortlist/market structure summary
2. `News/Sentiment Agent` формирует external context summary
3. `Forecast Model` даёт numeric directional contribution
4. `Chief Agent` получает всё выше и делает final synthesis
5. UI-facing layers получают итоговое summary/explanation/conflict notes

### 9.3 Где живёт финальная синтезация

Финальная synthesis живёт в `Chief Agent`.

Это значит:

- остальные роли не должны silently подменять финальный вывод;
- итоговый explanation layer собирается именно здесь;
- `Chief Agent` отвечает за честное отображение конфликта между inputs.

## 10. Conflict handling policy

### 10.1 Типы конфликтов

Минимально учитывать:

- market vs news conflict
- market vs forecast conflict
- provider/model degraded confidence conflict
- structured output inconsistency

### 10.2 Каноническое поведение

При конфликте система обязана:

- сохранить конфликт как first-class signal input;
- не стирать неудобные части reasoning;
- понизить confidence;
- отдать structured conflict summary в UI-facing layers.

### 10.3 Что запрещено

Нельзя:

- silently выбирать “более красивый” output;
- скрывать disagreement между ролями;
- оставлять прежний высокий confidence при явном конфликте.

## 11. Model assignment policy

### 11.1 Базовое правило

Для `v1` нормой считается:

1. у роли есть активный assignment;
2. assignment указывает конкретную `model version`;
3. `model version` знает свой `provider`;
4. runtime вызывает provider adapter через нормализованный интерфейс.

### 11.2 Operator-controlled switching

Смена assignment должна:

- инициироваться через панель;
- иметь review-card;
- проходить validation;
- фиксироваться в audit.

### 11.3 Review-card contents

Перед apply пользователь должен видеть:

- роль;
- provider;
- model name/version;
- role compatibility;
- capability summary;
- latency/cost profile;
- degraded fallback eligibility;
- notes / major risks.

### 11.4 Что запрещено

Нельзя:

- silently менять assignment;
- назначать несовместимую модель на роль;
- считать fallback assignment полной заменой основной роли.

## 12. Model registry semantics

### 12.1 Registry fields

Минимальные поля:

- `model_id`
- `display_name`
- `provider_id`
- `version_label`
- `role_compatibility[]`
- `capabilities[]`
- `training_date | null`
- `evaluation_summary | null`
- `source`
- `activation_status`
- `notes`

### 12.2 Provider fields

Минимальные поля:

- `provider_id`
- `provider_type`
- `display_name`
- `enabled`
- `availability_status`
- `timeout_policy`
- `retry_policy`
- `supports_streaming`

### 12.3 Assignment fields

Минимальные поля:

- `role_name`
- `model_id`
- `provider_id`
- `assignment_state`
- `fallback_only`
- `degraded_fallback_allowed`
- `changed_by`
- `changed_at`

## 13. Fallback and degraded policy

### 13.1 Базовое правило

Fallback — это ограниченное, видимое и аудируемое поведение.

### 13.2 Для `chief_agent`

Если `chief_agent` недоступен:

- fallback допускается только при явной совместимости;
- UI обязан показать degraded reasoning quality;
- confidence semantics должны быть снижены;
- audit обязан зафиксировать замену.

### 13.3 Для остальных ролей

Если fallback отсутствует:

- система должна честно показывать reduced capability;
- `Chief Agent` обязан учитывать missing/reduced input как часть reasoning;
- отсутствие input не должно маскироваться под normal full context.

## 14. UI-facing data contracts после `E5`

### 14.1 Model assignment summary

Минимальные поля:

- `role_name`
- `provider_name`
- `model_name`
- `model_version`
- `availability_status`
- `fallback_only`
- `degraded_fallback_allowed`
- `capability_summary[]`

### 14.2 Assignment review card

Минимальные поля:

- `role_name`
- `current_assignment`
- `proposed_assignment`
- `compatibility_check`
- `capability_diff[]`
- `risk_notes[]`
- `requires_confirmation`

### 14.3 Invocation summary

Минимальные поля:

- `invocation_id`
- `role_name`
- `model_id`
- `provider_id`
- `mode` (`full`, `degraded`, `fallback`)
- `latency_ms`
- `finish_status`
- `error_category | null`

### 14.4 Conflict summary contract

Минимальные поля:

- `conflict_id`
- `roles_involved[]`
- `conflict_type`
- `summary`
- `confidence_penalty`
- `visibility_level`

## 15. Transport and interaction expectations

### 15.1 HTTP snapshot examples

- `GET /ai/roles`
- `GET /ai/models`
- `GET /ai/assignments`
- `GET /ai/assignments/review/{roleName}`

### 15.2 HTTP command examples

- `POST /ai/assignments/review`
- `POST /ai/assignments/apply`
- `POST /ai/assignments/rollback`

### 15.3 SSE stream examples

- `GET /ai/events/stream`
- `GET /providers/stream`

### 15.4 Что нельзя

Нельзя:

- делать vendor-specific transport частью public UI contract;
- смешивать assignment control и raw provider internals в одном хаотичном endpoint zoo;
- переводить browser layer на magic auto-routing без отдельного решения.

## 16. Failure modes, которые `E5` обязан учитывать

### A. Assignment incompatible with role

Система обязана:

- отклонить apply;
- показать compatibility reason;
- не допускать partial silent activation.

### B. Provider unavailable

Система обязана:

- показать degraded/provider error;
- активировать fallback только по policy;
- сохранить audit trace.

### C. Forecast artifact missing

Система обязана:

- честно показать reduced analysis completeness;
- не притворяться, что forecast contribution присутствует.

### D. Conflict explosion

Если входы расходятся сильно:

- confidence должен снижаться;
- UI должен видеть conflict summary;
- `Chief Agent` не должен сглаживать конфликт до “всё ок”.

### E. Manual assignment switch during active session

Система обязана:

- показать impact review;
- предупредить о возможном изменении поведения explanations/signals;
- зафиксировать change в audit.

## 17. Acceptance criteria

Эпик `E5` считается готовым, если выполняются все условия:

1. Роли и provider/model assignments логически разделены.
2. `Chief Agent` зафиксирован как финальная точка synthesis.
3. `Market Scanner`, `News/Sentiment Agent`, `Forecast Model` имеют отдельные responsibilities.
4. Model switching спроектирован как operator-reviewed flow, а не silent magic.
5. Fallback/degraded semantics явно видимы и аудируемы.
6. Conflict handling влияет на итоговую уверенность.
7. Model registry и assignment contracts позволяют понять, кто реально участвовал в анализе.
8. Transport contracts не завязаны на vendor-specific UI logic.

## 18. Обязательные проверки для `E5`

- проверить role/model/provider separation;
- проверить assignment compatibility validation;
- проверить review-card перед apply;
- проверить degraded fallback visibility;
- проверить conflict summary output;
- проверить audit trace по assignment changes и invocations;
- проверить, что `Chief Agent` остаётся final synthesis point;
- проверить, что missing/reduced input не маскируется под full mode.

## 19. Dependencies и границы с соседними эпиками

### 19.1 Зависимости

`E5` зависит минимум от:

- `E1` runtime/control plane
- `E2` data/context foundation

### 19.2 Граница с `E4`

`E4` показывает operator-facing status и review entrypoints.

`E5` не должен превращаться в:

- generic runtime operations screen;
- сервисный health dashboard;
- конфиг-центр всей системы.

### 19.3 Граница с `E6`

`E6` отвечает за signal schema, ranking, lifecycle и risk-control internals.

`E5` даёт AI orchestration foundation, но не определяет final signal engine math.

### 19.4 Граница с `E10`

`E10` отвечает за knowledge/RAG layer.

`E5` может использовать research later, но knowledge retrieval не является hard dependency для раннего `v1`.

## 20. Артефакты, которые должны следовать после `E5 build-spec`

Сразу после `E5` логично подготовить:

- `E5 implementation plan — AI Roles, Orchestration And Model Assignment`
- `E6 build-spec — Signal Lifecycle, Ranking And Risk-Control`
- `E7 build-spec — Session Lifecycle`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E5`.
