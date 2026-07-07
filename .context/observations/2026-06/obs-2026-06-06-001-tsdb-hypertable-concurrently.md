# Finding J: TSDB hypertable + CREATE INDEX CONCURRENTLY

**Дата:** 2026-06-06
**Контекст:** G2.5c (49 missing indexes), волна 2 (4 hypertable).
**Тип:** infra / TSDB incompatibility

## Контекст

При применении миграции `0014_hypertable_indexes` (4 индекса на `market.market_bars`×3 + `market.orderbook_summaries`×1) с параметром `postgresql_concurrently=True` первая же команда упала:

```
sqlalchemy.exc.NotSupportedError: (psycopg.errors.FeatureNotSupported)
hypertables do not support concurrent index creation
[SQL: CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_market_bars_bar_close_time
       ON market.market_bars (bar_close_time)]
```

Это **противоречит** recon R6 G2.5a, где было зафиксировано «postgresql_concurrently=True поддержан TSDB 2.x». На самом деле TSDB 2.x поддерживает `CONCURRENTLY` только на **чанках** (per-chunk), но **НЕ на hypertable parent**.

## Что реально работает (TSDB 2.x)

| Операция | Hypertable parent | Chunk |
|---|---|---|
| `CREATE INDEX` (plain) | ✅ TSDB пропагирует по чанкам под brief ACCESS EXCLUSIVE lock | ✅ |
| `CREATE INDEX CONCURRENTLY` | ❌ NotSupportedError | ✅ на пустых |
| `DROP INDEX` (plain) | ✅ brief lock | ✅ |
| `DROP INDEX CONCURRENTLY` | ❌ NotSupportedError | ✅ |

## Решение

Для **пустых** hypertable (R6: `n_live_tup=0` во всех hot-таблицах Clay) — plain `CREATE INDEX` через `op.get_context().autocommit_block()`. TSDB пропагирует индекс по существующим чанкам и делает доступным для будущих под brief lock. На пустых таблицах lock = мгновенный.

```python
with op.get_context().autocommit_block():
    op.create_index(name, table, cols, schema=schema, if_not_exists=True)
```

## Why / How to apply

- **При миграциях на TSDB hypertable** в Clay: НЕ ставить `postgresql_concurrently=True` на parent. Plain `CREATE INDEX` + autocommit_block.
- **Для непустых** hypertable (когда R6 перестанет быть truth): нужна chunk-by-chunk стратегия. Цикл по `pg_inherits` → для каждого `_hyper_<N>_<seq>_chunk` → `CREATE INDEX CONCURRENTLY` на chunk-таблице. Или миграция «вне окна» + lock window.
- **В recon для будущих G-волн:** нельзя слепо доверять R6/R7 — verify на каждом TSDB-релизном апгрейде (текущая 2.26.3 → планируется 2.27.x).
- **Probe-ревизии в Clay:** никогда не оставлять в репо. Удалять сразу после извлечения списка (правило state.md).

## Связанные артефакты

- Commit: `36bcbf4` (G2.5c, миграция 0014)
- Recon: `.context/reports/last.md` G2.5a R6 (устаревший claim про CONCURRENTLY)
- Recovery: fix-through-revision, не INVALID-drop
