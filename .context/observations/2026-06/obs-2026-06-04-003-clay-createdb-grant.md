---
name: Grant CREATEDB to clay (live-gates scratch DBs)
description: Standing privilege GRANT 2026-06-04 → REVOKE 2026-06-05. Audit chain замкнут.
type: project
---

**Контекст:**

G2.2 (destructive round-trip миграций) требует scratch-БД `clay_migr_test`.
У `clay` (`rolcreatedb=f` в `pg_roles`) нет прав на `createdb`. Альтернативы:

- (A) Grant CREATEDB clay
- (B) Всё под postgres (включая alembic) — отвергнут: alembic на бою идёт от `clay`, owner всех объектов должен быть `clay` (prod-fidelity)
- (C) Grant + audit — выбран архитектором 2026-06-04

**Решение:** **(C) Grant + audit**

`ALTER ROLE clay CREATEDB` через `pkexec -u postgres psql` — однократно. Дальше:

1. `createdb clay_migr_test` — от `clay` (owner=clay, prod-fidelity)
2. `CREATE EXTENSION timescaledb` — через `pkexec -u postgres` (superuser-only; **timescaledb НЕ trusted extension** в PG, не зависит от CREATEDB)
3. alembic — от `clay` через `CLAY_DATABASE_URL=...` override

**Owner proof:** `\dt market.*` показывает `tableowner=clay` (а не `postgres`) — это и есть prod-fidelity (на бою миграции идут от `clay`, owner всех таблиц/индексов = `clay`).

**Re-iterations:** `0001.downgrade` оставляет `EXTENSION` и схемы (`market/context/ops`) — extension переживает `downgrade base`. Повторные `downgrade base ↔ upgrade head` идут без повторного escalation. Postgres-escalation = ровно один раз на setup.

**Revoke:** ✅ **выполнен 2026-06-05T18:12:18+03:00** (см. REVOKE-секцию ниже). Standing privilege `CREATEDB` снят, principle of least privilege восстановлен.

**REVOKE:** ✅ **2026-06-05T18:12:18+03:00** — выполнен

```sql
-- pkexec -u postgres psql -c "ALTER ROLE clay NOCREATEDB;"
-- verified: SELECT rolcreatedb FROM pg_roles WHERE rolname='clay'; → f
```

**Reason:** G2 (миграционный live-gate) closed 2026-06-05. Scratch `clay_migr_test` снят. G4 (endpoint-smoke) идёт против рабочей `clay` (не scratch) → standing privilege `CREATEDB` больше не нужен.

**Audit chain замкнут:** GRANT 2026-06-04 → REVOKE 2026-06-05. Если когда-либо понадобится `CREATEDB` снова — отдельный grant + новая obs-карточка.

**Why / How to apply:**

- `createdb` требует `CREATEDB` privilege (не superuser).
- `CREATE EXTENSION timescaledb` требует **superuser** (не trusted). Не зависит от `CREATEDB`.
- Alembic под `clay` (после grant) — owner всех таблиц/индексов = `clay` — совпадает с prod-flow.
- Standing privilege для app-user — нарушение PoLP. Standing privilege = **обязательный revoke** после использования.
- Audit-формат: каждое изменение прав на живом боксе (даже dev) → obs-запись с явной REVOKE-секцией.
- pg_hba + polkit дают `pkexec -u postgres` без пароля (auth_admin policy), но peer auth для `postgres` через Unix-сокет всё ещё failed — `pkexec` обходит это.
