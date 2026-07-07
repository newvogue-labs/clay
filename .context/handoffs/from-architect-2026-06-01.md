---
date: 2026-06-01
from: architect
status: A4 — accepted 2026-06-01; A5 — accepted 2026-06-01; A5.5 — accepted 2026-06-01; A6 — issued 2026-06-01, pending report
source_of_truth: Architect Working Log (Notion, owned by Emma); local copy kept for continuity
---

# Wave A / Slice A4 — Verdict (verbatim, 2026-06-01)

## Architect verdict on A4 (verbatim)

**A4 принят ✅** — 163 зелёных, thread `session` в 2 call-site (без правок семантики), discriminator fail-fast для session_state отлично ловит corrupted rows. Обновляй `handoffs` → A4=accepted. Лог обновлён.

### Ответы Emma на 3 вопроса

1. ✅ **A4 принят.** Обновляй `handoffs` → A4=accepted.
2. ✅ **Коммиты: 3 (или 4 с A5.5).** Финальное ОК на сам коммит — после зелёного `pytest` всей серии.
3. 📨 **Сначала A5, потом A5.5, потом A6.** Один план не валит другие: A5 закрывает 3 singleton (workspace/strategy/reliability), A5.5 закрывает D2 (model_assignment route), A6 — финал (integration restart-survival по всем 6 таблицам + runtime_manager reconciliation).

### 5 фиксов и обходов, за которые Emma дала ОК

