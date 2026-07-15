---
name: RetroResolver price-multiplier divergence
description: RetroResolver used hardcoded 2%/3% stop/target instead of faithful multipliers from _price_hint (bullish ×0.994/×1.012)
type: fix
---

**Контекст:**
RetroResolver.resolve() в ReplayHarness использовал хардкодные stop_loss_pct=0.02, target_pct=0.03. А live-путь в `_price_hint` использует множители: bullish stop ×0.994, target ×1.012; bearish stop ×1.006, target ×0.988. Это означало, что replay-сигналы имели стопы ~2% вместо ~0.6% и таргеты ~3% вместо ~1.2% — расхождение в ~3x.

**Решение:**
Рефакторинг RetroResolver — теперь принимает `stop_price`/`target_price`/`direction` params через сигнал-метадату. Значения вычисляются в `_compute_signal_levels`, которая вызывает тот же `_price_hint(direction, entry_price)`. Живой сигнал (source='live', session #22 с entry=66.34) верифицирован: stop=65.99 = 66.34 × 0.994.

**Why / How to apply:**
- Любой ретроспективный resolver должен использовать те же множители, что и live-путь
- `_price_hint` — единственный source of truth для уровней стопов/таргетов
- При добавлении новых множителей — обновлять их в одном месте (`_price_hint`), не в резолверах
