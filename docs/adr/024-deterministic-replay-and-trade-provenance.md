# ADR-024: Deterministic Replay Harness + Trade Provenance

- **Status:** Proposed
- **Date:** 2026-06-25
- **Replaces:** —
- **Donor-ref:** —

## Context

Soak-акселерация упёрлась в отсутствие batch/backfill-механизма. Единственный путь накопить ≥30 demo-исходов для рекалибровки Kelly (ADR-020) — real-time: ~3.5-5 ч на 15 сессий. Это неприемлемо для итеративного цикла разработки.

Параллельно: validation replay (S-LIVE-DEMO-2 Part A) симулировал 38 trades, но они легли в отдельную таблицу `validation.validation_runs` и НЕ засчитались в калибровку. Разрыв validation↔calibration требует закрытия.

**Решение:** построить детерминированный replay-харнесс через настоящий сервисный слой (не bypass), с провенансом записей и data-scope изоляцией. Это одновременно бэктест-движок платформы и механизм ускоренного soak'а.

## Decision

### (a) Clock-Seam

Заменить все хардкоды `datetime.now(UTC)` на вызов инъектируемого Clock-протокола.

**Текущие точки (6 persist, 3 compute):**

| Файл | Строка | Поле | Тип |
|------|--------|------|-----|
| `session_control/service.py` | 264 | `started_at` | persist |
| `session_control/service.py` | 295 | `paused_at` | persist |
| `session_control/service.py` | 396 | `created_at` | persist |
| `demo_trading/service.py` | 75 | `recorded_at` | persist |
| `demo_trading/service.py` | 133 | `observed_at` | persist |
| `reliability/service.py` | 143 | `last_rechecked_at` | persist |
| `session_control/service.py` | 570 | cooldown calc | compute |
| `signal_engine/service.py` | 109 | staleness calc | compute |
| `reliability/service.py` | 64 | snapshot freshness | compute |

**Clock-протокол:**

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
```

Две реализации:
- **SystemClock** — `now() = datetime.now(UTC)` — prod-поведение неизменно
- **VirtualClock** — `now() = frozen_as_of + elapsed` — детерминированный ticks

Инъекция через конструкторы сервисов. `SystemClock` = default (0 тестов сломано).

### (b) Provenance — `source` Enum

Добавить колонку `source VARCHAR(16) NOT NULL` в `demo.demo_trade_records`.

**Допустимые значения (Python Literal):**
```python
ProvenanceSource = Literal["baseline", "live", "replay"]
```

- **baseline** — 20 frozen Ring 1 сделок (backfill при миграции)
- **live** — реальные операторские сессии (дефолт для prod)
- **replay** — детерминированные replay-сессии через харнесс

**Никаких PG ENUM** — следует существующему паттерну VARCHAR + Python Literal (как `OperatorAction`, `OutcomeStatus`).

### (c) Replay Harness

Replay-харнесс — **НЕ bypass.** Он дёргает те же сервисы (`SessionControlService.start_session`, `DemoTradingService.log_current_trade`, `IngestionCycleService.run_once`), те же репозитории, те же валидации.

Отличия от live-пути:
1. **VirtualClock** вместо SystemClock — `as_of` фиксирован
2. **Scope=replay** — запись с `source='replay'`
3. **Ретро-разрешение** — берёт forward-свечи из `market.market_bars` для stop/target

**Запуск:**
```python
# псевдокод
harness = ReplayHarness(
    clock=VirtualClock(as_of=datetime(...)),
    scope="replay",
    services=injected_services,
)
for tick in harness.walk(days=5, step=timedelta(hours=1)):
    if tick.signal:
        session = harness.start_session()
        harness.log_trade(session, action="entered")
        outcome = harness.resolve_later(session, bars=market_bars)
        harness.ingest_result(session, outcome)
