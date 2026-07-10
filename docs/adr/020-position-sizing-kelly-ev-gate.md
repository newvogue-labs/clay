---
tags:
  - risk
---

# ADR-020: Position Sizing — Fractional Kelly + EV-Gate

- **Status:** Accepted
- **Date:** 2026-06-24
- **Replaces:** —
- **Donor-ref:** weatherbot (fractional Kelly + EV-gate)

## Context

Никакого позиционирования капитала нет. Demo-трейды исполняются всем доступным notional (равным). Отсутствие sizing — операционный риск перед real-money: без сайзинга единственная ошибка может съесть капитал полностью. Q5 (manual-only) инвариант сохраняется: сайзинг — ADVISORY рекомендация оператору, без авто-исполнения.

## Decision

Fractional Kelly с верхним капом. Формулы:

```
f*  = (p · b − (1−p)) / b       — full Kelly
f   = clamp(λ · f*, 0, cap)     — advisory fraction
```

Где:
- `λ` — дробная доля Kelly (default `0.25`)
- `cap` — hard cap доли equity (default `0.02 = 2%`)
- `p` — оценка вероятности выигрыша
- `b` — ожидаемый payoff в R-единицах

EV-gate — три полосы:
- `EV ≤ 0` — размер 0 + strong-warn (отрицательный edge; сигнал может быть блокирован)
- `0 < EV ≤ min_ev` — размер 0 + warning, **сигнал остаётся виден** с пояснением «EV ниже порога, размер не рекомендуется»
- `EV > min_ev` — размер `f`

При `f* ≤ 0` → no-trade (`f = 0`).

### Источник p

`confidence` в текущем сигнале — ординальный скор (не калиброванная вероятность). Маппить confidence → p через таблицу отклонено как ложная точность.

`p` — статистическая оценка win-rate со сжатием: **Wilson lower bound (95%)** ИЛИ **Beta(1,1)-posterior mean**. При тонких данных (n < 30) нижняя граница 13/20 ≈ 0.43 → `f ≈ 0`, и **это корректно**: edge статистически не доказан, advisory-размер ≈ 0 by design.

`confidence` остаётся фильтром допуска и ранжирования сигналов, но НЕ подставляется как `p`.

### Источник b

Первичный `b` — **эмпирический**, portfolio-level:

```
b_emp = mean(pnl_pct | pnl_pct > 0) / mean(|pnl_pct| | pnl_pct < 0)
```

Рассчитывается по реализованным demo-исходам (`demo.demo_trade_records`). Per-signal R-multiple (stop/target, ATR(14), target = 2×stop) — **будущий отдельный ADR**, не предусловие к этому.

### Пример (текущие demo-данные, n=20)

```
total = 20
wins  = 13
losses = 7
win_rate = 13/20 = 0.6500

avg_win  = +0.5485%
avg_loss = −0.3114%
b_emp    = 0.5485 / 0.3114 = 1.7611

f*       = (0.65 × 1.7611 − 0.35) / 1.7611 = 0.4513
λ·f*     = 0.25 × 0.4513 = 0.1128
f        = min(0.1128, 0.02) = 0.0200 = 2.00% equity
         (capped at hard limit)

EV       = 0.65 × 1.7611 − 0.35 = 0.7947 R-units
min_ev   = 0.15 → EV > min_ev ✓ → advisory size = 2%

Wilson 95% lower bound for p: 0.4329
→ f* (Wilson lower) = 0.1108 → f = min(0.25×0.1108, 0.02) = 0.02
  (capped, но при меньшем cap edge недоказан)
```

### Placement

Новый advisory-слой в `signal_engine` между risk_triggers и `build_signal_snapshot`:

1. `_build_risk_triggers` (существующий)
2. `_apply_kelly_sizing` (НОВЫЙ) — вычисляет `p`, `b`, `EV`, `f*`, `f`
3. EV-gate → новый риск-триггер `ev-below-min`: `response_action="warning_only"` (зануляет размер, НЕ блокирует сигнал). Хард-блок (`block_signal`) — только для EV ≤ 0.
4. `build_signal_snapshot` (существующий)

