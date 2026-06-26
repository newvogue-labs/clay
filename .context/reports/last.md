# Отчёт: сессия 2026-06-26 — S-REPLAY-6 доводка на реальных данных 5433

## Что сделано

### S-REPLAY-6 — Real-data soak 5433 + guard + commit (ГОТОВ ✅)

#### Диагноз (шаг 0)
- **Корень S-REPLAY-6:** два независимых VirtualClock в soak-фикстуре.
- Фикс: один `clock` для сервисов и ReplayHarness (test_soak.py:219).
- Guard: `session_control/service.py:578-585` — если `recorded_at - now > 60s` → `ValueError`.

#### Soak на реальных данных 5433 (soak_5433.py)
- **Проблема:** `MarketRepository.list_latest_bars` читает LATEST 50 баров из БД.
  На реальных данных в 5433 latest = Jun 26, а harness clock = Jun 2 →
  freshness evaluator → all signals "invalidated" → 0 trades.
- **Фикс:** патч `MarketRepository` для фильтрации по `clock.now()`.
  Pre-grouped bars by (symbol, timeframe), sorted desc.
- **Результаты (real SOLUSDT 1h, 583 бара, Jun 2–25):**
  - sessions_started: **62** (≥30 ✓)
  - trades_resolved: **61** (1 unresolved = forward buffer)
  - W/L: **42W / 19L** (реальный W/L mix!)
  - replay p/b:
    - before: **p=0.00000, b=1.00000, ev=-1.00000** (fallback)
    - after: **p=0.56408, b=1.30950, ev=0.30275** (реальная рекалибровка!)
  - default-scope: **p=0.40878, b=1.61910** byte-identical before/after ✅
  - isolation: `default_ids.isdisjoint(replay_ids)` ✅
  - L2 естественно: **19 потерь** в replay-scope (но нет 3 consecutive в cooldown окне → status=ok)
  - clock-desync guard: **сработал** — 7200s ahead detected ✅
- Soak завершён за ~960 сек (~16 мин) на PG.

#### Тестовое покрытие
- `test_soak.py` — **закоммичен** (tracked, 3 tests: 1 slow + 2 regular)
- `soak_5433.py` — **закоммичен** (standalone soak на 5433, non-pytest)
- `test_l2_cooldown_guard_detects_clock_desync` — guard регресс, regular speed
- `test_l2_loss_streak_blocks_replay_session` — L2 hard-block proof, regular speed
- `test_full_soak` — slow (2000 синтетических баров на SQLite)
- test counts: **669 excl slow** / **670 incl slow** (закоммичено)

#### ADR-024
- Обновлён Proof (i–v) с **реальными числами** из 5433 soak
- L2: честно отражено — 19 потерь, но no natural 3-consecutive в окне
- Guard: доказан на реальных данных

### Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `backend/tests/replay/test_soak.py` | Закоммичен (tracked) |
| `backend/tests/replay/soak_5433.py` | Standalone soak на 5433, clock-aware patch |
| `backend/src/clay/session_control/service.py` | Clock-desync guard + TZ coercion |
| `docs/adr/024-deterministic-replay-and-trade-provenance.md` | Accepted + real 5433 numbers |
| `backend/pyproject.toml` | `slow` marker registered |
| `.context/reports/last.md` | Этот отчёт |
| `.context/state.md` | S-REPLAY-6 → CLOSED, ADR-024 Accepted |

## Итог

**669 passed excl slow / 670 incl slow. ruff 0. HEAD b703ea2 (M226) + 7 staged. S-REPLAY-6 ДОВОДКА ГОТОВА — ждём отмашки на merge M227.**
