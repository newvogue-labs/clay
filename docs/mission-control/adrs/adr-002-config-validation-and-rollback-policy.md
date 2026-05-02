# ADR-002 — Config Validation And Rollback Policy

Дата: 2026-03-30
Статус: accepted
Связанный эпик: `E1`

## Контекст

`CLAY Mission Control` строится как `local-first` система с управляемым runtime, где:

- конфиги должны храниться локально и быть структурированными;
- часть параметров разрешено менять через UI;
- runtime не имеет права ломать рабочее состояние из-за плохого конфига;
- `preflight` и `degraded mode` зависят от валидности active config;
- system services, model assignments, risk thresholds и connector settings образуют связанную конфигурацию, а не набор независимых текстовых файлов.

Если разрешить “просто переписать TOML и надеяться на лучшее”, то появляются следующие риски:

- невалидный конфиг ломает startup или runtime reload;
- один scope становится формально валидным, но конфликтует с другим;
- UI применяет unsafe change без понятного rollback path;
- `preflight` видит не тот config state, который реально используется;
- degraded incidents становятся непредсказуемыми;
- audit перестаёт объяснять, какая именно конфигурация была активна в момент события.

Для `v1` система обязана вести себя по принципу `fail sanely`: плохой кандидат-конфиг должен быть отклонён или автоматически откатан, а не превращать панель в архитектурный `kernel panic` 😼

## Решение

Принять архитектурную политику:

1. Все runtime-конфиги хранятся как scoped structured files, но применяются как единый composite config snapshot.
2. Любое изменение создаёт `candidate revision`, которая валидируется не только по своему scope, но и против полного набора активных конфигов.
3. Система обязана хранить `last-known-good` snapshot и rollback path.
4. Невалидный кандидат не становится active config.
5. Если уже применённая конфигурация приводит к runtime failure, система обязана попытаться откатиться к `last-known-good`.
6. Если rollback не восстанавливает safe state, runtime обязан войти в `degraded`.
7. UI может менять только user-safe subset параметров.
8. Секреты запрещено хранить в versioned scoped config files.

## Канонические config scopes

Для `v1` обязательны следующие scope-файлы:

- `app.toml`
- `runtime.toml`
- `connectors.toml`
- `models.toml`
- `strategies.toml`
- `schedules.toml`
- `risk.toml`

Каждый scope имеет отдельную schema validation, но итоговая применяемая конфигурация считается полной только после composite validation.

## Config storage model

### XDG layout

Runtime-конфиги должны жить в XDG-friendly layout:

- `~/.config/clay-mission-control/` — active config scopes и metadata
- `~/.local/state/clay-mission-control/` — audit, apply results, rollback incidents

Planning-документы в Obsidian/Git не являются runtime-config storage.

### Revision model

Система обязана оперировать не только “текущими файлами”, но и revision-сущностями:

- `active revision`
- `candidate revision`
- `last-known-good revision`
- `revision history`

Даже если пользователь меняет только один scope, на apply создаётся новый полный snapshot состояния.

## Validation pipeline

### Уровень 1. File integrity

Проверяется:

- файл читается;
- формат корректен;
- TOML синтаксис валиден.

Провал на этом уровне:

- apply немедленно отклоняется;
- active config не меняется;
- runtime не переходит в degraded только из-за отвергнутого candidate.

### Уровень 2. Schema validation

Проверяется:

- типы полей;
- обязательные поля;
- диапазоны значений;
- enum-значения;
- структура вложенных объектов.

Провал на этом уровне:

- apply отклоняется;
- UI получает структурированную причину;
- в audit пишется rejected config attempt.

### Уровень 3. Cross-scope validation

Проверяется совместимость между scope:

- strategy profile ссылается только на существующие сущности;
- model assignment указывает только на зарегистрированные модели/роли;
- connector references согласованы с model provider requirements;
- risk settings совместимы с runtime rules;
- schedules не конфликтуют с общим runtime-поведением.

Провал на этом уровне:

- candidate не активируется;
- система остаётся на прежней active revision.

### Уровень 4. Safety policy validation

Проверяется:

- изменение разрешено для текущей роли пользователя;
- поля входят в user-safe envelope;
- изменение не затрагивает запрещённые инженерные настройки;
- изменение допустимо для текущего runtime state.

Провал на этом уровне:

- apply отклоняется как unsafe;
- событие попадает в audit как policy rejection.

### Уровень 5. Runtime impact validation

Проверяется:

- требует ли изменение live apply, controlled reload или restart-sensitive path;
- можно ли применить его в текущем состоянии системы;
- нужен ли повторный `preflight`;
- должны ли отдельные managed services подтвердить, что приняли revision.

Провал на этом уровне:

- change может быть:
  - отклонён;
  - принят как staged, но не активирован немедленно;
  - переведён в режим `revalidation required`.

## Apply policy

### Каноническое правило

Никакой config scope не применяется прямой записью “поверх рабочего состояния”.

Правильный apply flow:

1. Пользователь или система создаёт candidate change.
2. Формируется полный candidate snapshot.
3. Выполняется весь validation pipeline.
4. Если validation успешен:
   - revision получает новый идентификатор;
   - candidate становится active;
   - предыдущая active revision становится `last-known-good` или уходит в history;
   - runtime публикует structured config-applied event.
