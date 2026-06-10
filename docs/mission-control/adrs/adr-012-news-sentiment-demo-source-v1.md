# ADR-012 — News/sentiment: demo-источник для v1

Дата: 2026-06-10
Статус: accepted
Связанные эпики: `E5`, `DEPLOY-5`
Решение пользователя: 1A
Связанные ADR: ADR-005, ADR-009

## Контекст

Роль **news-sentiment-agent** потребляет новостной/sentiment-вход. Recon R4: реального источника нет — только `DemoNewsConnector` (хардкод «BTC holds breakout») и `DemoSentimentConnector` (BTCUSDT/bullish/0.68); таблицы `context.news_items`/`sentiment_snapshots` заполнены demo-данными. `signal_engine` использует sentiment в `_resolve_direction` (≥0.6 bull / ≤0.4 bear).

## Решение

Для DEPLOY-5 v1 **news-sentiment-agent остаётся на demo-коннекторах** (слабый вход, явно помечен как demo).

- Реальный источник (NewsAPI / X / Reddit) — **отложенный под-трек** после DEPLOY-5, под egress-политику ADR-009 + стоимость.
- `signal_engine` трактует demo-sentiment как **низкоуверенный** вход; news не доминирует над рыночным сигналом (роль не может override market signal).

## Последствия

- Вклад новостей в сигнал остаётся demo/слабым; задокументировано как out-of-scope сверх wiring в 5c.
- Избегаем преждевременного внешнего news-egress до готовности политики.

## Альтернативы

- Интегрировать реальный news сейчас. Отклонено: scope + egress + стоимость. **Ревизуемо** (отдельный под-трек).
