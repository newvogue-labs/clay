# ADR-015: Degraded-mode AI-слоя

- **Status:** Accepted (формализует доказанное поведение, 5c.4 раунд 3)
- **Date:** 2026-06-13
- **Связь:** blueprint §10.5; runbook-001-preflight-degraded-mode; runbook-004.

## Контекст

Падение ноды / исчерпание RPD / transient не должно валить весь цикл субагентов.

## Решение

- Per-role error-изоляция: падает только затронутая роль → строка с `error` в `ai_agent_runs`;
  остальные роли и цикл продолжаются.
- Правило интервала ≥ 2× длительности тика (тик 4 ролей ≈52s → 300s).
- Пробник ноды перед live: Binance ≠US ∧ Gemini-200.
- Fail-loud: `ModelUnavailableError` → строка с error, без тихих 200.

## Последствия

- (+) Контур выживает при частичных отказах free-провайдеров.
- (−) Рост error-строк в `ai_agent_runs` → актуализирует retention (backlog).
- (~) FOOTGUN E (кандидат): шлюз отдаёт пустую 400 без тела → error неинформативна (backlog).
