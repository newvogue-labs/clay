---
tags:
  - risk
  - signals
---


# ADR-026: Freshness Dual-Policy (per-pair worst-of + focused-pair gate)

- **Status:** Accepted (2026-06-29)
- **Driver:** Finding L (G2/G6) — рассинхрон политики свежести между signal-pipeline и workspace
- **Supersedes:** Nothing (дополняет ADR-004 §freshness, backlog E2.4)
- **Slices:** L2 (`3aea771`) · L3a (`b38df40`) · L3b (`bb3a246`)

## Context

Свежесть рыночных данных оценивалась по-разному в двух местах:

- **signal-pipeline / shortlist** — агрегировал статус свежести оптимистично
  (best-of по набору символов): одна свежая пара маскировала несвежесть
  остальных.
- **workspace** — гейтил сессию по глобальному рыночному статусу
  (`market_status != "fresh" → defensive`): одна несвежая пара уводила весь
  воркспейс в defensive, даже когда фокусная пара свежая.

Итог — визуальный и поведенческий рассинхрон: shortlist показывал «всё ок», а
workspace падал в defensive (или наоборот). Это Finding L — общий блокер
G2 (data integrity) и G6 (observability).

## Decision

Единая **dual-policy** свежести из трёх частей:

1. **Shortlist = worst-of пер-символ (L2).** `shortlist/read_models.py`
   оценивает свежесть по каждому символу отдельно (`evaluated_by_symbol`) и
   сворачивает статусы worst-of (`collapse_market_statuses`, приоритет
   fresh < unknown < stale < error). Несвежесть одной пары больше не
   маскируется.

2. **Workspace гейтит по ФОКУСНОЙ паре (L3a).** `workspace/service.py`: гейт
   `if posture == "normal" and focused_market_status != "fresh" → defensive`.
   Свежесть фокусной пары решает posture; глобальная несвежесть остальных пар
   больше НЕ роняет весь воркспейс. Старый глобальный гейт
   `market_status != "fresh"` снят.

3. **Глобальная несвежесть = advisory, не блокер (L3a backend + L3b frontend).**
   Новое поле `monitored_data_health` в `WorkspaceStateSnapshot` (backend =
   source of truth) несёт сводный статус мониторинга вне фокуса. UI показывает
   ненавязчивую advisory-строку при `monitored_data_health === 'degraded'`
   («часть пар вне фокуса несвежие — гейтинг ведём по фокусной паре»), не уводя
   оператора в defensive.

## Rejected

- **Вариант B (полный контракт + расширенный UI-баннер):** избыточен —
  отдельный баннер дублировал бы per-pair badge (`monitoring-pool-panel`) и
  market-badge (`update-meta-strip`), уже показывающие свежесть после L3a.
  Достаточно одной advisory-строки в focused-pair header.
- **Вариант C (воскресить orphan `workspace-state-banner.tsx`):** мёртвый
  компонент; его воскрешение — отдельный dead-code трек, не часть Finding L.
- **Глобальный worst-of гейт в workspace:** вернул бы исходную проблему (одна
  несвежая не-фокусная пара → defensive).

## Consequences

- **Плюс:** G2 (data integrity) закрыт — единая честная политика свежести,
  рассинхрон pipeline↔workspace устранён. Оператор гейтится по релевантной
  (фокусной) паре, несвежесть периферии видна, но не парализует сессию.
- **Плюс:** backend остаётся source of truth; фронт лишь зеркалит контракт
  (`monitored_data_health`) и показывает advisory.
- **Нейтрально:** добавлено одно поле в snapshot-контракт
  (`monitored_data_health: str`, дефолт `"unknown"`).
- **Риск:** если фокусная пара свежа, а торгуемая периферия — нет, оператор
  может пропустить деградацию. Смягчение: advisory-строка + per-pair
  `availability_status` badge + global market-badge остаются видимыми.

## Связанные артефакты

- **Гейты:** `release-gates.md` — G2 ✅; G6 (остаётся R3).
- **Журнал:** «Architect Working Log — Том 3», M261 (L2→L3a→L3b).
- **Код:** `shortlist/read_models.py` (L2) · `workspace/models.py` +
  `workspace/service.py` (L3a) · `frontend/src/types/workspace.ts` +
  `features/workspace/focused-pair-header.tsx` (L3b).
- **Дополняет:** ADR-004 (storage/freshness), backlog E2.4 (data freshness rules).