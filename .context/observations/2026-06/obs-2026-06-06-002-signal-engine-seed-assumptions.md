# Finding K: signal-engine assumptions exposed by seed-harness

**Дата:** 2026-06-06
**Контекст:** G5b (seam c — seed-fixture for FSM smoke). 3 fix-коммита потребовались чтобы live `clay` начал отдавать `weakening` сигнал.
**Тип:** infra / signal-engine behavior

## Контекст

Запуск `seed_demo_signal_data` на живой `clay` не давал eligible сигнал: shortlist возвращался со state=`absent`/`invalidated`, preflight=hard_fail. Потребовалось 3 fix-коммита чтобы закрыть:

1. **Peak volumes** (`ba66211`): seed peak < live historical max → проигрываем `max_volume` race в `build_shortlist_metrics`. `rolling_volume_score = bar.volume / max(all volumes)` → 0 → base 0 → ranking 0.
2. **Freshness для ВСЕХ таймфреймов** (`af6e668`): `build_shortlist_metrics` iterates `freshness_rows` sorted by `(symbol ASC, timeframe ASC)` и **вторая строка для того же символа ПЕРЕЗАПИСЫВАЕТ** первую если у неё хуже статус. Старая live-строка 1h с `latest_bar_open_time` 23h назад перезаписывала мою свежую 15m → `freshness_by_symbol[symbol] = "stale"`. Fix: seed `upsert_freshness_status` для 5m/15m/1h всех с `latest_bar_open_time = now - 1 min` (внутри всех thresholds: 10/25/80 min).

## Структурный penalty, который seed НЕ обходит

`build_shortlist_metrics` + `_build_risk_triggers` всегда добавляют `lower_confidence` penalty -0.08 когда `degraded_ai` non-empty. В Clay `degraded_ai` заполняется если **provider-mix conflicts** есть (chief-agent=openai, news-sentiment=anthropic, forecast=gemini) — каждая evidence-role с provider ≠ chief_provider добавляет конфликт, и все affected_roles получают `assignment_health="review_required"`. Это by design (multi-provider routing → confidence penalty).

Для **SOLUSDT** на живой `clay` после seed: base=0.66, penalty=-0.08 (ai-conflict) → ranking_score=0.58 → state=`weakening`. Этого достаточно для gate.

## Решение

`scripts/seed_demo_signal_data.py` инвариант:
- **Peak volume ≥ 5×10× live historical max** per symbol (per timeframe). Конкретные значения: BTC=50000, ETH=200000, SOL=2000000 (для текущего live `clay`).
- **Freshness upsert для ВСЕХ таймфреймов** (5m/15m/1h) per symbol, `latest_bar_open_time = now - 1 min` (passes все thresholds).
- **max_volume race**: учтён через peak volume выше.
- **AI penalty**: не обходим (это реальная operational семантика).

## Why / How to apply

- **При будущих seed'ах** в Clay: всегда смотри `SELECT max(volume) FROM market.market_bars WHERE symbol='X'` для каждого (symbol, timeframe) и ставь seed peak в 5-10× больше.
- **При будущих seed'ах freshness**: пиши `upsert_freshness_status` для ВСЕХ timeframe'ов в `IngestionSettings.market_timeframes` за один проход — иначе `build_shortlist_metrics` итеративно перезапишет старая строка с протухшим `latest_bar_open_time`.
- **При интерпретации signal scores на live** `clay`: ranking_score ≤ 0.66 на SOLUSDT/BTCUSDT — это **нормально**, не баг. Penalty от provider-mix структурный.
- **При hard_fail preflight "data-freshness"** на live: первое что проверить — не появилась ли старая freshness-строка для другого timeframe'а символа, которая overwrites fresh через iteration.
- **Документация для будущих G-волн**: `build_shortlist_metrics` — НЕ pure function от входных данных, зависит от итерационного порядка freshness_rows и глобального max_volume.

## Связанные артефакты

- Коммиты: `61fe00c` (initial), `ba66211` (peak volumes), `af6e668` (freshness timeframes)
- Live: 5 FSM cycles + 1 demo-trade (id=1) на SOLUSDT, `ranking_score=0.58, state=weakening`
- Q5: scheduler OFF, manual `POST`, 0 auto-execution
- teardown: 166 rows cleaned, 0 seed-data left
