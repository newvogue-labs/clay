---
tags:
  - infra
---

# ADR-018: Pool-Health Degraded Mode (never-empty invariant)

- **Status:** Accepted
- **Date:** 2026-06-17
- **Driver:** S3c-3
- **Replaces:** —
- **Referenced by:** ADR-013 (provider pool schema), ADR-014 (write governance)
- **Renumbered:** был ADR-015 → ADR-018 (коллизия разрешена 2026-06-24; mc ADR-015 = «Degraded-mode AI-слоя» сохраняет 015)

## Context

`ConfigReconciler` / `ConfigWriter` конвейер записи (`shadow → apply_live`) гарантирует валидность
конфига (структура, router_settings, model_list) — *если* запись происходит. Но конвейер
**не защищает** от ситуации, когда пул провайдеров «выгорел» (0 здоровых ключей/деплоев):

- Render фильтрует `available` строки → пустой `model_list` → validate ловит →
  `ConfigValidationError`.
- Если validate пропустить (например, добавить `floor=0` как особый случай) → `model_list: []`
  будет записан → LiteLLM либо не стартует, либо все запросы падают с 503.

Это **худший возможный исход** на боевом — шлюз молча перестаёт работать. Никакой
здоровой модели не остаётся для failover.

Кроме того, есть **частичная деградация**: пусть `model_list` непуст, но конкретная
`model_name`, на которую ссылается `assignments` (role → model), упала до 0 деплоев.
Эта роль повиснет, хотя шлюз как целое жив.

## Decision

Вводим **never-empty invariant** как обязательный гард в `ConfigWriter.reconcile()`:

### 1. `evaluate_pool_health(rows, floor=1) → PoolHealth`

Чистая функция: считает `available_total` (сколько деплоев прошло фильтр `available`)
и `by_model_name` (распределение по `model_name`). Если `available_total < floor` —
`degraded: True`.

- `floor` по умолчанию **1** — конфиг без единой модели опаснее, чем отсутствие изменений.
- `floor` параметризуется для будущих нужд (например, порог «нужно минимум 2 провайдера
  для redundancy»).

### 2. Degraded-ветка в `reconcile()`

Перед любым write/restart:

1. **Если `degraded`** → 0 write, 0 restart, last-good не тронут → ERROR-лог с
   `available_total` и `by_model_name` → возврат `ApplyReport(status="degraded")`.
2. **Иначе** → normal flow.

Сигнал громкий (`logger.error`), потому что degraded-mode — операционное ЧП, требующее
внимания дежурного.

### 3. Классификация ошибок

| Ошибка | Тип | Причина | Действие |
|--------|-----|---------|----------|
| Пустой рендер | `DegradedModeError` | Пул выгорел, 0 здоровых | degrade + ERROR-лог |
| Битый config (нет router_settings) | `ConfigValidationError` | Баг в рендере | `status="failed"` (не degrade) |

Ключевое различие: `degraded` — *ожидаемое состояние* пула (ключи закончились, cooling,
dead). `failed` — *баг* в конвейере. Scheduler должен:
- на `degraded` — логировать и retry на следующем цикле (пул может восстановиться);
- на `failed` — логировать как баг, retry только если изменился код/данные.

### 4. Частичная деградация (design decision, НЕ кодится в S3c-3)

Если `model_name`, на который ссылается `assignments`, упал до 0 деплоев, **но другие живы**:
- `model_list` непуст → инвариант не нарушен → **пишем выживших**.
- WARN-лог с указанием «роль X осталась без деплоя».
- Полагаемся на LiteLLM fallback-цепи `minimax-m3→[minimax-m2.7, local-ollama]`.

Альтернатива (держать last-good-запись для исчезнувшего `model_name`, не трогать
чьи-то строки) — отклонена как over-engineering для MVP. Решение отложено до
фазы governance (ADR-014 / UI-фаза 2-3).

### 5. API: `ConfigWriter.reconcile()`

```python
def reconcile(
    self,
    rows: Sequence[DeploymentRow],
    *,
    floor: int = 1,
    force: bool = False,
    health_timeout: float = 15.0,
    health_interval: float = 1.0,
    clay_user: str = "clay",
    sudo_cmd: str = "sudo",
) -> ApplyReport:
```

Возвращает `ApplyReport` с полем `status ∈ {applied, noop, degraded, rolled_back, failed}`,
а также `available_total` и `by_model_name` для наблюдаемости.

## Consequences

- ✅ **Безопасность:** never-empty invariant гарантирует, что конвейер никогда не запишет
  конфиг без рабочих моделей.
- ✅ **Fail-loud:** degraded-ситуация логируется как ERROR, не тонет в INFO/DUBUG.
- ✅ **Last-good:** при degraded старый конфиг остаётся нетронутым — если пул восстановится,
  следующий reconcile подхватит изменения.
- ✅ **Scheduler-ready:** `reconcile()` никогда не крашится — scheduler вызывает
  его в петле без try/except обёртки.
- ⚠️ **Двойная валидация:** validate вызывается в reconcile и затем в apply_live —
  избыточно, но безопасно. Оптимизация — если захочется убрать дублирование — простая,
  но не срочная.
- ⚠️ **Полнота health-check:** `evaluate_pool_health` считает только количество
  рядов после фильтра, не качество (rpd_used, cooling_until). Для MVP достаточно;
  углубление — в фазе retention/observability.
