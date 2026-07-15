# Finding L: freshness dual-policy (signal best-of-all vs workspace worst-of-all)

**Дата:** 2026-06-06
**Контекст:** G6-R (recon freshness-агрегации и ai-conflict-штрафа)
**Тип:** infra / signal-engine policy divergence

## Контекст

G6-R R1 пересмотрел предположение G5b Finding K о `last-write-wins` по `(symbol ASC, timeframe ASC)`. Реальный код `build_shortlist_metrics` (`backend/src/clay/shortlist/read_models.py:8-51`) использует **first-fresh-wins** (best-of-all per symbol): первая строка со статусом `"fresh"` записывается в `freshness_by_symbol`, остальные skipped (line 18-21). Сортировка `(symbol ASC, timeframe ASC)` определяет **порядок проверки**, не финальный статус.

Однако параллельный путь — `workspace/service.py:212-224` `collapse_market_statuses` — итерирует **ВСЕ** `freshness_rows` по всем timeframe и символам и берёт **max (worst-of-all)**. При `market_status != "fresh"` `workspace_posture="defensive"` (`workspace/service.py:242-244`).

Результат: на одном и том же наборе данных signal-path говорит "fresh, можно торговать", workspace-path — "defensive". Инконсистентность UI при частичном stale (1 из 3 timeframe отстал).

## Текущее состояние живой БД

При `CLAY_SCHEDULER_ENABLED=false` все 9 строк `market.freshness_status` (3 symbols × 3 timeframes) имеют `freshness_state="unknown"` уже 52ч. Через `resolve_market_freshness_status` (`freshness/evaluator.py:87-111`):

- `MARKET_STATUS_PRIORITY` (line 17-22): `unknown(1) > fresh(0)`.
- `_worse_market_status` (line 101): если `stored="unknown"`, effective остаётся `"unknown"` независимо от evaluated.

→ Effective freshness "unknown" для ВСЕХ (symbol, timeframe) → preflight `data-freshness` hard-fail → `start_session` блокирован.

При scheduler ON: best-of-all per symbol разморозится → лидер-timeframe "fresh" покроет отстающий. Signal path покажет "fresh", но workspace path уйдёт в "defensive" если **любой** timeframe stale.

## Решение (когда решим лечить)

**Минимальный фикс (для real-money):** синхронизировать политики — выбрать одну. Рекомендация: best-of-all в обоих местах (signal+workspace) И смена workspace `defensive` логики на что-то другое (например, explicit per-timeframe breakdown в UI). Альтернатива: worst-of-all везде — тогда `collapse_market_statuses` остаётся, а в `build_shortlist_metrics` ужесточить до "все timeframe должны быть fresh" (но это **ужесточит** gate и может false-negative'ить при штатном 1h lag).

**Что НЕ делать:**
- Не "фиксить" G5b Finding K как ложный — он остаётся валидным в части seed-инвариантов (писать freshness для ВСЕХ timeframe) даже после коррекции policy.

**Что зафиксировать сразу (zero-cost):**
- В `signal_snapshot` явно логировать `freshness_aggregation_policy = "best_of_all"` и `stale_timeframes: List[str]` для observability. Не меняет поведение, даёт оператору visibility.

## Why / How to apply

- **При real-money sign-off:** scheduler ON обязателен. Без него все freshness = "unknown" → preflight hard-fail.
- **При аудите UI-инконсистентности** (зелёный signal light + жёлтый workspace light): вероятная причина = stale 1h при свежих 5m/15m. Проверить через SELECT `market.freshness_status WHERE freshness_state != 'fresh'`.
- **При будущих G-волнах:** не полагаться на "single source of truth" в `build_shortlist_metrics` — есть второй aggregation path в `workspace`. Документировать dual-policy явно в CONTEXT.md.
- **При seed'ах:** держать G5b инвариант (писать freshness для всех timeframe) — даже после фикса dual-policy он остаётся defensive measure.
- **При real-money-блокер:** dual-policy без fix'а = оператор видит разные светы на разных экранах → decision latency / operator confusion. Блокер для real-money **если** не добавить observability (см. "зафиксировать сразу").

## Связанные артефакты

- Recon: G6-R R1 (отчёт агента)
- Observation: obs-2026-06-06-002 (G5b Finding K — freshness overwrite/race, корректируется этим observation'ом)
- Code: `shortlist/read_models.py:8-51`, `workspace/service.py:212-244`, `freshness/evaluator.py:87-111`
- Live: 9/9 freshness "unknown" при scheduler OFF