- **D1 fix в `workspace._build_snapshot`** — guard `if self._focus_source == "system_recommendation":` перед auto-pick. Минимальный, поведение system-recommendation не меняется.
- **Runtime_manager reconciliation отложен в A6** — A4 не трогает runtime_manager (A4 persistence scope: session_state).
- **Demo_trading / session_review — НЕ thread session в A4** — они не write-through на runtime_state. A5/A5.5 thread где нужно.
- **Discriminator fail-fast (sibling required fields)** — `session_id is None` → нет сессии; иначе sibling required fields required, иначе `ValueError`. Ловит corrupted rows (manual psql / future bug).
- **`pending_created_at` (A4 follow-up #2)** — добавлен в pending_* required field set, иначе `ValueError`. Закрывает subtle inconsistent-row failure mode.

### Следующий: A5 (3 простых singleton)

`workspace_focus` / `strategy_state` / `reliability_state` — все singleton, write-through по паттерну A3+A4. **Plus D1 fix** на workspace.

### 📝 Отчёт — обязательный шаблон (как A3)

В §2 обязательно: **две транзакционные границы**, точка restore, **полный список write-through call-sites** (все методы-мутаторы session_control), и **как `session` протаскивается через внутренних вызывающих** (demo_trading и пр.). Если кто-то из вызывающих мутирует сессию без request-`Session` — **не угадывай, вынеси в §6**. §4 — `pytest`.

---

⚠️ **Вероятная сложность A4:** `session_control` дёргают другие сервисы (`demo_trading`, будущий scheduler из Wave B), а не только HTTP-роут. Если внутренний путь не имеет request-сессии — пусть агент опишет это в §6 как открытый вопрос, а не подгоняет (можно через `session_factory` для внутренних путей, но это решаю я). При необходимости пришли `session_control/service.py` — уточню точечно.

Дальше после A4 — **A5** (3 простых singleton: `workspace` + `strategy` + `reliability`).

---

# Wave A / Slice A5 — Verdict & Task packet A5.5 (verbatim, 2026-06-01)

## Architect verdict on A5 (verbatim)

**A5 принят ✅** — 179 зелёных, D1 решён правильным guard'ом (на `_focus_source`), D2 чисто изолирован комментарием + isolation-тестом. Лог обновлён (A5 закрыт, A5.5 выдан, план коммитов → 4 логических).

### Ответы Emma на 3 вопроса

1. ✅ **A5 принят.** Обновляй `handoffs` → A5=accepted.
2. ✅ **Коммиты: 4** (выделенный A5.5 = 4-й). Итог Wave A: `db` / `ai_control` / `session+workspace+strategy+reliability` / `model_assignment-fix`. Финальное ОК на сам коммит — после зелёного `pytest` всей серии.
3. 📨 **Сначала A5.5, потом A6.** Закрываем долг durability до интеграционных тестов — тогда A6 покроет рестарт-выживание и для model_assignment-пути «из коробки».

---

## TASK-PACKET — Wave A / Slice A5.5

**D2 fix: `validation_lab.apply_activation('model_assignment')` → персист через ai_control**

[см. полную формулировку в deaddrop.md]

### Агент принял путь **B** (новый `set_assignment`).

5 аргументов:
- Семантическая чистота (operator-review vs internal promotion)
- Pending state pollution (мигание state в одной транзакции)
- Preflight hard_fail как новый failure mode
- `last_reviewed_at` pollution (activation ≠ operator review)
- Минимальный API drift (+1 явный метод)

---

# Wave A / Slice A5.5 — Verdict & Task packet A6 (verbatim, 2026-06-01)

## Architect verdict on A5.5 (verbatim)

**A5.5 принят ✅** — путь B реализован чисто: `set_assignment` с event-topic под `apply_assignment` (единый refresh), `last_reviewed_at`/`pending_review_*` не тронуты, контракт `apply_activation` неизменен, isolation 7/7. **D2 закрыт.** Весь persistence-код Wave A готов (184 зелёных). Закрываю A5.5 в логе и выдаю финальный **A6**.

### Ответы Emma

1. ✅ **A5.5 принят.** Все 7/7 acceptance + критерии выполнены.
2. ✅ **Коммиты: 4 → 5 (A6 = 5-й и 6-й).** Тонкость — `set_assignment` физически в `ai_control/service.py`, так что его тело можно положить в коммит #2 (ai_control), а в #4 оставить только call-site validation_lab + тесты. Разнести через `git add -p`. Если возиться лень — клади весь A5.5 одним коммитом #4, тоже собирается.
3. 📨 **Передавай — вот финальный A6.** Это последний слайс Wave A.

**Долги закрыты: D1 ✅ (A5), D2 ✅ (A5.5).** Весь persistence-код готов — осталось доказать, что всё это переживает рестарт end-to-end.

---

## TASK-PACKET — Wave A / Slice A6 (финал)

**Integration restart-survival + `runtime_manager` реконсиляция + `build_alpha_bundle` sync**

### 🎯 Цель

Закрыть Wave A: доказать сквозное выживание рестарта по всем 6 таблицам **в одном интеграционном сценарии** (не unit-per-service, как A2–A5, а полный bootstrap→мутации→новый bootstrap) и устранить последнее известное A4-ограничение — восстановленная активная сессия не должна презентовать ложный `lifecycle_state = "review"`.

### ⚠️ Gated: recon → plan → ОК → implement

A6 трогает **кросс-сервисное** состояние (`runtime_manager` ↔ восстановленный `session_state`) — это самая рискованная часть. **Сначала recon + план, до edit'ов.**

### 🔧 Объём работ

1. **Integration restart-survival suite** (NEW, `tests/integration/test_restart_survival.py`): полный контекст приложения с реальным file-based SQLite (`.tmp/`), репрезентативные мутации **по всем сервисам**.

2. **`runtime_manager` реконсиляция:** правило выводится в плане.

3. **`build_alpha_bundle` sync** — привести в соответствие с новым persisted-state shape.

### 🔬 Acceptance

1. `pytest -q` зелёный (184 + integration).
2. Сквозной сценарий: один тест мутирует все 6 областей → рестарт → все восстановлены.
3. Восстановленная активная сессия → `lifecycle_state` отражает реальное состояние.
4. `build_alpha_bundle` / alpha-readiness тест зелёный.
5. Все A1–A5.5 тесты зелёные.

**Старт:** recon + план до edit'ов. После A6 — **Wave A закрыта**, переход к Wave B (scheduler, ADR-007).

---

# Wave A / Slice A6 — Recon findings (от агента, 2026-06-01, до edit'ов)

## 🔴 Critical finding: production-баг двойной инициализации в `bootstrap.py`

`bootstrap.py` содержал двойную инициализацию (lines 154-193 перезаписывали часть сервисов). Точная диагностика:

| Сервис | 1-й блок | 2-й блок | Эффект |
|---|---|---|---|
| `ai_control_service` | ✅ factory | нет | OK |
| `workspace_service` | ✅ factory | нет | OK |
| `session_control_service` | ✅ factory | ✅ factory (line 161) | Косметический дубль |
| **`validation_lab_service`** | ✅ factory | ❌ **БЕЗ factory** | **🔴 NOT persistent** |
| **`reliability_service`** | ✅ factory | ❌ **БЕЗ factory** | **🔴 NOT persistent** |
| `alpha_readiness_service` | нет | ✅ собирается на 2-х дублях | **🔴** non-persistent зависимости |

**A3+A4+A5 wiring работал в тестах, но НЕ в production** (alpha_readiness_service читал non-persistent копию). Integration suite это поймал до релиза.

## 4 правки от Emma (post-recon, для A6)

1. **Хирургический bootstrap-фикс** — не bulk-delete, только 2 бага-дюбля + сохранить `demo_trading`/`session_review`
2. **Integration suite через production factory** — `build_services(session_factory)` общий для prod и suite (иначе suite не поймал бы этот баг)
3. **Reconcile через FSM-multihop** (потом скорректировано на `reconcile_to` — см. ниже)
4. **`_build_lifecycle` / `build_alpha_bundle` не трогаем** — reconcile как входной фильтр; in-memory alpha-тесты by design

## Path-selection для reconcile (post-recon уточнение)

После recon `transitions.py` показал, что `BACKGROUND_MONITORING → ACTIVE_SESSION/PAUSED` **напрямую ЗАПРЕЩЕНЫ** (FSM). Multihop через `PRE_SESSION` возможен, но дёргает `_assert_critical_services_ready()` → может уронить bootstrap если registry not ready.

**Решение: новый `RuntimeManager.reconcile_to(state)` (прямое присваивание, boot-safety by design).** Аргумент — "восстановление сессии — факт, а не запрос на старт". Validate transition (path + readiness gate) — контракт *смены режима оператором*. Restore проецирует уже-существовавшее состояние.

## Boot-safety check + 2 guard'а на реализацию (от Emma)

1. **`reconcile_to` whitelist-guard** — принимает только `{ACTIVE_SESSION, PAUSED}`. На остальное — `ValueError`. Это restore-примитив, не backdoor-сеттер.
2. **Reconcile проецирует только session-lifecycle, не service-health.** Health — отдельная ось (Wave B / ADR-007). Не вшивать health-гейтинг в reconcile.
3. **4-й тест** — `test_reconcile_boot_safe_when_critical_services_not_ready` (registry=NOT_READY, reconcile работает, не RuntimeError).

## План принят Emma

- 2 коммита для A6 (Wave A = 5 логических)
- `build_services(config_loader, session_factory=None)` factory
- `reconcile_to` + whitelist `{ACTIVE_SESSION, PAUSED}`
- 4 integration теста (full-survival + reconcile-active + reconcile-paused + boot-safety)
- delta: 184 → 188+

После зелёного A6 — **Wave A закрыта**, переход к Wave B (scheduler, ADR-007).
