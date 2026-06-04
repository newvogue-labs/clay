# Report: MP1 (retention) + MP4 (loud-failure) + MP3 (config-driven providers)

> **Сессия 2026-06-04 (продолжение).** E6a+b → MP0 → **MP1 ✅ + MP4 ✅ + MP3 ✅**. **357 passed** (+16 net, 0 regress). Pyright src 35. 4 коммита в origin.

## Что сделано

### MP1 — ops.* retention ✅ (committed `facef1f`)
- Миграция 0011: 3 индекса (all 3 ops time-cols)
- `OpsRetentionJob`: sync, threadpool, session-owned, isolated error policy
- 13 retention-тестов
- Микрофикс: `index=True` на `IngestRun.started_at` (модель=DDL symmetry)
- C3 (`routes/ingestion.py`) отделён в `c30a911`

### MP4 — loud-failure / observability ✅ (committed `a6b0e3f`)

| Компонент | Что |
|---|---|
| `core/logging.py` | own-handler, `propagate=False`, sentinel guard, `CLAY_LOG_LEVEL` env |
| `create_app()` wire | `configure_clay_logging()` первым вызовом |
| Site 1: `_collect_market_bars` | `logger.warning(source, symbol, tf, exc)` |
| Site 2: `_fetch_market_bars` retry | per-attempt `logger.warning` + финальный `logger.error` |
| Site 3: `context/manager.py` | `logger.exception(connector_id, source_name)` |
| Config tests (6) | propagate, anti-dup, level, env, format |
| Emission tests (3) | StreamHandler-capture (caplog не достаёт из-за `propagate=False`) |
| Caplog fix (2) | `test_clay_scheduler`, `test_context_repositories_dedup` |

### MP3 — config-driven providers ✅ (committed `cb5ef77`)

| Группа | Было | Стало |
|---|---|---|
| `limit=200` | 6 мест (protocol + clients defaults + `service.py:546`) | read from `settings.market_fetch_limit` at call-site only |
| `timeout=10.0` | 3 хардкода (binance/bybit ctors, lifespan) | read from `settings.market_fetch_timeout` |
| `Limits(20,10)` | lifespan.py literals | read from `settings.market_limits_*` |
| THRESHOLDS (5) | `evaluator.py` module-level consts | optional DI params `market_thresholds`/`context_thresholds` |
| Settings surface | only `IngestionSettings` exported | +`SchedulerSettings` exported |

**10 новых полей** в `IngestionSettings`, flat (Option A), defaults = прежние литералы.
evaluator через DI (not `import settings`). Settings-агрегат = YAGNI.

## Acceptance

| | baseline | now | Δ |
|---|---|---|---|
| pytest | 341 | **357** | +16 net |
| regressions | — | 0 | ✅ |
| pyright src | 35 | **35** | 0 new |
| pyright total | 194 | **194** | 0 new |
| migrations | 0011 | **0011** | ✅ |

## Commit lineage
```
cb5ef77 feat(settings): MP3 config-driven providers — 10 hardcoded values → IngestionSettings + DI
a6b0e3f feat(obs): MP4 loud-failure logging at 3 fetch/retry/context sites + clay logging config
facef1f feat(ops): MP1 wire ops.* retention prune-job + 0011 indexes + started_at index
c30a911 feat(ingestion): C3 route no longer owns session lifecycle
```

## Что дальше
- **MP2 (deploy capstone)** — финальный слайс MVP-polish. Ждёт от Emma.