5. Если validation или controlled reload провалены:
   - active revision не меняется или откатывается;
   - runtime публикует structured config-failed event;
   - при необходимости фиксируется incident.

## Config classes by runtime behavior

### A. Live-safe changes

Могут применяться без полной остановки сессии, если проходят safety validation:

- active strategy profile
- active model assignment среди уже доступных ролей
- confidence thresholds в safe envelope
- risk thresholds в safe envelope

Условие:

- affected services подтверждают reload или reread config;
- UI показывает, что revision применена.

### B. Controlled-reload changes

Можно применять только через controlled reload path:

- connector parameters
- session schedules
- runtime behavior settings
- параметры, влияющие на background/on-demand orchestration

Такие изменения:

- не должны silently применяться в боевом контуре;
- могут требовать `paused`, `pre_session` или `reconfiguring`.

### C. Restricted / engineer-only changes

Через UI не разрешены:

- secret paths
- OS-level paths
- storage backend type
- low-level transport settings
- internal service ids

Эти изменения допускаются только через инженерный слой и не входят в обычный операторский workflow.

## Secrets policy

Секреты не должны храниться в scoped config files, которые могут попасть в sync/Git.

Разрешённые источники:

- OS environment
- `.env`
- локальный secret file вне Git-synced project planning directory

Config validation должна уметь различать:

- секрет отсутствует как runtime dependency;
- секрет случайно записан в обычный config file.

Второй сценарий считается policy violation.

## Rollback policy

### Automatic rollback

Автоматический rollback обязателен, если:

- candidate прошёл file/schema validation, но провалил controlled reload;
- новый active revision делает critical service unusable;
- после apply runtime не может восстановить безопасный config state;
- `preflight` фиксирует active config как небезопасный для session admission.

### Manual rollback

Control API обязан поддерживать operator-triggered rollback к последней валидной revision.

### Rollback target

Каноническая цель rollback:

- предыдущая `last-known-good` полная revision, а не только один файл из затронутого scope.

Это нужно, чтобы не допускать полусостояния, где один файл уже новый, а остальные ещё из другой логической конфигурации.

## Связь с preflight и degraded mode

### Preflight

`Preflight` должен проверять не просто “есть ли файлы”, а что:

- active revision существует;
- active revision валидна;
- user-safe config применён;
- risk config загружен;
- revision не помечена как `revalidation required`.

Если изменение требует preflight before activation, система обязана:

- оставить change staged или перевести runtime в безопасный промежуточный режим;
- не пускать в `active_session`, пока preflight не пройден.

### Degraded mode

`Degraded` не должен включаться только из-за отвергнутого candidate config.

`Degraded` включается, если:

- уже active revision стала operationally unsafe;
- rollback не вернул safe state;
- critical service зависит от конфигурации, которую нельзя безопасно восстановить;
- runtime больше не может гарантировать честный normal mode.

## Audit requirements

Для каждого config action должно сохраняться:

- actor
- timestamp
- affected scopes
- revision id
- previous revision id
- validation result
- policy decision
- whether rollback happened
- rollback target revision
- whether revalidation or preflight is required

## Почему выбран именно этот вариант

Этот подход:

- совместим с `ADR-001` и runtime state machine;
- не даёт невалидному конфигу разрушить рабочий control plane;
- поддерживает user-safe UI editing без архитектурной анархии;
- делает `preflight` и `degraded mode` логически связными;
- даёт понятный audit trail для session review и incident analysis;
- сохраняет возможность постепенно расширять config system без смены базового контракта.

## Рассмотренные альтернативы

### A. Прямое редактирование active TOML без revision model

Отклонено.

Причины:

- высокий риск partial corruption;
- слабый rollback story;
- непредсказуемое поведение между scope.

### B. Валидация только по отдельным scope без composite snapshot

Отклонено.

Причины:

- не ловит cross-scope конфликты;
- слишком легко получить формально валидный, но operationally broken набор.

### C. Хранить всё в одной giant config file

Отклонено.

Причины:

- сложнее управлять scope;
- тяжелее безопасно разрешать UI-изменения;
- выше риск конфликтов и плохого UX.

## Последствия

### Положительные

- система получает предсказуемый config lifecycle;
- rollback становится first-class behavior;
- можно безопаснее проектировать config API;
- build-spec и implementation plans получают ясный контракт для config manager.

### Отрицательные

- растёт сложность config manager;
- нужен revision metadata layer;
- часть apply-path становится более многослойной, чем “просто сохранить файл”.

## Что теперь обязательно

- config manager обязан работать через revision lifecycle;
- `last-known-good` обязателен;
- invalid candidate не может silently стать active;
- rollback обязан быть явно доступен через control API;
- `preflight` должен учитывать revision validity;
- UI не должен изменять restricted config fields.

## Что это не запрещает

- позже добавить более сложную revision history;
- позже добавить signed config exports;
- позже расширить policy engine по ролям или режимам.

Но всё это должно сохранять базовый принцип:

плохой candidate config не ломает систему, а плохой active config имеет гарантированный путь отката.
