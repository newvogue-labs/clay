# Clay Development Docs

Дата: 2026-05-02
Статус: локальный documentation hub рядом с проектом

## Назначение

Эта папка теперь хранит основные документы разработки рядом с рабочим репозиторием `Clay`, чтобы не восстанавливать контекст из Obsidian, Codex sessions и разрозненных handoff-файлов каждый раз заново.

## Разделы

- `planning/` - минимальный набор planning-документов, который уже был импортирован в implementation repository.
- `mission-control/` - полный snapshot папки `CLAY_Mission_Control` из Obsidian.
- `development/` - handoff-документы, текущий статус разработки, точки остановки и следующие шаги.

## Источник Snapshot

Полная копия Mission Control взята отсюда:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/`

Копия в репозитории:

`/home/emma/Projects/clay/docs/mission-control/`

Оригинал в Obsidian не удалялся и не изменялся.

## Текущая Точка Входа

Начинать новый development-pass лучше отсюда:

`/home/emma/Projects/clay/docs/development/handoff-2026-05-02.md`

Этот handoff фиксирует восстановленную точку остановки, актуальные WIP-изменения и ближайшие безопасные шаги.

## Правило Обновления

Если Obsidian-документы меняются, обновлять snapshot в `docs/mission-control/` нужно осознанно: повторно скопировать измененные Markdown-файлы и обновить handoff. Это лучше, чем держать скрытую зависимость от внешней папки.
