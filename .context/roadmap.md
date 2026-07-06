# Roadmap

## ✅ Сделано (Wave 1, все 12 эпиков)

- [x] **E1**: runtime foundation — runtime states, XDG config, service registry, preflight, audit scaffolding
- [x] **E2**: data ingestion and local historical store — PostgreSQL/TimescaleDB, market normalization, repositories
- [x] **E3**: trading workspace and live signal surface — `GET /workspace/trading`, focus control, SSE
- [x] **E4**: control center and runtime operations — `GET /control-center/overview`, `stream`
- [x] **E5**: AI roles, orchestration, and model assignment — `ai-control` registry, review/apply flow
- [x] **E6**: signal lifecycle, ranking, and risk-control — `signal_engine`, confidence penalties, strategy mode
- [x] **E7**: session lifecycle, briefing, pause, and pair replacement — `session_control`, lifecycle routes
- [x] **E8**: demo trading integration and result tracking — `demo_trading` domain, outcome classification
- [x] **E9**: audit trail, feedback, and session review — `session_review`, `review.signal_feedback`
- [x] **E10**: knowledge base and research layer — `knowledge` domain, light-mode storage, advisory retrieval
- [x] **E11**: backtesting, replay, and model/strategy activation — `validation_lab`, replay runs, activation apply
- [x] **E12**: reliability, degraded mode, and release readiness — `reliability` domain, release gates

## ✅ Сделано (Alpha Hardening)

- [x] **Alpha Operator Console** — frontend shell для 7-шагового manual alpha path
- [x] **Runbook-002 (alpha-operator-path)** — формализованный manual flow через существующие API
- [x] **Runbook-002 Appendix (alpha-acceptance-state-map)** — таблица API contracts, state mutations, test coverage
- [x] **AlphaReadinessService** — единый `AlphaReadinessSnapshot` + `gates` + `operator_steps` + `is_next` + `readiness_status`
- [x] **HTTP/API acceptance tests** — `test_alpha_readiness_service.py::test_alpha_operator_path_runs_through_http_api_contracts`
- [x] **Frontend full path test** — `App.test.tsx::runs the full alpha operator console path`
- [x] **Recoverable failure tests** — 3 кейса (no awaiting result, no reviewable record, validation API error)
- [x] **Release readiness overview** — UI surface, alpha readiness gates
- [x] **Operator console hardening** — обработка recoverable errors без скрытой магии

## 🔄 В работе

- (пусто — новая сессия, ждём task-packet)

## ⏭ Дальше

- [ ] **Real-data rehearsal boundaries** (следующий engineering step по Runbook-002 §9):
  - какие реальные/semi-real market/context inputs нужны;
  - какие seeded/test shortcuts больше нельзя считать достаточными;
  - какие operator actions остаются manual-only;
  - какие критерии отличают alpha-core skeleton от alpha rehearsal.
- [ ] **Hardening** — после rehearsal: расширение alpha на реальные данные
- [ ] **Auto-execution** — запрещён до явного approval (Runbook-002 §8)
- [ ] **Wave 2** — TBD (отдельный planning pass)

## 🎯 Цели v1

1. ✅ Primary workflow работает end-to-end (E1-E12 done)
2. ✅ Alpha operator path проверен через `GET /alpha/overview` + 7 domain APIs
3. ✅ Release readiness gates видны (Reliability Center)
4. ⏳ Real-data rehearsal — определить boundaries и перейти к rehearsal mode
5. ⏳ Auto-execution — запрещён (manual-only)

## Запрещено (по Runbook-002 §8)

- ❌ Добавлять отдельный backend orchestrator только для прохождения alpha path
- ❌ Продвигать runbook в UI без успешного ответа domain API
- ❌ Скрывать reliability/demo warnings после финального path complete
- ❌ Считать `operator_path_ready` разрешением на auto-execution
- ❌ Делать destructive runtime action без отдельного operator confirmation
