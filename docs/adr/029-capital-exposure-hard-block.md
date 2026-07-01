# ADR-029: Capital Exposure Hard-Block (dual-tier off-by-default)

- **Status:** Accepted (2026-07-01)
- **Driver:** S-CAPLIMITS-1 — exposure warn-only недостаточен для реальных денег; нужен опциональный hard-block поверх advisory-порога
- **Supersedes:** Nothing (дополняет ADR-021 L4)
- **Slice:** S-CAPLIMITS-1 (squash `7759910`, PR #6, CI #28506529830)

## Context

ADR-021 ввёл L4 (max aggregate advisory exposure) как `warn`-only — `blocks_start=False`.
Это осознанно для pre-money: оператор видит превышение, но старт не блокируется.
Перед real-money (Ring 1) нужен опциональный жёсткий блок: оператор может
установить второй, более высокий порог, при превышении которого preflight
останавливает старт сессии.

Один порог не может делать две работы одновременно (advisory + gate):
- Если сделать существующий `max_total_exposure_pct` блокирующим — сломается
  demo (warn-семантика теряется) и текущие тесты.
- Если добавить отдельный block-only порог — dual-tier, чистое разделение.

## Decision

**Dual-tier aggregate advisory exposure:**

1. **Advisory-порог (существующий) — без изменений.**
   `max_total_exposure_pct: float = 4.0` (дефолт). При превышении → `warn`,
   `blocks_start=False`. Поведение не меняется, demo 20/5 зелёные.

2. **Новый hard-block порог.**
   `max_total_exposure_block_pct: float = 0.0` (дефолт `0.0` = off).
   При `block_pct > 0.0 AND total_exposure > block_pct` → preflight check
   `risk-limit-exposure` = `hard_fail`, `blocks_start=True`.

3. **Off-by-default.** Дефолт `block_pct = 0.0` ⇒ `0.0 > 0.0` всегда `False` —
   блок никогда не срабатывает. Не ломает demo-baseline и зелёные тесты.
   Включается явным конфигом в `risk.toml` / apply_config.

4. **Пороги независимы.** `block` и `warn` не мешают друг другу:
   - `block_pct > 0` И `exposure > block_pct` → `hard_fail` (блок).
   - `block_pct = 0` (off) ИЛИ `exposure ≤ block_pct` → проверяется warn-порог.
   - `exposure ≤ warn_pct` → `ok`.

## Rejected

- **Один порог (4% → hard_fail):** заставил бы advisory-warn делать две работы
  и сломал бы demo-baseline. Разделение чище.
- **Notional / rolling-окно вместо Σ `advisory_size_pct`:** точнее, но требует
  нового стора — вне слайса. Backlog: single-bar (сумма открытых позиций).
- **Client-side enforcement:** UI не должен быть защитным рубежом —
  backend source of truth.
- **Всегда блокировать:** real-money = осознанное решение (Q5); hard-block
  опционален — оператор сам решает, нужен ли он.

## Consequences

- **Плюс:** L4 перестал быть placeholder — exposure теперь hard-block-capable
  off-by-default.
- **Плюс:** ADR-021 capital-часть закрыта, KNOWN GAP снят.
- **Плюс:** backend остается source of truth; порог читается из `SessionLimitsConfig`.
- **Нейтрально:** добавлено одно поле конфига (`max_total_exposure_block_pct: float`,
  дефолт `0.0`).
- **Безопасность изменения:** off-by-default ⇒ поведение prod/demo не меняется
  до явного включения; main остаётся зелёным.
- **Fail-closed:** список fallback в `_build_preflight` уже включает
  `risk-limit-exposure` с `hard_fail` — не менялся.

## Связанные артефакты

- **ADR-020:** `docs/adr/020-position-sizing-kelly-ev-gate.md` — Kelly/EV-gate
  (слой размера, ортогонален admission).
- **ADR-021:** `docs/adr/021-session-risk-limits.md` — L4 теперь hard-block-capable.
- **Код:** `config/models.py` (`SessionLimitsConfig.max_total_exposure_block_pct`) ·
  `config/loader.py` (default-writer) ·
  `session_control/service.py` (`_build_preflight` 3-ветка).
- **Тесты:** `tests/session_control/test_session_risk_limits.py` — 4 теста D9.
