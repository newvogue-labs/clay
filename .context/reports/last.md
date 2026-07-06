# Отчёт: сессия 2026-07-06 — E-KNOW S4 phase 2 (advisory cards) + ablation eval

## Что сделано

### E-KNOW S4 phase 2 — 4 advisory карты (83-86)
- Созданы 4 карты в vault: signals/noise-vs-signal, rank-confidence-kelly, data-freshness-discount, posture-flag-triggers
- Все карты используют голос strict advisory (рекомендуют/флагят, без императивов)
- Карты скопированы из `chief-agent-interpretive-cards.md` (6 оригинальных → выбраны 4 под архитектора)

### Idempotent vault sync (PR #17 → #18)
- `external_id` колонка + UNIQUE CONSTRAINT + upsert API в knowledge backend
- Sync больше не delete+recreate — атомарный INSERT ON CONFLICT DO UPDATE
- 56 items, 0 дублей (верифицировано двойным прогоном)
- 2 бага пофикшено post-PR#17: migration constraint vs index, duplicated external_id в .values()

### Guaranteed retrieval slots (PR #18)
- Новый `_STANDING_INTERP_QUERY` с `category=None` для observation/note карт
- `guaranteed_ids` параметр — force-include curated карт в inject
- `_MAX_CARDS` 10→14: 4 curated + 9 risk + 1 checklist
- Multi-snapshot verification: 3/3 снапшота — все 4 карты present

### Knowledge Ablation Eval (minimax-m3)
- 3 сценария × off vs inject = 6 LLM-прогонов
- **M278: 0 violations** в inject-режиме (advisory-only holds)
- Все 4 карты (83-86) использованы LLM: карта 84 (rank-confidence-kelly) — самая impactful
- INJECT-ответы структурированнее, с конкретными порогами (rank ≥ ~0.5, conf ≥ ~0.5)
- OFF → generic, INJECT → decisive ("нет позиции" через Kelly≈0)
- Рекомендовано добавить 2 карты: regime classification + stale data escalation protocol

### Общее
- 129 тестов pass (scheduler + knowledge), ruff 0, pyright 0
- Eval результаты сохранены в `/tmp/eval_*.txt`

## Следующий шаг

Выбор Emma: создание карт 3/4 (regime + stale escalation), Q5-GO, или открытие valve.
