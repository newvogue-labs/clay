---
date: 2026-06-02
type: recon
applies-to: [clay, b5, ingestion, context, dedup, micro-recon]
status: ratified — app-level dedup verified, [HIGH-1] NOT a block (under single-worker + asyncio.Lock)
tags: [recon, b5, micro-recon, dedup, news, sentiment, asyncio-lock, single-worker]
---

# obs-2026-06-02-006: B5 micro-recon — `store_news_items` / `store_sentiment_snapshots` dedup

## Scope

Read-only микро-recon на 2 файлах:
- `backend/src/clay/db/repositories_context.py` (методы `store_news_items`, `store_sentiment_snapshots`)
- `backend/src/clay/db/models_context.py` (`NewsItem`, `SentimentSnapshot` models, `__table_args__`)

Цель: подтвердить/опровергнуть [HIGH-1] из `obs-2026-06-02-005` — есть ли dedup (constraint / app-level / ON CONFLICT) для news и sentiment items.

## Verdict

### `store_news_items` (`repositories_context.py:11-27`)

- **App-level dedup: ДА** (SELECT-then-skip pattern)
  ```python
  for item in items:
      existing = self.session.scalar(
          select(NewsItem).where(
              NewsItem.source_name == item["source_name"],
              NewsItem.headline == item["headline"],
              NewsItem.published_at == item["published_at"],
          ),
      )
      if existing is not None:
          continue  # ← dedup: skip если уже есть
      self.session.add(NewsItem(**item))
      written += 1
  ```
- **Dedup key:** `(source_name, headline, published_at)` — 3 поля
- **DB-level UniqueConstraint: НЕТ** (см. ниже)
- **Идемпотентность в single-worker: ДА** (повтор → 0 inserts)
- **TOCTOU race risk:** есть, если две сессии работают параллельно. Но в B5 добавляется `asyncio.Lock` (per Emma [MED-A]) → сессии serialized на event loop → race closed.

### `store_sentiment_snapshots` (`repositories_context.py:29-45`)

- **App-level dedup: ДА** (тот же SELECT-then-skip pattern)
  ```python
  for item in items:
      existing = self.session.scalar(
          select(SentimentSnapshot).where(
              SentimentSnapshot.source_name == item["source_name"],
              SentimentSnapshot.symbol == item["symbol"],
              SentimentSnapshot.captured_at == item["captured_at"],
          ),
      )
      if existing is not None:
          continue
      self.session.add(SentimentSnapshot(**item))
      written += 1
  ```
- **Dedup key:** `(source_name, symbol, captured_at)` — 3 поля
- **DB-level UniqueConstraint: НЕТ**
- **Идемпотентность в single-worker: ДА**

### Models (`models_context.py`)

```python
class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = {"schema": "context"}  # ← NO UniqueConstraint
    # id PK + source_name (indexed) + headline + summary + published_at (indexed) + symbol (indexed) + source_url

class SentimentSnapshot(Base):
    __tablename__ = "sentiment_snapshots"
    __table_args__ = {"schema": "context"}  # ← NO UniqueConstraint
    # id PK + source_name (indexed) + symbol (indexed) + sentiment_label + sentiment_score + captured_at (indexed)
```

- **DB-level UniqueConstraint: НЕТ ни на одной модели** (только `schema: "context"` в `__table_args__`)
- **Defense-in-depth отсутствует:** если app-level SELECT-then-skip пробит (concurrent sessions, race condition) → оба INSERT'нут → duplicates
- **Mitigation в B5:** `asyncio.Lock` (per Emma [MED-A]) сериализует все вызовы `run_once` в одном event loop. В single-worker v1 (deaddrop "B0 single-worker assumption") — race closed.

## 🚩 Risk flags

### [INFO-1] Dedup keys — content-чувствительные

- News key включает `headline` (строка 512 chars). Если connector возвращает slightly different `headline` для одной и той же новости (different casing, trailing whitespace, encoding difference) → **dedup не сработает → duplicate rows**.
- **Реальный источник:** Demo-коннекторы (`demo_news`/`demo_sentiment`) — насколько стабильны их payloads? Не проверено в micro-recon scope.
- **Severity:** LOW (демо-коннекторы, не production-grade). Но в roadmap B5+ — заметка.

### [INFO-2] No DB-level UniqueConstraint = no defense-in-depth

- Если asyncio.Lock пробит (например, manual route + scheduler race без lock) → SELECT-then-skip в обоих threads/sessions → оба INSERT'нут → duplicates.
- **Mitigation:** asyncio.Lock (B5) + single-worker v1 assumption. Достаточно для v1.
- **Backlog candidate:** добавить `UniqueConstraint("source_name", "headline", "published_at", name="uq_news_item")` для news и `UniqueConstraint("source_name", "symbol", "captured_at", name="uq_sentiment_snapshot")` для sentiment — defense-in-depth, не блокер B5.

## Recommendation

**[HIGH-1] НЕ блокирует B5 plan-фазу.** App-level dedup is in place. B5 добавляет `asyncio.Lock` service-level guard → race closed в single-worker v1. Нет необходимости в B5.0 dedup-gate (миграция + app-level upsert) как pre-req слайсе.

**Backlog (NOT now):**
- DB-level `UniqueConstraint` для `news_items` и `sentiment_snapshots` — defense-in-depth, не блокер
- Проверка Demo-коннекторов на стабильность payload'ов (особенно `headline` casing/whitespace)

## How to apply

- B5 plan-фаза может стартовать сразу
- `asyncio.Lock` (Emma [MED-A]) — primary mitigation, уже планируется
- Single-worker assumption (B0 deaddrop) — closed остается, в plan упомянуть

## Carry-forward

- App-level SELECT-then-skip — приемлемая стратегия v1 для dedup **при наличии** service-level lock
- DB-level UniqueConstraint — defense-in-depth, eventual hardening, не блокер для scheduler-job
- Connector payload stability — separate concern (low-priority)
