---
id: obs-2026-06-01-001
type: discovery
date: 2026-06-01
session: context-init-2026-06-01
files:
  - .context/
  - AGENTS.md
tags: [memory, context, system-setup, workflow]
---

**Что случилось:**

В Clay развёрнута vendor-agnostic система памяти `.context/` (по шаблону `~/.opencode/templates/agent-context-template.md`).

Восстановлено из `~/Projects-Backups/clay-2026-06-01-pre-context/hot/`:
- `CLAUDE.md.bak` → `memory/project/{project-overview,tech-stack,ai-rules}.md`
- `runbook-002-alpha-*.md` → `memory/project/runbooks.md`
- `README.md` (Clay) → `state.md`, `roadmap.md`, `architecture.md`

**Наблюдение (важное для будущих агентов):**

В Clay `.context/decisions/` **намеренно пуста** — ADR не ведётся, потому что:

1. **Архитектор** принимает архитектурные решения и фиксирует их в `docs/planning/*-v1.md`
2. **Агент** — исполнитель task-packets, не автор архитектуры
3. `.context/` — это **continuity между сессиями**, а не архив архитектурных решений

Если найдёшь что-то, что меняет архитектуру → пиши в `observations/` (type: `discovery`/`question`) + сообщи архитектору через `reports/last.md`. Не пиши ADR.

**Why:**

Если `.context/decisions/` будет пустой без объяснения — будущий агент может решить "надо бы вести ADR" и начать плодить файлы. Эта запись фиксирует **workflow Clay**:
- docs/ → архитектура (архитектор пишет)
- handoffs/ → входящие задания
- reports/ → исходящие отчёты
- memory/ → долгосрочный контекст (стек, правила, runbook'и)
- observations/ → важные находки

**How to apply:**

- Читай `docs/planning/*-v1.md` для архитектуры, **не** `.context/decisions/`
- Читай `.context/state.md` для текущего момента
- Читай `.context/handoffs/current.md` для задания
- После работы обнови `state.md` + `reports/last.md`
- Если меняется **подход к работе** (а не архитектура) — пиши в `memory/feedback/`
- Если нашёл баг/несоответствие — пиши в `observations/`

**Связанные записи:**

- [decisions/README.md](../decisions/README.md) — почему нет ADR
- [memory/MEMORY.md](../memory/MEMORY.md) — индекс памяти
- [state.md](../state.md) — текущее состояние
