# ADR-024: Deterministic Replay Harness + Trade Provenance

- **Status:** Accepted
- **Date:** 2026-06-26
- **Supersedes:** Proposed (2026-06-25)
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

## ✅ Proof (S-REPLAY-6, 2026-06-26)

### Synthetic тесты (test_soak.py, SQLite)

Прогон на SQLite: 2000 баров SOLUSDT 1h, START_AS_OF=2026-06-02 00:00 UTC.

- `test_full_soak`: ≥30 sessions, p/b recalibrated, default frozen, isolation ✅
- `test_l2_loss_streak_blocks_replay_session`: 3 replay-loss → hard_fail ✅
- `test_l2_cooldown_guard_detects_clock_desync`: recorded_at ahead of clock → ValueError ✅

### Real-data soak (soak_5433.py, прод-5433)

Подлинныйvalidation на реальных барах SOLUSDT 1h из 5433, Jun 2–25.
583 бара, VirtualClock, MarketRepository патчен clock-aware для
фильтрации freshness по текущей позиции часов.

```
soak_5433.py — real 5433 data (583 SOLUSDT 1h, Jun 2–25 06:59 → Jun 26 12:59)
  sessions_started: 62   (≥30 threshold surpassed)
  trades_resolved:  61   (1 unresolved = forward buffer, correct)
  W/L:               42W / 19L  (реальный W/L mix, НЕ синтетик 976W/0L)
  replay p/b:
    before:  p=0.00000  b=1.00000  ev=-1.00000   (fallback, 0 записей)
    after:   p=0.56408  b=1.30950  ev=0.30275    (62 записей, Wilson + Kelly)
    ✅ p пересчитан (0 → 0.564), b пересчитан (1.0 → 1.309, НЕ fallback)
  default-scope (baseline=20W/7L, live=1L):
    before:  p=0.40878  b=1.61910  ev=0.07064
    after:   p=0.40878  b=1.61910  ev=0.07064   (byte-identical, заморожен ✅)
  isolation: replay_ids ∩ default_ids = ∅  ✅
  clock-desync guard: 3 replay-loss с recorded_at = now+2h → ValueError (7200s ahead) ✅
```

### (i) Рекалибровка ≥30

- `summary.sessions_started = 62` — подтверждено (SQLite: 977, но те же code path)
- `trades_resolved = 61` — все трейды разрешены (1 unresolved — forward buffer)
- `replay_before[0] == 0.0, replay_after[0] = 0.56408` — p recalibrated на реальных W/L
- `replay_before[1] == 1.0, replay_after[1] == 1.3095` — b_emp пересчитан (критично!)
- **default-scope p/b заморожен:** `default_before == default_after` (R6 выполнен)
- **b_emp реально пересчитан:** avg_win / avg_loss для 42W/19L ≠ 1.0 (согласно доказательству)

### (ii) L2/L1 блок (2 доказательства)

**a) Изолированный тест** (`test_l2_loss_streak_blocks_replay_session`):
- 3 replay-loss записи в replay-скоупе → `build_snapshot(for_start=True)` →
  L2 (`risk-limit-cooldown`) = `hard_fail` c `blocks_start=True`
- `start_session()` кидает ValueError

**b) В составе soak** (5433 real data):
- Соак прошёл на реальных данных Jun 2–25, 42W/19L, 19 потерь всего
- Естественного loss-streak ≥ 3 внутри 30-мин cooldown окна **не возникло**
- L2 статус = "ok" (коoldown не сработал, что корректно для данного окна)
- **Важно:** L2-механика доказана синтетическим тестом (a), на реальных данных
  distribution потерь не дало 3 consecutive — это честный результат, не отсутствие теста

### (iii) Изоляция под нагрузкой

- `bl_before == bl_after` — baseline (20) + live (#22, 1L) байт-в-байт целы
- `default_ids.isdisjoint(replay_ids)` — replay-записи (62) не просачиваются
  в default scope (scope isolation, ADR-024 §(d))
- 62 replay записей в 5433 подтверждают масштаб soak'а

### (iv) Clock-desync guard (урок)

В процессе доказательства обнаружен корень «data-freshness блокирует L2»:

| Вердикт | Описание |
|---------|----------|
| **Было** | Два независимых VirtualClock: сервисы (заморожен Jun 2) vs харнесс (двигается) → `(now - streak_ts)` = negative → cooldown всегда active → L2 silent hard_fail |
| **Фикс** | Один VirtualClock на все сервисы + ReplayHarness (тестовая фикстура) |
| **Guard** | Прод-код: если `recorded_at > now + 60s` → `ValueError("clock desync: ...")` — Structural backstop для clock-seam инварианта |

Регресс-тест: `test_l2_cooldown_guard_detects_clock_desync` (3 replay-loss с
`recorded_at > services_clock.now()` → guard raise).
См. `session_control/service.py:578-585`.

### (v) Вердикт принятия

Решение ADR-024 подтверждено:

1. ✅ **Clock-seam** — VirtualClock в harness (M226). Guard на clock-desync (M227)
2. ✅ **Provenance** — миграция 0020 + `source` filter во всех repo-методах (M222)
3. ✅ **Scope изоляция** — replay vs default не пересекаются
4. ✅ **Replay harness** — финальный прогон через backend-сервисы
5. ✅ **Soak ≥30** — p/b recalibrated, isolated от live
6. ✅ **L2/L1 block** — 3 losses → hard_fail в replay-scope

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