```

### (d) Data-Scope Invariant

**Главный инвариант:** replay-записи НИКОГДА не контаминируют live-калибровку и не триггерят live-safety.

**Механизм:** все репозиторные методы, читающие `demo_trade_records`, получают опциональный параметр `source_filter: ProvenanceSource | None = None`.

| Метод | Default filter | С поведением `source_filter=None` |
|-------|---------------|----------------------------------|
| `list_all_trade_records()` | `None` → `WHERE source IN ('baseline','live')` | **622 тестов зелёные** (replay записей нет) |
| `list_resolved_window(hours)` | `None` → `WHERE source IN ('baseline','live') AND …` | То же |
| `list_ordered_recent(limit)` | `None` → `WHERE source IN ('baseline','live') AND …` | То же |
| `list_open_positions()` | `None` → `WHERE source IN ('baseline','live') AND …` | То же |

Когда харнесс запускает `compute_sizing_stats(scope="replay")`, он передаёт `source_filter="replay"` — видит только replay-записи. В live-режиме (дефолт) replay-записи невидимы.

Это закрывает разрыв validation↔calibration: replay-прогон идёт через те же таблицы, но живёт в своём скоупе.

## Как доказываем

### (i) Рекалибровка ≥30

1. Запустить replay-прогон, накопить ≥30 resolved исходов со `source='replay'`
2. Вызвать `compute_sizing_stats(scope="replay")` — dry-run
3. Наблюдать сдвиг p/b относительно текущих консервативных значений (Wilson interval сужается)
4. Убедиться, что `compute_sizing_stats(scope="live")` вернул прежние значения (изоляция)

### (ii) L2/L1 блок

1. В replay-скоупе сконструировать 3 последовательных loss-записи с `source='replay'`
2. Вызвать `start_session()` → preflight в replay-режиме проверяет replay-scope records
3. L2 cooldown (3 losses, 60 min) детерминированно блокирует старт → hard_fail
4. Убедиться, что в live-скоупе `start_session()` НЕ блокируется (replay-записи не видны)

## Scope и Non-Goals

### In scope
- Clock-seam (SystemClock / VirtualClock)
- Provenance-миграция 0020 + backfill (baseline=20, live=1)
- Scope-параметр в репозиториях (default=live)
- Replay-харнесс (детерминированный)
- Replay-прогон на исторических свечах
- Доказательства: калибровка dry-run + L2 блок

### Non-goals / deferred
- Real-money исполнение
- Авто-рекалибровка по триггеру (live threshold)
- UI для replay
- Параллельный replay (multi-symbol)

## Разбивка на impl-слайсы

| Слайс | Описание | Зависимости | Оценка |
|-------|----------|-------------|--------|
| **S-REPLAY-2** | Clock-seam: `Clock` protocol, `SystemClock`, `VirtualClock`, инъекция в 6 сервисов. Все 622 тестов зелёные. | — | |
| **S-REPLAY-3** | Provenance-миграция 0020: `ADD COLUMN source`, backfill (20→baseline, #22→live), `list_all_trade_records()` → filter by source. | — | |
| **S-REPLAY-4** | Scope-параметр: `source_filter` во всех repo-методах + `_compute_sizing_stats` + `_build_preflight`. Default=`live`. 622 тестов зелёные. | S-REPLAY-3 (колонка) | |
| **S-REPLAY-5** | Replay-харнесс: `ReplayHarness` + VirtualClock + retro-resolution + entry point. | S-REPLAY-2 (clock), S-REPLAY-3 (provenance), S-REPLAY-4 (scope) | |
| **S-REPLAY-6** | Soak-прогон: ≥30 replay-исходов, calibration dry-run, L2/L1 block proof. | S-REPLAY-5 | |

**Порядок:** S-REPLAY-2 + S-REPLAY-3 параллельно, затем S-REPLAY-4, затем S-REPLAY-5, затем S-REPLAY-6.

## Открытые вопросы

1. **VirtualClock.dt() vs VirtualClock.now()**: заморозить as_of или тикать? Для детерминизма — заморозить. Но preflight считает cooldown от `now` — если as_of заморожен, cooldown никогда не истечёт. Решение: VirtualClock имеет `.tick(delta)` для пошагового продвижения.

2. **Retro-resolution**: харнесс после записи `entered` должен дождаться forward-свечей для stop/target. Проще всего: при `source='replay'` хранить `entry_price`, а `resolve_later` читает бары после `recorded_at` из `market.market_bars`. 23.5 дня данных хватит на 15+ сессий по всем символам.

3. **Alembic-коллизия 019/022**: ADR-024 использует номер 024 (019/022 зарезервированы под доноров, 023 занят). Миграция — 0020.
