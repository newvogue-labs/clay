# EV-Gate Block Proof — S-KELLY-2-R

> **Дата:** 2026-06-24
> **Версия кода:** `78332b1` (S-KELLY-2 merged)
> **Связанный ADR:** [ADR-020](../adrs/adr-020-kelly-ev-gate.md)

## Сводка

Документ доказывает, что EV-gate (fractional Kelly с expected-value фильтром) **реально блокирует размер позиции** на сквозном пути `_apply_kelly_sizing → execution_notes`. А также что EV-gate **НЕ каскадирует** в state/response_action сигнала — сигнал остаётся видимым для UI/аналитика.

## Таблица 4 сценариев

| # | Сценарий | Вход: p, b, EV, degraded | Выход: f | ev_gate_triggered | Нота в execution_notes | Тест |
|---|----------|--------------------------|----------|-------------------|------------------------|------|
| a | **EV ≤ 0** (negative edge) | p=0.3, b=1.0, EV=-0.4 | `0.0` | `True` | `"EV ≤ 0 — negative edge, advisory size = 0."` | `TestEvGateScenarios::test_negative_edge_ev_below_zero` |
| b | **0 < EV ≤ min_ev** | p=0.5, b=1.05, EV=0.025 | `0.0` | `True` | `"EV 0.03R below min (0.15R) — advisory size = 0 (signal still visible)."` | `TestEvGateScenarios::test_below_min_gate_blocks` |
| c | **EV > min_ev** (gate open) | p=0.65, b=1.76, EV=0.79 | `0.02` (capped) | `False` | `"Advisory size: 2.0% equity (fractional Kelly, EV 0.79R)."` | `TestEvGateScenarios::test_above_min_passes_gate` |
| d | **Degraded** | RuntimeState.DEGRADED, любые stats | `None` | `False` | `"System degraded — advisory size suppressed (0)."` | `TestEvGateScenarios::test_degraded_skips_kelly` |

Во всех сценариях (a–d) сигнал **остаётся видимым**: `state`, `response_action`, `ranking_score` не изменяются EV-gate'ом. Изменяются только:
- `signal.advisory_position_size` ← `kelly_result.f`
- `signal.ev_gate_triggered` ← `kelly_result.ev_gate_triggered`
- `signal.execution_notes` ← содержит sizing-note на последней позиции

Доказательство независимости: `TestEvGateNoCascade::test_signal_state_independent_of_kelly` и `TestEvGateNoCascade::test_response_action_independent_of_kelly`.

## Golden на реальных данных

Параметры с реального раннинга (Ring 1 demo, 20 сессий, 13W/7L):

| Метрика | Значение | Формула |
|---------|----------|---------|
| Wilson lower (p) | **0.433** | `wilson_lower(wins=13, total=20)` |
| Empirical b | **1.761** | `empirical_b(win_sum=7.131, loss_sum=-2.180, wins=13, losses=7)` |
| EV | **0.195R** | `p * b - (1-p) = 0.433 * 1.761 - 0.567` |
| min_ev (конфиг) | 0.15 | из risk.kelly.min_ev |
| Вердикт | **gate PASS** | 0.195 > 0.15 → EV gate открыт |
| f_star | 0.111 | `EV / b = 0.195 / 1.761` |
| f (advisory) | **0.02** (2%) | cap по `risk.kelly.cap=0.02` |

Итог: на данных Ring 1 EV-gate **пропускает**, размер **capped** на 2%.

## Scope & limits

### Что доказано

- **EV-gate блокирует РАЗМЕР** (advisory position size зануляется при EV ≤ min_ev)
- **Hard-block (stale-market / expired-window)** по-прежнему блокирует сигнал через `response_action=block_signal` (`TestHardBlockRegression`)
- **EV-gate НЕ влияет на state/response_action** — сигнал остаётся видимым
- **Degraded** полностью отключает Kelly-размер (f=None)

### Известные gaps (НЕ покрыты)

1. **session-level `risk-limits-active` — заглушка**  
   В `session_control/service.py:522`:
   ```python
   SessionPreflightCheck(
       check_id="risk-limits-active",
       status="ok",           # hardcoded
       blocks_start=False,    # НИКОГДА не блокирует
   )
   ```
   Этот check **всегда** `"ok"` и **всегда пропускает**, независимо от размера позиции, капитала, drawdown или session-P&L. Капитальные/сессионные лимиты НЕ enforced.  
   **Статус:** KNOWN GAP — кандидат на отдельный слайс/ADR.

2. **Per-signal stop/target (ATR)** — `S-KELLY-2-R` enhancement, не входит в данный proof.

## Сквозной путь блокировки

```
_evaluate_candidates()
  ├── _build_risk_triggers()          ← stale-market → block_signal
  │                                     expired-window → block_signal
  ├── _apply_kelly_sizing()           ← EV≤0/min_ev → f=0, gate_triggered=True
  ├── _resolve_response_action()      ← зависит ТОЛЬКО от risk_triggers
  ├── _resolve_signal_state()         ← зависит от market_status, response_action, ranking
  ├── _build_execution_notes()        ← kelly_result → sizing note
  └── EvaluatedSignalSnapshot()       ← f→advisory_position_size, GT→ev_gate_triggered
```

## Ссылки

- [ADR-020: Fractional Kelly + EV-gate](../adrs/adr-020-kelly-ev-gate.md)
- Тесты: `tests/signal_engine/test_sizing.py` — `TestEvGateScenarios`, `TestEvGateNoCascade`, `TestHardBlockRegression`
- Session-level gap: `backend/src/clay/session_control/service.py:522`
