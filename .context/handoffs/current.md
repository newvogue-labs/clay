---
date: 2026-06-26
from: Agent (big-pickle)
session: S-REPLAY-6 доводка на реальных данных 5433
---

## Что сделано

- **S-REPLAY-6 доводка:** ✅ CLOSED — real-data soak на 5433 + guard + commit
  - Диагноз clock-desync: вердикт (A) — два VirtualClock в soak-фикстуре
  - Фикс: один clock, guard на `recorded_at > now + 60s` + регресс-тест
  - **Real-data soak 5433** (soak_5433.py, 583 SOLUSDT 1h, Jun 2–25):
    - 62 sessions, 61 resolved (1 forward buffer)
    - **42W / 19L** (реальный W/L mix, не синтетик)
    - p/b recalibrated: **p=0.0→0.564, b=1.0→1.3095** ✅
    - default frozen: **p=0.40878, b=1.61910** byte-identical ✅
    - isolation: replay_ids ∩ default_ids = ∅ ✅
    - L2 natural: 19 потерь (status=ok, нет 3 consecutive в cooldown)
    - guard: 7200s ahead detected ✅
  - test_soak.py: закоммичен (tracked, 3 tests: 1 slow + 2 regular)
  - ADR-024: Accepted с реальными числами (5433, not synthetic)

## Следующий шаг

**M227 — merge.** DIRTY HEAD `b703ea2`:
- `backend/tests/replay/test_soak.py` — tracked, L2 + guard tests
- `backend/tests/replay/soak_5433.py` — standalone 5433 soak, clock-aware patch
- `backend/src/clay/session_control/service.py` — clock-desync guard
- `docs/adr/024-...md` — Accepted, real 5433 numbers
- `backend/pyproject.toml` — slow marker registered

## Блокеры

- Нет. Всё готово к merge. Жду команды Emma.

## На заметку

- Soak на 5433: 583 real bars, ~960s, 42W/19L, b 1.0→1.3095 (реальная рекалибровка)
- L2 status=ok — честно: 19 потерь, но не 3 подряд в 30-мин окне (синтетический был 976W/0L — артефакт)
- Guard: 7200s detected on real data
