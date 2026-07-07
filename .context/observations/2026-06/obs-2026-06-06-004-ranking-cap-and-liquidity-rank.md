# Finding M: ranking cap 0.92 (hardcoded provider-mix) + rank-based liquidity

**Дата:** 2026-06-06
**Контекст:** G6-R (recon freshness-агрегации и ai-conflict-штрафа)
**Тип:** signal-engine / structural policy + liquidity model

## Контекст

G6-R вскрыл 2 связанных наблюдения о ranking-функции и volume-нормализации.

### R2 — структурный cap 0.92 от hardcoded provider-mix

`signal_engine/service.py:331-332`: `_apply_ranking_penalty` срабатывает за каждый trigger с `response_action="lower_confidence"` (включая `ai-conflict`) → `ranking -= 0.08`. Penalty **ДО** порогов `0.72`/`0.45` (применение: line 148 → state assignment: line 154-160).

**Источник trigger'а** (`signal_engine/service.py:235-299` + `ai_control/service.py:386-421`): `ai-conflict` эмитится если хотя бы одна evidence-role имеет `provider != chief_provider` с severity="warning" (by design — provider diversity discount).

**Где назначаются провайдеры:** `db/repositories_runtime_state.py:41-46` `INITIAL_ASSIGNMENTS`:
- `chief-agent: openai-gpt-5.4`
- `market-scanner: openai-gpt-5.4-mini` (OpenAI → skip в conflict detection, line 393)
- `news-sentiment-agent: anthropic-claude-sonnet-4.5` (Anthropic → conflict #1)
- `forecast-model: gemini-2.5-flash` (Google → conflict #2)

**Hardcoded**, не ConfigLoader. `bulk_upsert(INITIAL_ASSIGNMENTS)` на init (`ai_control/service.py:96, 106`) при пустой таблице. Подтверждено в живой БД: 4 строки, ровно INITIAL_ASSIGNMENTS.

**Per-row confidence_penalty = `round(0.2/2, 2) = 0.10`** (config/loader.py:90 `degraded_confidence_penalty=0.2`).

**Итог:** `degraded_ai = {news-sentiment-agent, forecast-model}` non-empty ВСЕГДА в steady-state → `ai-conflict` эмитится на КАЖДЫЙ сигнал → `ranking -= 0.08` безусловно → **потолок ranking_score = 0.92**.

**Потолок для active-state:** `ranking ≥ 0.72` → нужен `base_ranking ≥ 0.80` (т.к. 0.80 - 0.08 = 0.72). Base = 0.55·vol + 0.45·vol → нужны оба ≥ 0.80. Достижимо но узко. На живом seed SOLUSDT: base=0.66, ranking=0.58 (state=weakening) — то есть даже с seed'ом, давшим `state=weakening`, до active не хватило.

**Стратегия-mode:** `_resolve_strategy_mode` (line 374-379) — `ranking ≥ 0.78` для momentum. При потолке 0.92 momentum-стратегия формально достижима, но только при base≥0.86. На живых seed-данных: нет.

### R3 — rank-based liquidity без min-volume guard

`shortlist/read_models.py:15`: `max_volume = max(bar.volume for bar in bars) or 1.0` — **глобальный max по preferred-timeframe bars** (через `_pick_preferred_bars`, line 214-225 signal_engine/service.py).

`read_models.py:31`: `rolling_volume_score = round(bar.volume / max_volume, 4)` — **relative rank**, абсолютный объём не важен.

`read_models.py:32-39`: `liquidity_summary` дискретизация: ≥0.75 → "high", ≥0.4 → "medium", <0.4 → "low" — тоже **rank-based**, не absolute.

**Нет min-volume guard.** Тихий рынок (падение объёмов в 10×) → лидер всё равно получит score=1.0 + `liquidity_summary="high"` → система не сигнализирует о slippage/spread-риске.

**Live подтверждение (SELECT max(volume) per (symbol, timeframe)):**

| symbol  | timeframe | max_vol (live) | seed peak | ratio |
|---------|-----------|----------------|-----------|-------|
| BTCUSDT | 15m       | 3100           | 50000     | 16×   |
| ETHUSDT | 15m       | 57012          | 200000    | 3.5×  |
| SOLUSDT | 15m       | 405962         | 2000000   | 5×    |

Seed peak **завышен** в 3.5-16× относительно live, чтобы выиграть `max_volume` race (G5b Finding K) — но **только** preferred timeframe. При падении объёмов в 10× seed SOLUSDT=2M упадёт до ~200K — и **всё равно** будет rank=1 среди 3 symbols (BTC ~310, ETH ~5700). То есть seed-стратегия "переиграть global max" robust к падению, но **не сигнализирует** о реальном падении.

## Решение (когда решим лечить)

**Для R2 (real-money блокер?):**
- **Минимально (zero-cost):** документировать cap 0.92 в preflight/observability — оператор видит `ranking_cap_reason = "ai-conflict"` в metadata. Не меняет поведение, даёт visibility.
- **Правильно:** сделать provider-mix конфигурируемым (ConfigLoader или admin endpoint). Назначить все evidence-roles на chief provider (OpenAI) → 0 conflicts → ranking cap снят. Trade-off: теряем provider-diversity discount (что **может быть** хорошо для momentum-стратегий, плохо для resilient-стратегий).
- **Альтернатива:** penalty gating до ranking — `if ranking_score < ranking_threshold * 1.10: response_action = "lower_confidence"` ужесточает на cap, а не наличии conflict. Но это меняет прод-семантику сигнала.

**Для R3 (real-money блокер?):**
- **Минимально (zero-cost):** добавить observability — в `signal_snapshot`/`briefing` показывать `absolute_volume_usd` (или quote_volume) + `min_volume_threshold_flag` (есть ли в конфиге).
- **Правильно:** добавить `min_volume_threshold` (absolute) в IngestionSettings. `if preferred_bar.volume < threshold: liquidity_summary = "thin"` (или override `liquidity_summary="low"` независимо от rank). Threshold = quote_volume >= N USD за 15m bar (например, $5M для major pairs).
- **Семантически:** rank-based нужен для cross-symbol comparison (BTC vs SOL объёмы разные на порядки), но **не** для absolute-liquidity gate. Два разных сигнала должны быть разделены.

**Что НЕ делать:**
- Не "фиксить" R2 через aligned providers без продуктового обсуждения (это меняет risk-model).
- Не "фиксить" R3 через удаление rank-based (нужен для cross-symbol).

## Why / How to apply

- **При real-money sign-off:** cap 0.92 + rank-based liquidity — оба **потенциальные блокеры** для EMA-настроенной стратегии. Без observability оператор не увидит "почему active-state не достигается" (R2) или "почему liquidity=high при падении объёмов" (R3).
- **При интерпретации ranking_score в логах:** помнить что 0.92 — потолок, не bug. State "weakening" при base=0.66 — это провайдер-mix, не данные.
- **При будущих seed'ах:** seed peak volumes держать выше live max (G5b), но **также** записывать absolute volume в metadata для observability R3.
- **При будущих config-изменениях:** `INITIAL_ASSIGNMENTS` — single point of failure для cap 0.92. Любое изменение провайдеров меняет penalty автоматически.
- **При дискуссии "что есть by-design diversity discount":** текущий код — намеренная архитектурная политика, не bug. Вопрос — соответствует ли она продуктовой стратегии real-money.

## Связанные артефакты

- Recon: G6-R R2, R3 (отчёт агента)
- Code: `signal_engine/service.py:120-160, 235-299, 310-372`, `ai_control/service.py:341-421`, `db/repositories_runtime_state.py:41-46`, `shortlist/read_models.py:8-51`, `config/loader.py:90`
- Live: 4 строки `ai_assignments` = INITIAL_ASSIGNMENTS; 9 строк bar volumes
- Observation: obs-2026-06-06-002 (G5b Finding K — max_volume race, related)
