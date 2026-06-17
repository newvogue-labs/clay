# Отчёт: сессия 2026-06-17 — S3b — S3c-3 ✅ CLOSED + rehearsal

## S3b — ConfigReconciler parity-diff

- ✅ **0017 folded into 0016**: `provider_id` добавлен в DDL `provider_deployment` (NOT NULL, FK). Down→up, re-seed, 0 churn.
- ✅ **`ConfigReconciler.render()`**: round-trip YAML через `ruamel.yaml`, заменяет только `model_list`. Фильтр по `key_state=available`.
- ✅ **Parity-diff**: семантическое сравнение (set по model_name+upstream_model). `Equivalent: True` против `/etc/clay/litellm/config.yaml`.
- ✅ **Seed bug fix**: `_key_id_for_deployment()` — прямой маппинг `(provider_name, key_ref)` вместо хрупкого `label.startswith`. `minimax-m3` теперь с ключом.
- ✅ **14 тестов** (render, parity GATE, exclusion, guard).
- ⚠️ **recon**: два конфига. Канонический выяснен в S3c-1R.

## S3c-1 — ConfigWriter shadow

- ✅ **`ConfigWriter`**: `validate()`, `write_shadow()` (temp→os.replace), `make_backup()`, `noop_skip()`.
- ✅ **`scripts/reconcile_shadow.py`**: pre-flight TS 2.27.1, флаг `CLAY_PROVIDER_POOL_RECONCILE_ENABLED`.
- ✅ **24 теста** (atomic write, validation gate, backup, noop-skip, guard IO). 0 live-касаний.

## S3c-1R — recon канонического пути

- ✅ **Канонический путь**: `/etc/clay/litellm/config.yaml` (system-юнит, User=clay, PID 2100509).
- ✅ **Dead user-unit**: `clay-litellm.service` (emma) удалён, старый конфиг `.stale`.
- ✅ **Prov-enance**: runtime (7 NVIDIA) из файла. Restart безопасен. FOOTGUN H снят.
- ✅ **master_key**: нет → `/config/update` недоступен. Reload = restart.
- ✅ **Parity подтверждён**: `Equivalent: True` против канонического пути.

## S3c-2 — apply_live (live-запись + restart)

- ✅ **Host cleanup**: user-юнит удалён, sudoers-правило добавлено.
- ✅ **`ConfigWriter.apply_live()`**: backup→write (как clay)→restart→health→rollback.
- ✅ **Privilege**: запись = `sudo -u clay cp` (root не нужен). restart = `sudo systemctl restart` (узкое sudoers).
- ✅ **`scripts/reconcile_apply.py`**: флаг + `--force` rehearsal.
- ✅ **10 тестов** (happy, noop, force, validation fail, rollback×2, health-parse, write-as-clay, no-kill).
- ✅ **No-op live run**: `Applied: False` (0 записи, 0 restart).

## Ключевые находки

- **FOOTGUN H (ложный)**: два конфига → user-unit (мёртвый) vs system-unit (живой). Устранён.
- **Два litellm процесса**: user-unit под emma (не запущен) и system-unit под clay (PID 2100509).

## S3c-3 — degraded-mode (never-empty invariant)

- ✅ **`evaluate_pool_health(rows, floor=1)`** — чистая функция: считает `available_total`, `by_model_name`, `degraded`.
- ✅ **`DegradedModeError`** — отдельное исключение (ожидаемое состояние пула, НЕ баг).
- ✅ **`ConfigWriter.reconcile()`** — render → health-check → validate → apply_live. Никогда не крашится.
- ✅ **`ApplyReport.status ∈ {applied, noop, degraded, rolled_back, failed}`**.
- ✅ **ADR-015** в `docs/adr/015-degraded-mode.md` — Accepted. Never-empty invariant, fail-loud, last-good.
- ✅ **12 тестов** (5 pool_health, 7 reconcile).

## Rehearsal S3c-2 (live, `--force`)

- ✅ **Baseline**: health=healthy, 7 моделей, sha `bf415a14…`, clay:clay 640.
- ✅ **Прогон**: `Applied=True`, Backup=`…bak-180454Z`, `Restart OK`, `Health OK`, `Rolled back=False`.
- ✅ **Post**: health=healthy, 7/7 моделей, sha бэкапа == sha ДО, **Equivalent: True**.
- ✅ **2 бага поймано**:
  1. `_make_backup_timestamped` — `shutil.copy2` → PermissionError (emma не пишет в `/etc/clay/litellm/`). Fixed: `sudo -u clay cp`.
  2. `_write_as_user` — temp-файл root:0600 → нечитаемый для clay. Fixed: `chmod 0644`.

## Верификация

- ✅ 8 коммитов, HEAD `6def8b5`
- ✅ 558 passed (+12 S3c-3)
- ✅ ruff 0
- ✅ rehearsal S3c-2 live: green
