---
id: obs-2026-06-01-002
date: 2026-06-01
slice: A1
type: discovery
tags: [alembic, sqlite, postgres, environment, wave-a]
---

# obs-2026-06-01-002 — Alembic chain в Clay не идёт на SQLite

**Контекст:**

При выполнении Slice A1 (DDL для persistence) по плану Emma прогон `alembic upgrade head` планировался на file-based SQLite (`CLAY_DATABASE_URL=sqlite:///./.tmp/migr_test.db`). Первая же миграция `0001_create_e2_ingestion_baseline.py:14` упала:

```
sqlite3.OperationalError: near "SCHEMA": syntax error
[SQL: CREATE SCHEMA IF NOT EXISTS market]
```

**Причина:**

`0001` содержит `op.execute("CREATE SCHEMA IF NOT EXISTS market")` и аналогичные для `context`/`ops` + `CREATE EXTENSION IF NOT EXISTS timescaledb`. SQLite не поддерживает ни `CREATE SCHEMA`, ни `timescaledb`. Полная цепочка alembic в Clay **не идёт на SQLite ни в одной точке истории миграций**.

**Как обходится в тестах:**

`tests/conftest.py:24` использует `Base.metadata.create_all(engine)` напрямую — в обход alembic. SQLAlchemy сама создаёт таблицы по моделям, schema-различие решается через `SQLITE_SCHEMA_TRANSLATE_MAP` в `db/session.py:7`. Поэтому pytest 107/107 на SQLite проходит, но это **не валидирует миграции** — только модели.

**Решение для A1:**

Прогон `alembic upgrade head` / `downgrade -1` / повторный `upgrade head` сделан на **локальном PG 18.4** (`clay:clay@localhost:5432/clay`, `timescaledb` уже установлен). Все 5 acceptance criteria выполнены.

DDL `0008` написан в **переносимом стиле** (`String(length=N)`, `DateTime(tz)`, `Integer`, `CheckConstraint`, `server_default=sa.text("CURRENT_TIMESTAMP")`) — нет ни hypertables, ни PG-специфики, так что для production-PG он валиден. Но факт-проверка на PG vs SQLite дала разные результаты.

**Why / How to apply:**

- **Любой будущий A-slice с alembic-миграцией** — план Emma про «SQLite для миграций в Clay» не работает. Сразу использовать PG (или поднять временный контейнер, или, если невозможно — прогнать через `Base.metadata.create_all()` в Python-скрипте как proxy).
- **Если архитектор хочет, чтобы alembic шёл и на SQLite** — нужен фейк-dialect в `env.py` (проверять `dialect.name == "sqlite"` и скипать `CREATE SCHEMA`/`CREATE EXTENSION`). Это **A_extra slice**, не часть A1.
- **Перед коммитом `0008`** — стоит явно зафиксировать: "миграции тестируются на PG, не на SQLite". Можно добавить в `docs/development/` короткий runbook.
- **`.tmp/` от SQLite-попытки** — был создан `migr_test.db`, удалён вручную после прогона. Не должно попасть в коммит.
- **Для агента в новой сессии:** если задача "прогнать миграции" — сначала проверить, PG ли доступен (`pg_isready -h localhost`), потом действовать. Не тратить токены на SQLite-попытку.

**Связанные записи:**

- `handoffs/recon-a0-2026-06-01.md` §2.3 (TRANSLATE_MAP)
- `reports/last.md` §3, §5 (прогон A1, отклонение по среде)
- snapshot для архитектора §10 (долги) — там упомянут риск с миграциями
