---
name: Wall-clock audit — 3 leaks found and seamed
description: В S-REPLAY-5 найден 3 leak datetime.now(UTC) в коде, которые нарушали детерминизм
type: fix
---

**Контекст:**
Полный аудит всех 54 точек `datetime.now(UTC)` в проекте. Классификация: 30 операторские, 3 интенциональные, 2 clock impl, 3 утечки. Утечки: `build_shortlist_metrics` использовал `datetime.now(UTC)` вместо параметра; `workspace/service.py:126,205` — прямой `datetime.now(UTC)` вместо `self._clock.now()`.

**Решение:**
- `build_shortlist_metrics` теперь принимает `now: datetime` параметр
- workspace/service.py строки 126 и 205 переведены на `self._clock.now()`

**Why / How to apply:**
- Любой код, касающийся времени в детерминированном контексте, должен использовать clock.inject или clock.now()
- При добавлении нового кода с datetime — проверять, не нарушает ли он детерминизм через `datetime.now(UTC)` (<tool_use> или `datetime.now(UTC)`)
- Нарушители: `datetime.now(UTC)`, `datetime.utcnow()`, `time.time()`
