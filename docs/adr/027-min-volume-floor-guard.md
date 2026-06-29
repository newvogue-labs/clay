# ADR-027: Min-Volume Floor Guard (anti-slippage signal gate)

- **Status:** Accepted (2026-06-29)
- **Driver:** R3 (G3/G6) — сигнал не защищён от неликвида: `low_quote_volume` считался, но был advisory-only (dead-end флаг)
- **Supersedes:** Nothing (дополняет observability-флаг `low_quote_volume_threshold`, G6-obs Finding R3)
- **Slice:** R3 (`0f418d5`, squash PR #5, CI #28382355347)

## Context

USD-оборот preferred-бара (`leader_quote_volume = close * volume`) уже
вычислялся в shortlist и нёсся в сигнал, но использовался ТОЛЬКО как
observability-флаг `low_quote_volume` (порог `low_quote_volume_threshold`,
дефолт 1M): писался лог `signal.low_quote_volume_detected` — и всё. Никакого
влияния на trigger/gating/ranking. На тихом рынке система могла показать
«нормальный» сигнал по паре, где реальной ликвидности нет: ручной вход
проскальзывает раньше, чем идея отыграет (anti-slippage риск). Это Finding R3 —
общий блокер G3 (signal quality) и остаток G6 (observability).

## Decision

**Dual-tier ликвидности** — разделяем «осторожно» и «нельзя торговать»:

1. **Advisory-флаг сохраняется без изменений.** `low_quote_volume_threshold`
   (дефолт 1M) остаётся observability-only: поднимает `low_quote_volume` и лог.
   Семантика не тронута.

2. **Новый жёсткий guard — min-volume floor.** Настройка
   `min_quote_volume_floor: float` (env `CLAY_MIN_QUOTE_VOLUME_FLOOR`, дефолт
   `0.0`). В `signal_engine/_build_risk_triggers`: при
   `floor > 0.0 and leader_quote_volume < floor` поднимается risk-trigger
   `low-volume-floor-{symbol}` (severity `critical`,
   `response_action="block_signal"`). Через существующую машинерию:
   `_resolve_response_action → block_signal`, `_resolve_signal_state →
   invalidated`, ranking-penalty −0.2.

3. **Паритет уверенности.** `_resolve_confidence_penalty` штрафует
   `low-volume-floor` так же, как `stale-market` (`degraded_penalty`): блок не
   должен показываться оператору с высокой confidence (честный UI).

4. **Off-by-default.** Дефолт `floor = 0.0` ⇒ guard выключен: не трогаем
   demo-baseline (20 сессий) и зелёные тесты. Включается явным env в проде.
   Рекомендованный прод-ориентир — ~250_000 USD оборота preferred-бара
   (тюнится по инструменту).

## Rejected

- **Один порог (1M → block):** заставил бы advisory-флаг делать две разные
  работы (observability + gate) и задним числом сломал бы demo 20/5. Разделение
  чище.
- **Softer `lower_confidence` вместо `block_signal`:** самообман — сигнал
  остаётся на экране и соблазняет, хотя ручной вход на неликвиде заведомо
  проскользнёт. На floor-breach честнее убрать сигнал.
- **Rolling / 24h-объём вместо single-bar:** точнее, но требует нового
  стора/окна — вне слайса R3. Backlog-caveat: floor работает по обороту
  preferred-бара.
- **Frontend-слайс:** не нужен — `trigger.title` авто-появляется в
  `active_triggers`, блок виден через существующий signal-state UI.

## Consequences

- **Плюс:** G3 (signal quality) закрыт — сигнал больше не обманывает на
  неликвиде (anti-slippage guard) + win-rate baseline зафиксирован (20 сессий).
- **Плюс:** G6 (observability) закрыт — последний caveat (R3) снят.
- **Плюс:** backend остаётся source of truth; floor — единственная точка правды,
  читается из настроек в движке.
- **Нейтрально:** добавлено одно поле настроек (`min_quote_volume_floor: float`,
  дефолт `0.0`) и один параметр `_build_risk_triggers`.
- **Безопасность изменения:** off-by-default ⇒ поведение prod/demo не меняется
  до явного включения; main остаётся зелёным.
- **Риск:** single-bar метрика может дёргаться на разовых тонких барах.
  Смягчение: floor консервативный + advisory-флаг (1M) остаётся видимым;
  rolling-объём — backlog.

## Связанные артефакты

- **Гейты:** `release-gates.md` — G3 ✅, G6 ✅.
- **Журнал:** «Architect Working Log — Том 3», M262 (R3).
- **Код:** `settings/ingestion.py` (`min_quote_volume_floor`) ·
  `signal_engine/service.py` (`_build_risk_triggers` guard +
  `_resolve_confidence_penalty` parity) ·
  `tests/signal_engine/test_signal_engine_service.py` (+2 теста).
- **Дополняет:** G6-obs Finding R3 (`low_quote_volume_threshold` advisory-флаг).
