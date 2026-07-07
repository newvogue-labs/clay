---
name: S-EXEC-3a config unify merge
description: S-EXEC-3a merged: Pydantic ExecutionConfig dropped, live-rejection warning added
type: project
---

**Проблема/Контекст:**

Design-confirm 3a после ревью (C1/C2/C3). D8 требовал independent verification «0 prod-readers» перед удалением Pydantic ExecutionConfig из config/models.py. Recon на main подтвердил: CONFIG_MODELS = {runtime, risk}, bootstrap использует dataclass, Pydantic-твин мёртв. C2 (clamp live→dry_run) — оказалась уже существующей; Emma's заявка «live пропускается» была recon-ошибкой (читала множество как включающее "live").

**Решение/Вывод:**

Удалён Pydantic ExecutionConfig из config/models.py (−14 строк). Добавлен logger.warning на rejected CLAY_EXECUTION_MODE в execution/config.py (+4 строки). Кламп {dry_run, testnet} уже existed, поведение не меняется. Full suite 682 passed, ruff 0. PR #1 merged no-ff → bc64600. Branch deleted.

**Why/How to apply:**

Lesson: connector loadFile/loadPR/loadCommit имеет fallback-ограничение для непримёрдженных feature-веток — читает только то, что достижимо из default-branch. Для верификации непримёрдженного контента использовать только loadPR diff (partial) + host-side git diff --stat/--full-diff, а не loadFile по имени ветки или SHA.
Post-merge сверка обязательна для подтверждения удаления мёртвого кода.
