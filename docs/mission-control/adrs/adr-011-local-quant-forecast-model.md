# ADR-011 — Forecast: локальная количественная модель

Дата: 2026-06-10
Статус: accepted
Связанные эпики: `E5`, `DEPLOY-5`
Решение пользователя: 2A
Связанные ADR: ADR-005, ADR-009
Supersedes: stale ML-track карточки проекта (Colab T4, Ollama-forecast, forecast-провайдер=gemini)

## Контекст

Роль **forecast-model**. Recon R1: `forecast-lite-v1` (Local) в standby; текущее назначение forecast→`gemini-2.5-flash` (заглушка). Доступен Lightning.ai как burst-GPU для тренировки (US-egress, только обучение, без TUN; free Studio засыпает, ~80 GPU-ч/мес). Локальное железо: GTX 1660 SUPER 6GB. В БД есть `market.market_bars` (история баров).

## Решение

**forecast-model — локальная количественная модель** (LSTM/TCN/Transformer), обучаемая на `market.market_bars`; инференс выполняется **локально**. Gemini — только **опциональный fallback**.

- Датасет-пайплайн строится из `market.market_bars` → тренировка (локально или burst на Lightning.ai, training-only, под data-egress политику ADR-009) → локальный инференс.
- Инференс вызывается в async-job, латентность приемлема вне request-path.
- Эта ADR **отменяет** устаревшие карточки ML-трека (Colab/Ollama-forecast/gemini-forecast) на карте проекта.

## Последствия

- Нужен dataset/feature-пайплайн и артефакт-стор модели.
- Тренировка офлайн/burst; инференс без внешнего egress (privacy-плюс).
- Карта проекта (ML-трек) требует ресинка под это решение.

## Альтернативы

- Облачный forecast (gemini) как основной. Отклонено: privacy + стоимость; оставлен как опц. fallback.
- Полный отказ от forecast в v1. Отклонено: forecast — часть orchestration-flow E5.
