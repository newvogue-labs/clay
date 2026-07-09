# Notion-mirror: vault → Notion publisher

Публишер зеркалит vault знаний Clay (`~/clay-knowledge/`) в базу Notion для read-only
доступа оператора.

- **Идемпотентность:** ключ = `clay_id` + `content_hash`. Повторный apply не плодит дубли.
- **Crash-safe:** manifest сохраняется по-действийно. Прерванный apply = повторить.
- **Advisory-only:** зеркало содержит те же advisory карты, что и `#knowledge`.
  Никакие исполнительные параметры не публикуются.

## Как запускать

```bash
# dry-run (показать план, ничего не менять)
make backend-notion-publish

# apply (реально обновить Notion)
make backend-notion-publish-apply
```

Pre-flight в `backend-notion-publish-apply`:
1. Проверяет связность Notion API (`curl` → ждёт HTTP 401).
2. Устанавливает `CLAY_NOTION_KB_DB` и `CLAY_NOTION_TOKEN` из `backend/.env`.

## Env

| Переменная | Обязательна | Описание |
|---|---|---|
| `CLAY_NOTION_KB_DB` | да | ID базы Notion |
| `CLAY_NOTION_TOKEN` | да | API-токен интеграции Notion |
| `CLAY_NOTION_FORCE_IPV4` | нет | При `true` форсирует IPv4 (если IPv6 блокирован) |

## Exit-коды

| Код | Значение |
|---|---|
| `0` | OK: план выполнен / dry-run |
| `1` | Ошибка конфигурации (нет env, битый vault-path) |
| `2` | Runtime-ошибка (apply упал, сеть недоступна) |

## Особенности сети

Notion API может быть заблокирован на торговом хосте (DPI по SNI).
Запускайте публишер **с машины вне DPI** (ноутбук, не торговый хост).

Make-таргет `backend-notion-publish-apply` проверяет связность через
`curl https://api.notion.com/v1/users/me` и ждёт HTTP 401
(неаутентифицирован = API жив).

## Детали реализации

- Модуль: `backend/src/clay/tools/notion_publish.py`
- Manifest: `<vault>/notion-sync-manifest.json`
- Версионирование Notion API: `2022-06-28` (query) / `2025-09-03` (markdown)
- Reconciliation-by-Clay-ID: поиск существующей страницы через `databases/{id}/query`
- Orphan-archive: страницы без пары в vault → `archived=true`
- ADR: [ADR-031](../adr/031-notion-mirror-publisher.md)
