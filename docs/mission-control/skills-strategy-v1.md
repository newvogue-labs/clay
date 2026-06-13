> **Перенесено из `docs/planning/` (2026-06-13).** Апрельский артефакт планирования,
> сохранён как канон в mission-control. Историю происхождения см. git log --follow.

# Clay v1 — Skills Strategy

Дата: 2026-04-16
Статус: working skills strategy for implementation phase

## 1. Цель документа

Этот документ фиксирует, какие `skills` реально нужны проекту `Clay v1` во время реализации, а также как относиться к внешним skill-репозиториям и community workflow-идеям.

Главная задача:

- не превращать разработку в коллекционирование skills;
- использовать только те `skills`, которые реально улучшают качество проекта;
- удерживать правильный engineering workflow на протяжении всех волн реализации.

## 2. Главный принцип

Для `Clay` важнее не количество skills, а качество workflow:

- сначала прояснение задачи;
- затем план;
- затем ограниченная реализация;
- затем проверка;
- затем review;
- затем следующий шаг.

Если просто навесить много skills без дисциплины, получится не ускорение, а красиво оформленный хаос.

## 3. Skills, которые уже считаются основным ядром

### `brainstorming`

Использовать:

- перед новыми крупными модулями;
- перед архитектурными развилками;
- перед значимыми UX/API/AI decisions.

Почему:

- помогает не прыгать сразу в код;
- снижает риск скрытых предположений;
- особенно полезен там, где есть несколько разумных вариантов реализации.

### `create-plan`

Использовать:

- когда нужен детальный инженерный план;
- для крупных архитектурных или phased-delivery задач.

Почему:

- помогает принимать decision-complete решения;
- особенно полезен для новых подсистем и крупных integration contours.

### `writing-plans`

Использовать:

- после spec/build-spec;
- перед реальной реализацией крупных блоков.

Почему:

- даёт execution-grade decomposition;
- помогает переводить архитектуру в конкретные file/task/test steps.

### `concise-planning`

Использовать:

- для коротких рабочих чеклистов;
- для локальных iteration plans внутри эпика.

Почему:

- не всегда нужен огромный plan;
- хорошо подходит для малых scoped tasks.

### `ai-agents-architect`

Использовать:

- для `E5`;
- для provider abstraction;
- для role topology;
- для fallback/degraded design;
- для boundaries между AI and non-AI logic.

Почему:

- `Clay` — не просто CRUD-приложение;
- AI layer здесь должен быть спроектирован дисциплинированно, иначе потом начнётся религия “агент сам разберётся”.

### `agent-evaluation`

Использовать:

- для `E5`, `E6`, `E8`, `E9`, `E11`, `E12`;
- при проверке качества AI behavior;
- при design и review evaluation loops.

Почему:

- LLM behavior нельзя оценивать как обычную deterministic функцию;
- без evaluation discipline легко получить “выглядит умно, но в бою ведёт себя странно”.

### `rag-engineer`

Использовать:

- для `E10`;
- для retrieval design;
- для chunking/embedding/search quality вопросов.

Почему:

- knowledge layer имеет свою инженерную специфику;
- retrieval quality сильно влияет на usefulness всей research-поверхности.

## 4. Skills, которые использовать точечно

### `openai-docs`

Использовать:

- когда нужно уточнить детали OpenAI API;
- когда вопрос касается конкретных official model/API capabilities.

Почему:

- даёт актуальную информацию по официальной документации;
- помогает не строить архитектуру на устаревших догадках.

### `plugin-creator`, `skill-creator`, `skill-installer`

Использовать:

- только при явной необходимости создавать/ставить/обновлять skills или plugins.

Почему:

- это сервисные инструменты, а не основной development workflow.

## 5. Recommended skills by implementation wave

### Wave 1 — Foundation

- `brainstorming`
- `writing-plans`
- `concise-planning`

Применение:

- `E1`
- `E2`
- `E4`

### Wave 2 — Core analyst workflow

- `brainstorming`
- `writing-plans`
- `ai-agents-architect`
- `agent-evaluation`

Применение:

- `E3`
- `E5`
- `E6`
- `E7`

### Wave 3 — Validation and review

- `writing-plans`
- `agent-evaluation`
- `concise-planning`

Применение:

- `E8`
- `E9`

### Wave 4 — Extension and hardening

- `writing-plans`
- `agent-evaluation`
- `ai-agents-architect`
- `rag-engineer`

Применение:

- `E10`
- `E11`
- `E12`

## 6. Что мы думаем о внешних skill-репозиториях

### `openai/skills`

Роль для нас:

- официальный baseline-ориентир для Codex ecosystem;
- хороший источник совместимых и ожидаемых по стилю skills.

Вывод:

- использовать как **официальный reference**;
- не ожидать, что он один решит всю проектную дисциплину.

### `obra/superpowers`

Роль для нас:

- сильный reference по workflow discipline;
- особенно полезен как модель процесса: `spec -> plan -> execution -> review`.

Вывод:

- использовать как **методологический reference**;
- забирать идеи workflow, а не тащить весь ecosystem вслепую.

### Большие community mega-packs

Сюда относятся:

- крупные сборки под `Claude Code`;
- “everything” style repositories;
- наборы, которые пытаются закрыть все сценарии сразу.

Вывод:

- смотреть как на источник идей;
- не импортировать целиком на раннем этапе `Clay`;
- слишком высокий риск лишней сложности и смешения чужих предположений с нашей архитектурой.

## 7. Что рекомендуют опытные разработчики и почему это нам подходит

По внешним обсуждениям чаще всего повторяются такие принципы:

- planning важнее импровизации;
- маленькие батчи лучше гигантских задач;
- review обязателен;
- внешний validation полезнее самодекларации “готово”;
- свои repo-specific instructions часто полезнее общего marketplace.

Это хорошо совпадает с потребностями `Clay`, потому что проект:

- архитектурно плотный;
- multi-layer;
- чувствителен к деградации качества;
- требует explainability и operational discipline.

## 8. Нужны ли нам ещё внешние skills прямо сейчас

На старте реализации `Wave 1`:

- **нет, срочно не нужны**.

Почему:

- у нас уже есть сильное базовое ядро skills;
- planning у проекта зрелый;
- текущий bottleneck — не нехватка skills, а переход от planning к disciplined execution.

## 9. Что стоит сделать позже

После первых рабочих итераций имеет смысл создать собственные project-specific skills, например:

- `clay-wave-execution`
- `clay-runtime-foundation-checks`
- `clay-signal-review`
- `clay-demo-validation`
- `clay-degraded-readiness`

Это будет полезнее, чем импортировать десятки чужих универсальных skills.

## 10. Финальный verdict

Для `Clay v1` правильная стратегия такая:

- использовать компактное ядро уже имеющихся skills;
- опираться на `openai/skills` как на официальный reference;
- опираться на `superpowers` как на workflow reference;
- не тащить огромные внешние skill packs на раннем этапе;
- позже создать собственные repo-specific skills под реальные нужды `Clay`.

Итог:

**Current skills baseline is sufficient for implementation start.**
