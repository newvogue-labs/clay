# ADR-031: Notion-mirror publisher — односторонний sync vault → Notion

- **Status:** Accepted — live в production (57 карт, S2-APPLY-1)
- **Driver:** S2 — Notion-mirror для visibility без доступа к БД
- **Supersedes:** Nothing
- **Slices:** S2-1 (vault_core), S2-2 (skeleton), S2-3/3b/3c/3d (apply+reconcile+hardening+fix), S2-4 (archive), S2-5 (CLI+doc)

## Context

Clay хранит знания в git-ваулте (`~/clay-knowledge/`) и синкает их в `#knowledge` (backend Postgres). Оператору нужен read-only доступ к этим картам без доступа к БД и без необходимости клонировать vault.

Notion был выбран как зеркало потому что:
- Не требует поднимать сервис (SaaS)
- Поддерживает markdown-API
- Уже используется командой для других целей

Требования к зеркалу:
- **Одностороннее:** vault → Notion. Notion никогда не пишет обратно.
- **Идемпотентное:** повторный apply не создаёт дубли (ключ = `clay_id`).
- **Crash-safe:** manifest сохраняется после каждого действия, прерванный apply можно повторить.
- **Advisory-only:** Notion-зеркало содержит те же карты, что и `#knowledge` — advisory контент, не исполнительные параметры.

## Decision

### 1. Идемпотентность через `clay_id` + `content_hash`

Публишер сравнивает `content_hash` (SHA-256 от `title|category|priority|tags|content`) с сохранённым в локальном `notion-sync-manifest.json`. Изменение → `UPDATE`, совпадение → `SKIP`, новое → `CREATE`, удалённое → `archive` (soft-delete, не hard-delete).

### 2. Reconcilation-by-Clay-ID

При `CREATE` публишер сперва ищет страницу с таким же `clay_id` (свойство "Clay ID") через `databases/{id}/query`. Нашёл → `RECONCILED→UPDATE` (принимает существующую страницу). Не нашёл → нормальный `CREATE`. Это позволяет пережить потерю локального манифеста.

### 3. Orphan-archive

Страницы, которых нет в ваулте, архивируются (`archived=True`). Не удаляются — это soft-delete, можно восстановить вручную.

### 4. Версионирование API

- `2022-06-28` — query-эндпоинты (reconcile, archive)
- `2025-09-03` — markdown-эндпоинты (create, update контента)
- Управляется через `_api_version()` context manager.

### 5. Сеть

Notion API может быть заблокирован на торговом хосте (DPI по SNI). Публишер запускается с машин вне DPI. Make-таргет `backend-notion-publish-apply` делает pre-flight пробу `curl` к `api.notion.com` и ждёт HTTP 401 как признак связности.

### 6. Красная линия M278

Зеркало содержит advisory-only карты. Никакие исполнительные параметры, ключи, сиды не публикуются. M278 (advisory-only chief-agent) — инвариант.

## Consequences

- **+** Оператор видит знания в Notion без доступа к БД.
- **+** Идемпотентность позволяет перезапускать apply без риска дублей.
- **+** Manifest crash-safe — не теряет прогресс при частичном фейле.
- **−** Notion API недоступен с торгового хоста (DPI) — требует off-host машины.
- **−** Одностороннее — изменения в Notion не синкаются обратно в vault.
