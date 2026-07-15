# Handoff Prompt Template

> **Переиспользуемый шаблон** для генерации промпта-перехода между сессиями.
>
> **Когда использовать:** Emma пишет "переходим к новой сессии" / "завершаем сессию" / "session handoff".
>
> **Как использовать:** агент подставляет значения в `{{...}}` плейсхолдеры и выдаёт Emma готовый промпт для копирования.

## Шаблон

```text
Продолжаем работу в {{project_path}} ({{project_name}}).

Перед началом прочитай (в этом порядке):
1. {{project_path}}/.context/AGENTS.md — правила проекта
2. {{project_path}}/.context/state.md — горячее (что в работе, где остановились)
3. {{project_path}}/.context/handoffs/current.md — задание от архитектора{{extra_files_block}}

Сейчас: {{state_summary}}
Следующий шаг: {{next_step}}{{pending_question}}
```

## Плейсхолдеры

| Плейсхолдер | Откуда брать | Описание |
|---|---|---|
| `{{project_path}}` | константа | абсолютный путь к проекту |
| `{{project_name}}` | из README | короткое имя |
| `{{state_summary}}` | `state.md` секция "Что в работе" + "Блокеры" | 1-3 строки текущего момента |
| `{{next_step}}` | `state.md` "Следующий шаг" + конец `reports/last.md` | что конкретно делать |
| `{{pending_question}}` | `handoffs/` (если есть) или observations/ | что ждём от кого (архитектор / Emma) |
| `{{extra_files_block}}` | зависит от ситуации | какие ещё файлы критичны (recon, snapshot, конкретный домен) |

## Когда добавлять `{{extra_files_block}}`

- Есть активный `recon-*.md` в `handoffs/` → добавить: " и `handoffs/recon-YYYY-MM-DD.md`"
- Есть непрочитанный snapshot для архитектора → не нужен агенту, НЕ добавлять
- Есть конкретный эпик в работе → добавить: " и `memory/project/ai-rules.md`" или другой конкретный
- В работе конкретный баг → добавить: " и `observations/2026-MM/obs-NNN-bug-name.md`"

## Когда добавлять `{{pending_question}}`

- Ждём ответа архитектора → " Жду ответа от Emma (task-packet от архитектора в `handoffs/current.md`)"
- Есть открытый вопрос к Emma → " Открытый вопрос к Emma: ..."
- Нет вопросов → оставить пустым

## Готовый пример (для текущей сессии)

```text
Продолжаем работу в /home/emma/Projects/clay (Clay — trading workspace).

Перед началом прочитай (в этом порядке):
1. /home/emma/Projects/clay/.context/AGENTS.md — правила проекта
2. /home/emma/Projects/clay/.context/state.md — горячее (что в работе, где остановились)
3. /home/emma/Projects/clay/.context/handoffs/current.md — задание от архитектора
4. /home/emma/Projects/clay/.context/handoffs/recon-a0-2026-06-01.md — отчёт A0

Сейчас: Wave A (persistence), Slice A0 recon завершён, baseline 107 passed.
Следующий шаг: ждать task-packet A1 (DDL для persistence) от архитектора через Emma.
```

## Чеклист перед выдачей промпта Emma

- [ ] `state.md` обновлён (что в работе актуально)
- [ ] `reports/last.md` заполнен (что сделано)
- [ ] При необходимости — `observations/YYYY-MM/obs-NNN.md` создан
- [ ] Промпт содержит только то, что **нужно агенту** для старта
- [ ] Промпт **короткий** (≤15 строк)
- [ ] Нет ссылок на snapshot для архитектора (это не для агента)
- [ ] Нет ссылок на личные файлы Emma (deaddrop и т.д.)
