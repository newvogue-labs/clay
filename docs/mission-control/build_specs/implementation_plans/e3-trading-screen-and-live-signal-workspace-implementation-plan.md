> **STATUS: HISTORICAL PLANNING (заморожен).** План относится к этапу планирования (апрель 2026) и сохраняется как исторический контекст.
> Источник истины — `blueprint-v1.md`, `release-gates.md`, ADR (`docs/adr/`) и код (`backend/`).
> Namespace в тексте — планировочный (`clay_mc`, `app/backend`); реальный код использует `clay` / `backend`.

# E3 Implementation Plan — Execution Override (S-EXEC-3c)

Эпик S-EXEC-3c: показать и управлять execution-override во фронтовом trading-workspace.

## Контракт
`WorkspaceStateSnapshot` (ADR-001 addendum 2026-06-28): `execution_override_expires_at`
(ISO UTC, nullable) + `server_time` (ISO UTC). Backend — source of truth; клиент строит
countdown через offset, на истечении делает refetch. Override TTL = 1 час (ADR-025).

## Слайсы
- 3c-0 — backend: `execution_override_expires_at` + `server_time` в snapshot (commit 2f0fc87)
- 3c-1 — TS-типы: catch-up execution-полей + новые поля (commit 1e62e65)
- 3c-2 — header badge + server-synced countdown + refetch на нуле (commit 16a1d5d)
- 3c-3 — модалка confirm/revoke + client-методы + hook-действия + doc

## Ключевые решения
- Offset считается раз на снапшот (useMemo по server_time), тик от абсолютного времени.
- Badge ключится на `execution_override_state`, не на `expires_at`.
- Override-badge — отдельная кнопка в command-strip; orphan-компонент
  workspace-state-banner не воскрешали (dead-code cleanup — отдельно).
- `actor` для override-действий берётся из env `VITE_CLAY_OPERATOR_NAME` (дефолт
  `operator`) — компромисс для single-user. Действия пишутся в provenance/audit
  (ADR-024/025), поэтому привязка к реальной auth/session — отдельный backlog item.
- refetch экспонирован из useWorkspace через nonce (sanctioned useEffectEvent usage).
