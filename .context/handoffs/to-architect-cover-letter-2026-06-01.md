# Clay v1 — Architect Brief (Cover Letter)

> **Дата:** 2026-06-01
> **От:** Emma (оркестратор)
> **Кому:** Архитектор (Opus 4.8 / назначенная модель)
> **Тема:** запрос на следующий engineering wave
> **Приложение:** `to-architect-snapshot-2026-06-01.md` (1133 строки, 72K)

---

## 1. TL;DR

Проект **Clay** — локальная web-first панель для **ручной** торговли на Binance Spot, AI-assisted (hybrid alpha). Wave 1 (E1-E12) реализован, Alpha Operator Hardening завершён 2026-05-31. Все тесты зелёные (107 backend + 15 frontend).

Нам нужны от вас:
1. **Task-packet** на следующий engineering wave
2. **Ответы** на 15 вопросов в snapshot §13 (приоритет: Q3, Q4, Q5, Q1)

---

## 2. Схема ролей

```
┌─────────────────┐         ┌──────────────┐         ┌──────────────┐
│   АРХИТЕКТОР    │ ←─────→ │    EMMA      │ ←─────→ │    АГЕНТ     │
│   (Opus 4.8)    │ Emma    │  (посредник) │  Emma   │  (M3 Free)   │
└─────────────────┘         └──────────────┘         └──────────────┘
        │                          │                         │
        │                          │                         │
        ▼                          ▼                         ▼
   docs/planning/             .context/                 пишет код
   task-packets               (общая память)            по task-packet
   ADR-001..005
```

**Архитектор (вы):**
- Читаете `docs/planning/` (blueprint, execution-backlog, approved-stack, master-planning-review)
- Читаете `docs/development/handoff-2026-05-02.md` (runtime handoff)
- Выдаёте **task-packets** агенту (формат: цель, контекст, требования, ограничения, acceptance criteria, файлы)
- Принимаете архитектурные решения, оформляете ADR при необходимости

**Агент (M3 Free):**
- Исполнитель task-packets
- Пишет код **строго** на основе `docs/` + ваших task-packets
- Не принимает архитектурных решений — обращается к вам через handoff
- Ведёт `.context/state.md`, `.context/reports/last.md`, `.context/observations/`

**Emma (оркестратор, человек):**
- Единственный человек в контуре
- Копирует ваши ответы агенту, ответы агента — вам
- Хранит долгосрочную память в `.context/` (13 файлов, ~1 800 строк, развёрнута сегодня)
- Принимает финальные решения (коммиты, удаление/архивация файлов, deaddrop)

---

## 3. Механика взаимодействия

### Что вы получаете от Emma
- Этот cover letter + приложенный snapshot
- Reports от агента (`reports/last.md`) — что сделано
- Observations (`observations/2026-MM/obs-NNN.md`) — важные находки
- Вопросы агента (если нужна ваша помощь)

### Что Emma ждёт от вас
- **Task-packet** на следующий wave (по формату из snapshot §14, ask A)
- **Ответы на Q1-Q15** (snapshot §13, ask B) — особенно Q3, Q4, Q5, Q1
- Опционально: новые ADR (ask C), обновления `docs/planning/` (ask D), новые handoff'ы (ask E)

### Чего НЕ нужно делать
- ❌ Писать код напрямую (это работа агента)
- ❌ Вызывать tools/bash/git — вы в режиме planning/review
- ❌ Дублировать то, что уже в `docs/planning/`
- ❌ Менять `.context/` — это зона Emma + агента
- ❌ Делать silent switching / auto-execution (политика Clay)

---

## 4. Структура snapshot'а (что где)

`to-architect-snapshot-2026-06-01.md` — ваш главный документ:

| Секция | Что внутри | Приоритет чтения |
|---|---|---|
| §0 TL;DR | 7 главных открытий про дрейф стека | **must read** |
| §1-2 | Миссия, фактический стек (с расхождениями от `CLAUDE.md.bak`) | must read |
| §3-4 | Структура проекта, документация | skim |
| §5 | Эпики E1-E12 (таблица) | skim |
| §6 | **Alpha Operator** (главный фокус) | **must read** |
| §7-8 | Архитектура backend/frontend | skim |
| §9 | Тестирование | skim |
| §10 | Долги и риски (in-memory state, scheduler, ...) | **must read** |
| §11 | Точка остановки (handoff-2026-05-02) | must read |
| §12 | Варианты шагов (A-J waves) | **must read** |
| **§13** | **Q1-Q15 — вопросы к вам** | **must answer** |
| **§14** | **A-F — конкретные asks** | **must answer** |
| Приложения | Карта файлов, команды, что НЕ проверено | reference |

---

## 5. Что мы ожидаем в этом цикле

1. Прочитать snapshot (начните с §0, потом §6, §10, §12-14)
2. Ответить на **Q1-Q15** (хотя бы приоритетные)
3. Выдать **task-packet** на следующий engineering wave
4. Опционально: оформить новые решения как ADR, обновить `docs/planning/`

**Рекомендация Emma (из snapshot §12.3):** следующий wave = **A (persistence) → B (scheduler) → D (real-data rehearsal)**. Если согласны — выдайте task-packet на A. Если есть другое мнение — мы открыты.

---

## 6. Контакты

- Emma → передаст ваш ответ агенту в новой сессии
- Если нужны уточнения от агента — Emma спросит
- Snapshot временный, после прочтения можно удалить (или Emma перенесёт в `handoffs/archive/`)

Спасибо! 🐧
