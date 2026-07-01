# ADR-021: Session-Level Risk Limits (Admission Gate)

- **Status:** Accepted (2026-07-01)
- **Date:** 2026-06-24
- **Replaces:** —
- **Depends on:** ADR-020 (Kelly/EV-gate), M211 ev-gate-proof Scope & Limits

## Context

`risk-limits-active` в `session_control/service.py:522` — заглушка: `status="ok"` (hardcoded), `blocks_start=False`. Капитальные/сессионные лимиты не проверяются. Зафиксировано как KNOWN GAP в S-KELLY-2-R (M211).

Перед Ring 1 go/no-go и тем более real-money нужен настоящий admission-gate на старт сессии, проверяющий агрегированные риски (портфельные/сессионные). EV-gate (ADR-020) решает per-signal размер — это отдельный ортогональный слой.

## Decision

Ввести слой session-level risk-limits как часть `_build_preflight()`. Пять кандидатов (L1-L5), каждый с предикатом, источником, порогом (в `[session_limits]`), reason-строкой и severity.

### L1 — Drawdown stop (hard_fail)

- **Предикат:** `SUM(pnl_pct) OVER resolved+entered trades за drawdown_window_hours ≤ -max_drawdown_pct`
- **Источник:** `demo_trade_records.pnl_pct` WHERE `outcome_status` = resolved AND `operator_action` = entered, ORDER BY `recorded_at` DESC, window = `drawdown_window_hours` (24h default)
- **Окно:** **скользящее недавнее**, не all-time — чтобы длинная плюсовая история не маскировала свежую просадку
- **Порог:** `max_drawdown_pct = 15.0` (%), `drawdown_window_hours = 24`
- **Severity:** `hard_fail` → blocks_start
- **Reason:** "Cumulative P&L over last {window}h = {X}% exceeds max drawdown of {Y}%."

### L2 — Consecutive-loss cooldown (hard_fail)

- **Предикат:** `COUNT(consecutive resolved+entered trades WHERE pnl_pct < 0) >= max_consecutive_losses`
- **Источник:** `demo_trade_records.pnl_pct`, ORDER BY `recorded_at` DESC, считать стрик подряд убыточных resolved+entered сделок с конца. Победа (pnl_pct > 0) сбрасывает стрик. Cooldown выводится из таймстемпов: `(now − recorded_at последнего убытка в стрике) < cooldown_minutes`
- **Порог:** `max_consecutive_losses = 3`, `cooldown_minutes = 60`
- **Severity:** `hard_fail` → blocks_start (если cooldown не истёк)
- **Reason:** "{N} consecutive losses — cooldown active for {remaining} min."
- **Хранение:** новых столбцов НЕ вводится — cooldown выводится из существующих таймстемпов

### L3 — Max concurrent sessions (hard_fail, defense-in-depth)

- **Предикат:** активная сессия уже существует
- **Источник:** `session_state.session_id IS NOT NULL` ИЛИ `runtime_state == ACTIVE_SESSION`
- **Порог:** `max_concurrent_sessions = 1` (архитектурно гарантирован singleton `CHECK(id=1)`)
- **Severity:** `hard_fail` → blocks_start
- **Reason:** "Active session already in progress — start blocked."
- **Примечание:** defense-in-depth поверх существующей архитектурной гарантии. Явный check для единообразия/читаемой причины.
- **Аспирационное поле:** `max_concurrent_sessions` — конфиг допускает N>1, но архитектура физически держит максимум 1 активную сессию (`_active_session` = `ActiveSessionRecord | None`). Текущий чек корректно enforced'ит реальный инвариант «1 активная». Пересмотр — при мульти-сессионности (backlog).

### L4 — Max aggregate advisory exposure (warn, placeholder)

- **Предикат:** `Σ(advisory_size_pct) OVER open trades > max_total_exposure_pct`
- **Источник:** `demo_trade_records.advisory_size_pct WHERE broker_status='awaiting_result'`
- **Порог:** `max_total_exposure_pct = 4.0` (2× kelly.cap как консервативный старт)
- **Severity:** `warn` (advisory для pre-money; не blocks_start)
- **Reason:** "Total open exposure = {X}% exceeds {Y}% threshold."
- **Prerequisite:** `advisory_size_pct` nullable — если данные не заполнены, L4 пропускается (best-effort)
- **Near-vacuous note:** при текущей one-session + DEDUP-1 (≤1 открытая запись/сессия) L4 почти всегда ≤1 позиции. Станет осмысленным только при мульти-позиции.
- **Upgraded (ADR-029, 2026-07-01):** L4 больше не placeholder — добавлен `max_total_exposure_block_pct: float = 0.0` (off-by-default). Dual-tier: warn на `max_total_exposure_pct` (4.0) + опциональный hard-block при `block_pct > 0.0`. ADR-029 — `docs/adr/029-capital-exposure-hard-block.md`.

### L5 — Per-session loss alert (warn, advisory)

- **Предикат:** `SUM(pnl_pct) WHERE session_id = current ≤ -per_session_loss_warn_pct`
- **Источник:** `demo_trade_records.pnl_pct` по текущей сессии
- **Порог:** `per_session_loss_warn_pct = 8.0`
- **Severity:** `warn` (НЕ blocks_start — только уведомление, Q5 invariant)
- **Reason:** "Current session P&L = {X}% — below per-session caution threshold."
- **Manual-only:** без авто-закрытия позиций

### blocks_start семантика

