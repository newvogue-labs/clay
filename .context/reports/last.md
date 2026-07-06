# Отчёт: сессия 2026-07-05 — peer review + первый --apply vault→#knowledge

## Что сделано

### E-KNOW S4 — review всего корпуса clay-knowledge
Последовательный peer review 4 доменов (49 карточек):
- **signals/ (3)** — regime-detection: найдена неверная атрибуция CHOP (Dreiss, не Wilder). Исправлено.
- **risk/ (13)** — atr-stop: Chandelier Exit описан через EMA вместо Highest High (LeBeau). optimal-f: некорректное сравнение с Kelly (классический Kelly — p/b-бинарная модель, не «нормальное распределение»). Исправлено.
- **market/ (18)** — все формулы/атрибуции корректны. Без замечаний.
- **strategy/ (15)** — keltner-breakout: повтор ошибки Chandelier Exit (EMA→Highest High). Исправлено.
- Все 49 промотированы `draft → peer_reviewed`

### E-KNOW S5 — первый --apply vault→#knowledge ✅
- Dry-run: 49 CREATE (signals 3, risk 13, market 18, strategy 15)
- `--apply`: ошибка 500 — `source_type VARCHAR(32)` overflow для длинных имён файлов
- Создана alembic-миграция `df9cf24f3af4`: `source_type VARCHAR(32)→VARCHAR(64)` (non-destructive)
- Повторный `--apply`: 49/49, 0 ошибок (3 SKIP, 46 CREATE)
- Манифест закоммичен в vault (`f10e217`)
- Найден pre-existing баг в `/knowledge/overview`: `total_items = len(recent_items(limit=20))`, не реальный count

### Найденные баги в clay backend
1. **FIXED:** `source_type VARCHAR(32)` — overflow для `vault:market/stop-hunt-liquidity-pools` (38 символов). Миграция → VARCHAR(64).
2. **LOGGED (pre-existing):** `/knowledge/overview` — `_build_summary` считает `total_items = len(items)`, где items — `list_recent_items(limit=20)`, не реальный total count в БД.

## Следующий шаг
Выбор Emma: что дальше — новый контент в vault, Q5-GO, или другое.