В `EvaluatedSignalSnapshot` добавляются advisory-поля (только explainability/аудит):
- `probability_estimate: float | None` — `p`
- `payoff_estimate: float | None` — `b`
- `kelly_fraction: float | None` — `f*`
- `advisory_position_size: float | None` — `f` (доля equity)
- `ev_value: float | None` — `EV`
- `ev_gate_status: str | None` — `"passed"` | `"warning"` (0 < EV ≤ min_ev) | `"blocked"` (EV ≤ 0)

### Конфиг (новые поля `RiskConfig`)

```toml
[kelly]
lambda = 0.25           # дробная доля Kelly
cap = 0.02              # hard cap (2% от equity)
min_ev = 0.15           # стартовый строгий порог EV (R-единицы); пересмотр после калибровки
equity_base = 1.0       # demo default: 100% demo notional

[calibration]
min_outcomes_for_recalibration = 30  # минимальный n для перекалибровки p
```

`default_payoff` — удалён. `b` — вычисляемый (эмпирический), не конфиг-константа.

### Degraded / Fallback

`f = 0` (no-size advisory). Никакого сайзинга в degraded-режиме. No-trade advisory — инвариант.

### Единицы

`EV` и `min_ev` — в **R-единицах** (согласовано с определением `b`). `min_ev = 0.15` — стартовый строгий порог, помечен на пересмотр после калибровки `p`.

`f` — доля **equity счёта**. Для demo `equity_base = 1.0` (100% demo notional).

## Invariants

1. **Manual-only:** размер — рекомендация, оператор вводит вручную
2. **Advisory:** no auto-send, no auto-slide
3. **Bounded:** `f ≤ cap` (hard) и `f* ≤ 1.0` (by Kelly math)
4. **Fail-safe:** пока `p` не калиброван → `λ` низкий, EV-gate строгий; degraded → `f = 0`
5. **Explainable:** все метрики (`p`, `b`, `EV`, `f`, `f*`, `ev_gate_status`) в snapshot и логе
6. **Backward-compat:** существующие demo-трейды без размера = `null`

## Prerequisites

**Per-signal stop/target (ATR-based)** — будущий отдельный ADR, не блокер для S-KELLY-2.

Текущий `b_emp` — portfolio-level эмпирическая оценка. Per-signal R-multiple через ATR(14) с target = 2×stop (по донору) даст более точный `b` на уровне сигнала. Это enhancement, не prerequisite.

## Calibration Plan

- **n < 30:** `p` через Wilson lower bound или Beta(1,1)-posterior. Ранний advisory-размер ≈ 0 — корректное поведение при недоказанном edge.
- **n ≥ 30:** bootstrap-калибровка `confidence` → `p`. Пересмотр `min_ev` и `λ`.
- **Порог:** `calibration.min_outcomes_for_recalibration = 30`.

## Early-Regime Expectation

При тонких данных (n < 30) статистическая неопределённость `p` высока. Wilson lower bound для 13/20 = 0.43 → `f* ≈ 0.11` → `f` упрется в `cap=0.02`, но **это фича, не баг**: пока edge не доказан, система рекомендует минимальный размер. С накоплением данных оценка `p` уточняется.

## Consequences / Open Questions

1. База equity: `equity_base = 1.0` (demo notional). Для real-money потребуется отдельный параметр.
2. Multi-signal: при нескольких `active` сигналах — top-1 only (manual-only, оператор выбирает).
3. Kelly long/short: симметрично (одинаковый `p` и `b` для обоих направлений).
4. Recalibration: пересчёт `b_emp` и `p` при достижении `min_outcomes_for_recalibration`.

## Alternatives

- **Fixed-fraction (без EV-gate):** отклонено — нет защиты от отрицательного матожидания.
- **Full Kelly:** отклонено — 42% капитала при p=0.65/b=1.5, неприемлемо агрессивно.
- **Volatility-targeting:** отмечено как future enhancement (R2).
- **Flat sizing (1/n):** текущее состояние, отклонено.
