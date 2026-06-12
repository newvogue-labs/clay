# Decisions

> **В Clay ADR не ведётся.** Папка оставлена пустой намеренно.

**Почему:**

В Clay **архитектурные решения** принимаются **архитектором** (Opus 4.8) и фиксируются в:

- `docs/planning/blueprint-v1.md`
- `docs/planning/tech-stack-v1.md`
- `docs/planning/execution-backlog-v1.md`
- `docs/planning/master-planning-review-v1.md`

**Агент** (M3 Free) — **исполнитель** task-packets, а не автор архитектурных решений.

## Где агенту искать архитектурный контекст

| Нужно | Где смотреть |
|---|---|
| Архитектурное решение (почему так) | `docs/planning/*-v1.md` |
| Текущее задание от архитектора | `.context/handoffs/current.md` |
| Что делал в прошлой сессии | `.context/reports/last.md` |
| Контекст проекта (стек, правила) | `.context/memory/project/*` |
| Что важного случилось | `.context/observations/YYYY-MM/obs-NNN.md` |

## Если нашёл что-то, что меняет архитектуру

Не пиши ADR. Вместо этого:

1. Зафиксируй в `.context/observations/YYYY-MM/obs-NNN.md` (type: `discovery` или `question`)
2. Сообщи архитектору через `.context/reports/last.md` (секция "Что нужно от архитектора")
3. Дождись нового task-packet

Если **твоя** находка касается не архитектуры, а **подхода к работе** (как писать код, что делать первым) — это `memory/feedback/`.
