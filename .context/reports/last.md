# Отчёт: сессия 2026-07-04 — Batch F/G/H + branch-protection + E12.5 CLOSED

## Что сделано

### Batch F (F19+F20) — verification + landing
- Проверено, что Batch F отсутствует в `1223a15` (main до F). F24 (Vitest scope src/) оказался между Batch F и main — сначала F24 → main green (PR #8), затем rebase Batch F → CI green → squash-merge PR #7 (`59119c8`).
- Landing sweep: grep подтвердил все 5 sentinel-паттернов Batch A–F на `59119c8`.

### Batch G (P2 cosmetic) — PR #9
- F7: alpha label flicker — `Loading…` fallback при refresh
- F8: nav click swallow — `AnimatePresence mode="wait"` → default sync
- F14: ai-control `Review {model}` → `Stage {model}…` + tooltip
- F29: `git rm` 3 orphan knowledge panels (0 imports)
- CI success → squash-merge `5d89729`

### Batch H (knowledge-polish) — PR #10
- F27: `DELETE /knowledge/items/{id}` — репозиторий (chunks→item), service (ValueError→404), route, фронт (client+hook+button+confirm), pytest 2 новых
- F28: `isLoading: true` в `refresh()` — консистентность
- CI success → squash-merge `14be6e9`

### Branch-protection (M275)
- `gh api -X PUT` — `required_status_checks.strict=true`, `contexts=["backend","frontend"]`, `enforce_admins=true`, `required_pull_request_reviews=0` (solo), `linear=true`, `force_push=false`, `deletions=false`
- Verify JSON: совпал с ожидаемым 1:1
- M271 dev-DX recon: `de10b26` — предок текущей main → **уже на main**

### Dead-code cleanup — PR #11
- `workspace-state-banner.tsx` — 0 импортов → `git rm`
- Первый PR под новым branch-protection gate
- Main-CI упал на flaky test (pre-existing race condition) → rerun → success
- Merge `a02bc78`

### E12.5 CLOSED
- Все F-тикеты: done или wontfix
- Branch-protection структурно закрывает дыру M275

## Открытые вопросы
1. **Ring 1 GO** — следующий слайс (Q5-гейт, execution layer, real-money gate)
2. **E-KNOW** — новый эпик в карте
3. **Sampler `--noproxy`** — deferred до следующего soak-прогона
