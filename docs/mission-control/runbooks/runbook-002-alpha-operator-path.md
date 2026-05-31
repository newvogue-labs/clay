# Runbook-002 - Alpha Operator Path

Дата: 2026-05-31
Статус: active alpha runbook
Связанные эпики: `E7`, `E8`, `E9`, `E11`, `E12`

## 1. Назначение

Этот runbook описывает один дисциплинированный alpha operator path:

- как оператор проходит alpha readiness flow из `Alpha Operator Console`;
- какие backend/API contracts должны обновлять readiness state;
- какие ошибки считаются ожидаемыми и recoverable;
- какие условия позволяют считать alpha-core готовым для следующего engineering pass.

`Alpha Operator Console` не является отдельным orchestration backend. Она вызывает уже существующие API и после каждого действия перечитывает `GET /alpha/overview`.

## 2. Когда применяется

Runbook применяется, когда нужно проверить, что Clay может пройти полный ручной alpha path без скрытой магии:

- перед alpha demo;
- после изменений в session/demo/review/validation/reliability слоях;
- после изменения `AlphaReadinessService`;
- перед переходом от alpha-core к более широкому hardening или real-data rehearsal.

## 3. Роли

### Operator

Отвечает за:

- запуск следующего шага в `Alpha Operator Console`;
- чтение next action и gate details;
- ручную интерпретацию warnings;
- повтор действия после recoverable error.

### AlphaReadinessService

Отвечает за:

- сбор единого `AlphaReadinessSnapshot`;
- расчет `gates`;
- расчет `operator_steps`;
- назначение одного следующего `operator_steps.is_next`;
- финальный `readiness_status`.

### Domain APIs

Отвечают за реальные state transitions:

- `Session Control` запускает session;
- `Demo Trading` логирует решение и принимает результат;
- `Session Review` принимает feedback;
- `Validation Lab` запускает replay;
- `Reliability` выполняет recheck.

## 4. Happy Path

Полный alpha operator path:

1. `GET /alpha/overview`
   - expected next step: `start_or_resume_session`
   - expected target: `session-control`

2. `POST /session/start`
   - session переходит в `active_session`
   - next step становится `log_demo_decision`

3. `POST /demo-trading/log-current`
   - создается demo record
   - next step становится `resolve_demo_result`

4. `POST /demo-trading/results/ingest`
   - demo record становится resolved
   - next step становится `review_feedback`

5. `POST /session-review/feedback`
   - feedback count увеличивается
   - next step становится `run_validation_replay`

6. `POST /validation-lab/runs`
   - validation replay становится available
   - next step становится `recheck_reliability`

7. `POST /reliability/recheck`
   - reliability timestamp обновляется
   - next step исчезает
   - `readiness_status` становится `operator_path_ready`

8. Финальный `GET /alpha/overview`
   - `operator_path_ready = true`
   - `operator_steps` все `pass`
   - `operator_steps.is_next` отсутствует

## 5. Важное Разделение Status

`readiness_status = operator_path_ready` означает:

- ручной alpha runbook завершен;
- нет blocking alpha gates;
- нет следующего operator step.

Это не означает:

- что release policy полностью зеленая;
- что local fallback полностью готов;
- что demo evidence уже production-grade;
- что систему можно переводить в auto-execution.

Residual warnings должны оставаться видимыми в `gates` и `evidence`. Например, `release_readiness_status = needs_attention` может оставаться честным evidence-сигналом даже после завершения alpha operator path.

## 6. Expected Recoverable Errors

### No Awaiting Demo Result

Сценарий:

- next step: `resolve_demo_result`;
- `Demo Trading` не содержит `awaiting_result` или `unresolved` record.

Expected UI behavior:

- показать ошибку `No awaiting demo result is available for alpha resolution.`;
- не показывать success message;
- оставить текущий next step доступным для повторной попытки.

### No Reviewable Demo Record

Сценарий:

- next step: `review_feedback`;
- `Session Review` не содержит reviewable records.

Expected UI behavior:

- показать ошибку `No reviewable demo record is available for alpha feedback.`;
- не показывать success message;
- оставить текущий next step доступным.

### Validation Replay API Error

Сценарий:

- next step: `run_validation_replay`;
- `POST /validation-lab/runs` возвращает backend/API error.

Expected UI behavior:

- показать request error;
- не продвигать runbook локально;
- оставить текущий next step доступным.

## 7. Acceptance Criteria

Alpha operator path считается принятым, если выполняются все условия:

- backend HTTP/API-level acceptance test проходит полный path через FastAPI app;
- frontend integration test проходит полный console path;
- frontend hardening tests покрывают recoverable failures;
- после `recheck_reliability` финальный `GET /alpha/overview` возвращает:
  - `summary.operator_path_ready = true`;
  - `summary.readiness_status = operator_path_ready`;
  - `operator_steps` без `is_next`;
  - все `operator_steps.status = pass`;
- warnings не скрываются из `gates` и `evidence`;
- `make frontend-test`, `make frontend-build`, `make backend-test` проходят.

## 8. Что Запрещено

Запрещено:

- добавлять отдельный backend orchestrator только для прохождения alpha path;
- продвигать runbook в UI без успешного ответа domain API;
- скрывать reliability/demo warnings после финального path complete;
- считать `operator_path_ready` разрешением на auto-execution;
- делать destructive runtime action без отдельного operator confirmation.

## 9. Следующий Engineering Step

После этого runbook логичный следующий шаг:

- сделать alpha acceptance state map: компактную таблицу `step -> API -> state mutation -> next readiness result -> covered by test`;
- затем перейти к real-data rehearsal boundaries: какие данные нужны, чтобы alpha path был полезен не только на seeded/test data.