1. Все `hard_fail` checks агрегируются: **ANY hard_fail → blocks_start**
2. `blocking_reason` = первый hard_fail check.reason (как сейчас)
3. Warn-checks (`warn`) НЕ блокируют, но отображаются в UI
4. Fail-safe: **DB error / exception** при запросе → `hard_fail` (не смогли проверить → не стартуем). **Успешный запрос с 0/мало строк** → лимит НЕ сработал → `pass` (пустая история ≠ нарушение риска). Два случая разведены.

### Override политика

Pre-money (MVP):
- **Без override** — все hard_fail блокируют жёстко.
- Оператор видит blocking_reason в UI и может устранить причину.

Post-MVP / real-money (будущий ADR):
- Operator acknowledge: UI-кнопка "Override risk limits" с аудитом.
- Override НЕ отключает лимиты — только разрешает 1 старт.
- Аудит: `audit_writer.write("risk_limits.override", ...)`.

### Поведение при Degraded

**L1–L5 НЕ меняются при degraded.** Degraded = система менее надёжна, но это не повод ослаблять капитальные лимиты. Runtime-здоровье покрыто отдельным `runtime-stability` гейтом; капитальные лимиты от него независимы. Ослабление было бы footgun.

## Invariants

1. **Admission-gate ≠ auto-execution** — limits блокируют СТАРТ сессии, не закрывают позиции. Manual-only (Q5).
2. **Explainable** — каждый блок с читаемой reason-строкой.
3. **Fail-safe — split:** DB error → hard_fail; empty result → pass (не нарушение).
4. **Отделён от EV-gate** — session_control не вызывает sizing, signal_engine не вызывает preflight.
5. **Слой не пересекается с EV** — EV решает размер 1 сигнала, session-limits решают admission.

## Config

Новые поля `RiskConfig` в `config/models.py`:

```python
class SessionLimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_drawdown_pct: float = 15.0       # (0, 100]
    max_consecutive_losses: int = 3      # ≥1
    cooldown_minutes: int = 60           # ≥0
    drawdown_window_hours: int = 24      # ≥1
    max_concurrent_sessions: int = 1     # ≥1
    max_total_exposure_pct: float = 4.0  # (0, 100]
    per_session_loss_warn_pct: float = 8.0  # (0, 100]
```

TOML (секция `[session_limits]` в `risk.toml`):

```toml
[session_limits]
max_drawdown_pct = 15.0
max_consecutive_losses = 3
cooldown_minutes = 60
drawdown_window_hours = 24
max_concurrent_sessions = 1
max_total_exposure_pct = 4.0
per_session_loss_warn_pct = 8.0
```

Пороги — **conservative starting values**, tunable после калибровки на реальных данных.

## Implementation notes (для S-RISKLIMITS-2)

- `_build_preflight()` (`session_control/service.py:448`) сейчас выбрасывает `session` (`del session`). Для S-RISKLIMITS-2: убрать `del session`, inject dependency на `DemoRepository` (или прямой read-путь к `demo_trade_records`).
- Все LIMIT-запросы — read-only, через существующий `DemoRepository` или его расширение.
- `SessionLimitsConfig` грузится из `risk.toml` через `config_loader.load_scope("risk").session_limits`.

## Consequences (positive)

- Замена заглушки на реальный gate перед реальными деньгами
- Единый механизм проверки в `_build_preflight()` с существующими checks
- Все проверки explainable, оператор видит причину
- Fail-safe: консервативен при DB error, но не клинит на пустой истории

## Consequences (negative)

- `advisory_size_pct` nullable — L4 best-effort до миграции на NOT NULL
- Consecutive-loss требует window-запроса (ORDER BY + streak counting)
- Увеличение времени префлайта (N+1 запросов к demo_trade_records)

## Alternatives

1. **Оставить заглушку** — отклонено: это и есть gap из M211. Нельзя идти к go/no-go с заявленным, но не работающим контролем.
2. **Только advisory-warn без block** — Hibernate Advisory для pre-money (все L1-L5 как warn, ничего не блокирует) — самообман, повторяет ту же проблему. Отклонено.
3. **Перенести лимиты в отдельный сервис** — overengineering для pre-money. `_build_preflight` уже существует и принимает session.

## Open Questions

| Q | Тема | Вердикт |
|---|------|---------|
| Q1 | Seed-сценарий для пустой БД | **RESOLVED** — RV1: empty result → pass (не нарушение), не блок. Первая сессия проходит. Grace period не нужен. |
| Q2 | Real-money vs demo пороги | **FUTURE ADR** — пока единые; раздвоение после real-money requirements. |
| Q3 | Cooldown persistence | **RESOLVED** — RV3: вывод из таймстемпов, новых столбцов не нужно. |
| Q4 | Override-аудит | **FUTURE ADR** — post-MVP override UI с аудитом. |
| Q5 | Взаимодействие с degraded | **RESOLVED** — RV7: degraded НЕ меняет L1-L5 (не ослаблять). |
| Q6 | Test strategy | → **S-RISKLIMITS-2** — 10-15 scenario-тестов для `_build_preflight` с моками demo_repo. |

## Ссылки

- M211: `docs/mission-control/ev-gate-proof.md` — Scope & Limits (KNOWN GAP → resolved)
- ADR-020: `docs/adr/020-position-sizing-kelly-ev-gate.md`
- ADR-029: `docs/adr/029-capital-exposure-hard-block.md` — L4 hard-block upgrade
