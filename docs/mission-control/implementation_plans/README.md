# Implementation Plans

Здесь лежат implementation plans по отдельным эпикам.

Текущий статус:

1. `e1-runtime-foundation-control-plane-implementation-plan.md`
2. `e2-data-ingestion-and-local-historical-store-implementation-plan.md`
3. `e3-trading-screen-and-live-signal-workspace-implementation-plan.md`
4. `e4-control-center-and-runtime-operations-implementation-plan.md`
5. `e5-ai-roles-orchestration-and-model-assignment-implementation-plan.md`
6. `e6-signal-lifecycle-ranking-and-risk-control-implementation-plan.md`
7. `e7-session-lifecycle-preflight-briefing-active-mode-pause-implementation-plan.md`
8. `e8-demo-trading-integration-and-result-tracking-implementation-plan.md`
9. `e9-audit-trail-feedback-and-session-review-implementation-plan.md`
10. `e10-knowledge-base-and-research-layer-implementation-plan.md`
11. `e11-backtesting-replay-and-model-strategy-activation-implementation-plan.md`
12. `e12-reliability-degraded-mode-and-release-readiness-implementation-plan.md`

Пояснение:

- наличие `E1 implementation plan` не означает, что для каждого следующего эпика план уже автоматически собран;
- `E2 implementation plan` теперь собран и закрывает data-ingestion/storage слой;
- `E3 implementation plan` теперь собран поверх `E1 + E2` contracts и approved `v15` UI baseline.
- `E4 implementation plan` теперь собран как operator/control-plane продолжение поверх `E1 + E2` и `E4 build-spec`.
- `E5 implementation plan` теперь собран как AI-orchestration слой поверх `ADR-005`, `E3`, `E4` и data/runtime foundation.
- `E6 implementation plan` теперь собран как signal/risk слой поверх `E3` workspace contracts и `E5` orchestration semantics.
- `E7 implementation plan` теперь собран как session-discipline слой поверх `E3`, `E4`, `E6` и `E7 build-spec`.
- `E8 implementation plan` теперь собран как demo validation слой поверх `E6`, `E7`, `ADR-004` и `E8 build-spec`.
- `E9 implementation plan` теперь собран как audit/review слой поверх `E6`, `E8`, `ADR-004` и `E9 build-spec`.
- `E10 implementation plan` теперь собран как knowledge/research слой поверх `E9`, `ADR-004` и `E10 build-spec`.
- `E11 implementation plan` теперь собран как validation/activation слой поверх `E5`, `E6`, `E9` и `E11 build-spec`.
- `E12 build-spec` теперь собран как reliability/readiness policy слой поверх `ADR-001..005`, `E7`, `E8`, `E9` и `E11`.
- `E12 implementation plan` теперь собран как operational reliability слой поверх `E7`, `E8`, `E9`, `E11` и `E12 build-spec`.
- `master-planning-review-v1.md` теперь собран как финальный approval-layer для всей planning chain `E1–E12` перед implementation start.

То есть здесь не “пропущен эпик”, а просто planning pipeline пока завершён неравномерно:

- `E1`: есть `build-spec` + `implementation plan`
- `E2`: есть `build-spec` + `implementation plan`
- `E3`: есть `build-spec` + `implementation plan`
- `E4`: есть `build-spec` + `implementation plan`
- `E5`: есть `build-spec` + `implementation plan`
- `E6`: есть `build-spec` + `implementation plan`
- `E7`: есть `build-spec` + `implementation plan`
- `E8`: есть `build-spec` + `implementation plan`
- `E9`: есть `build-spec` + `implementation plan`
- `E10`: есть `build-spec` + `implementation plan`
- `E11`: есть `build-spec` + `implementation plan`
- `E12`: есть `build-spec` + `implementation plan`

Рекомендуемый следующий порядок:

1. использовать `E2 implementation plan` как каноническую основу для data spine и local historical store;
2. использовать `E3 implementation plan` как каноническую основу для analyst-first workspace поверх `HTTP + SSE`;
3. использовать `E4 implementation plan` как каноническую основу для operator control, health visibility и safe runtime actions;
4. использовать `E5 implementation plan` как каноническую основу для AI role model, assignments, fallback и orchestration;
5. использовать `E6 implementation plan` как каноническую основу для signal schema, ranking, lifecycle и risk-control;
6. использовать `E7 implementation plan` как каноническую основу для preflight, briefing, active-session discipline, pause/resume и degraded recovery;
7. использовать `E8 implementation plan` как каноническую основу для manual demo validation, read-only reconciliation и result tracking;
8. использовать `E9 implementation plan` как каноническую основу для audit trail, feedback capture и session review;
9. использовать `E10 implementation plan` как каноническую основу для knowledge light mode, controlled retrieval и research linking;
10. использовать `E11 implementation plan` как каноническую основу для replay, validation summaries и staged activation review;
11. после `E12 implementation plan` считать planning-chain базово закрытой для `v1`;
12. использовать `master-planning-review-v1.md` как финальный review/approval мост перед началом реализации;
13. следующим шагом уже не плодить новые planning-эпики, а переходить к реализации через `Wave 1`;
14. не считать текущую файловую раскладку final-form архитектурой: после demo-обкатки допустим отдельный structural refactor путей и каталогов.
