# E11 Build Spec — Backtesting, Replay And Model/Strategy Activation

Дата: 2026-04-15
Эпик: `E11`
Статус: build-spec draft v1
Основа:
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/blueprint-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/execution-backlog-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/tech-stack-v1.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-001-runtime-state-model.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-002-config-validation-and-rollback-policy.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-004-storage-baseline-and-phased-extensions.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/adrs/adr-005-model-provider-abstraction.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e6-signal-lifecycle-ranking-and-risk-control.md`
- `/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/build_specs/e9-audit-trail-feedback-and-session-review.md`

## 1. Цель эпика

Собрать `validation and activation layer` для `CLAY Mission Control`, который:

- даёт системе осмысленный `backtesting / replay` в базовом виде;
- позволяет сравнивать стратегии, модели и качество сигналов на истории;
- связывает replay с review/history контуром, а не держит его отдельной игрушкой;
- вводит `activation review-card` перед включением новой модели или стратегии;
- не допускает silent activation без operator confirmation и при необходимости без повторного `preflight`.

`E11` нужен, чтобы новые идеи попадали в рабочий runtime не через ритуал “кажется, это должно быть лучше”, а через понятный validation loop. Иначе мы просто научимся красиво переименовывать риск в “экспериментальность” 😼

## 2. Входит в scope

- `backtesting scope v1`
- `replay workflow`
- model comparison semantics
- signal quality on history
- activation review workflow for model/strategy changes
- mandatory review-card before activation
- activation confirmation and preflight relationship
- UI-facing contracts for replay and activation review

## 3. Не входит в scope

- full institutional backtesting platform
- high-frequency simulation
- live order execution
- silent self-activation of models or strategies
- automatic policy override after a “good” backtest
- replacing demo validation with replay-only evidence

## 4. Архитектурные допущения

- `E11` опирается на `E5` model/provider assignments, `E6` signal semantics и `E9` review/history layer
- replay использует локально накопленную историю и не требует online retrieval as hard dependency
- market bars, signals, decisions, feedback и audit уже хранятся как объяснимая основа для replay/review
- activation of new model/strategy remains operator-reviewed and can require `preflight before activation`
- browser-facing replay and activation review interactions идут через `HTTP/JSON`, realtime progress при необходимости может идти через `SSE`
- replay/backtesting в `v1` остаётся analyst-support tool, а не magical truth oracle

## 5. Главный результат эпика

После завершения `E11` разработчик должен получить:

- канонический `backtesting / replay scope v1`;
- ясную replay workflow модель;
- минимальный набор validation metrics;
- review-card discipline перед activation новой модели/стратегии;
- acceptance criteria, по которым можно проверить, что activation опирается на evidence и confirmation, а не на внезапную уверенность.

## 6. Главные пользовательские сценарии

### A. Strategy replay

Пользователь:

- выбирает исторический период;
- запускает replay;
- видит, какие сигналы и решения система показала бы на этом участке;
- связывает результаты с review screen.

### B. Model comparison

Пользователь:

- сравнивает несколько model/strategy variants;
- смотрит quality metrics;
- не активирует вариант автоматически только потому, что одна метрика выглядит вкусно.

Система обязана:

- показать сравнение;
- показать ограничения и контекст;
- не маскировать слабые места за одной красивой цифрой.

### C. Signal quality on history

Система должна уметь показать:

- сколько сигналов было;
- сколько были valid vs weak vs invalidated;
- как это коррелировало с outcomes на истории;
- где signal quality деградировала.

### D. Activation review-card

Перед включением новой модели/стратегии пользователь обязан увидеть:

- review-card;
- summary of evidence;
- risks and limitations;
- confirmation requirement;
- нужна ли повторная `preflight` валидация.

## 7. Канонические сущности E11

### 7.1 Replay run

Минимальные поля:

- `replay_id`
- `started_at`
- `completed_at | null`
- `time_range`
- `strategy_variant`
- `model_variant | null`
- `status`

### 7.2 Validation summary

Минимальные поля:

- `summary_id`
- `replay_id`
- `signal_count`
- `high_confidence_count`
- `weakening_count`
- `invalidated_count`
- `mismatch_count`
- `quality_notes[]`

### 7.3 Model/strategy comparison record

Минимальные поля:

- `comparison_id`
- `candidate_id`
- `candidate_type`
- `baseline_id`
- `metric_bundle`
- `risk_notes[]`
- `decision_readiness`

### 7.4 Activation review-card

Минимальные поля:

- `review_card_id`
- `candidate_id`
- `candidate_type`
- `evidence_summary`
- `key_metrics`
- `risks[]`
- `requires_preflight`
- `requires_confirmation`

## 8. Backtesting scope policy

### 8.1 Что входит в `v1`

В `v1` backtesting scope обязан покрывать минимум:

- strategy replay
- model comparison
- signal quality on history

### 8.2 Что `v1` не обещает

`E11` не обещает:

- идеальную market simulation;
- exchange-grade execution modelling;
- exhaustive slippage realism;
- абсолютную истину вместо demo validation.

### 8.3 Базовое правило

Replay/backtesting в `v1` нужен для validation and learning, а не для самообмана уровня “цифра в отчёте = рынок обязан подчиниться”.

## 9. Replay workflow policy

### 9.1 Как запускается replay

Пользователь выбирает:

- исторический период;
- strategy/model candidate;
- вариант сравнения;
- при необходимости filters/context.

### 9.2 Что показывает replay

Минимум:

- replay timeline;
- generated signals;
- confidence and invalidation states;
- key decisions;
- summary metrics;
- link to review context.

### 9.3 Связь с review screen

Replay обязан быть связан с review/history, чтобы:

- пользователь видел continuity между real sessions и validation;
- идеи можно было объяснять через прошлую evidence base;
- replay не превращался в isolated sandbox без памяти.

## 10. Validation metrics policy

### 10.1 Минимальные метрики

- signal count
- valid/high-confidence count
- weakening count
- invalidated count
- mismatch count
- coarse quality summary

### 10.2 Что важно

Validation metrics не должны сводиться к одной “прибыльности”, потому что:

- replay не заменяет demo;
- poor signal discipline может быть скрыта одной удачной серией;
- comparison должен учитывать quality, consistency и risk notes.

### 10.3 Что запрещено

Нельзя:

- активировать candidate по одной красивой метрике;
- скрывать invalidations и weak signals;
- считать replay-only evidence достаточным для confidence uplift без operator review.

## 11. Activation review workflow

### 11.1 Review-card обязателен

Перед activation новой модели или стратегии UI обязан:

- показать review-card;
- показать роль/candidate type;
- показать evidence summary;
- показать capability/risk summary;
- требовать confirmation.

### 11.2 Обязательные данные review-card

Минимум:

- candidate name/version
- baseline comparison
- metric bundle
- key risks
- degraded/fallback implications
- whether `preflight` is required before activation

### 11.3 Что запрещено

Нельзя:

- silently переключать model/strategy assignment;
- выдавать candidate recommendation за уже применённое решение;
- терять audit trace review-card acknowledgment.

## 12. Activation and preflight relationship

### 12.1 Базовое правило

Если изменение требует `preflight before activation`, система обязана:

- оставить activation staged;
- не переводить runtime в normal active mode без повторной проверки;
- показывать пользователю, что candidate ещё не operationally admitted.

### 12.2 Что означает staged activation

`Staged` activation значит:

- review-card подтверждён;
- candidate выбран;
- но operational enablement ждёт preflight или safe apply path.

### 12.3 Что запрещено

Нельзя:

- bypass’ить preflight через UI convenience;
- активировать candidate только потому, что replay был красивым;
- скрывать unsafe state transition behind “Apply”.

## 13. UI-facing contracts после `E11`

### 13.1 Replay run contract

Минимальные поля:

- `replay_id`
- `status`
- `time_range_label`
- `strategy_variant`
- `model_variant | null`
- `timeline_items[]`

### 13.2 Validation summary contract

Минимальные поля:

- `summary_id`
- `signal_count`
- `high_confidence_count`
- `weakening_count`
- `invalidated_count`
- `mismatch_count`
- `quality_notes[]`

### 13.3 Comparison card contract

Минимальные поля:

- `candidate_id`
- `candidate_type`
- `baseline_id`
- `metric_bundle`
- `risk_notes[]`
- `decision_readiness`

### 13.4 Activation review-card contract

Минимальные поля:

- `review_card_id`
- `candidate_id`
- `candidate_type`
- `evidence_summary`
- `risks[]`
- `requires_preflight`
- `requires_confirmation`

## 14. Transport and interaction expectations

### 14.1 HTTP snapshot examples

- `GET /replay/runs`
- `GET /replay/runs/{replayId}`
- `GET /validation/comparisons`
- `GET /activation-review/{candidateId}`

### 14.2 HTTP command examples

- `POST /replay/run`
- `POST /validation/compare`
- `POST /activation-review/{candidateId}/confirm`
- `POST /activation-review/{candidateId}/stage`

### 14.3 SSE stream examples

- `GET /replay/stream`
- `GET /activation-review/stream`

### 14.4 Что нельзя

Нельзя:

- строить replay только как frontend toy-state;
- подменять activation workflow локальным toggle without backend truth;
- смешивать validation progress и runtime state changes без явных границ.

## 15. Failure modes, которые `E11` обязан учитывать

### A. Replay не может быть собран на выбранный период

Система обязана:

- честно показать insufficent historical basis;
- не рисовать synthetic confidence;
- не ломать основной runtime.

### B. Candidate красивый в replay, но risky operationally

Система обязана:

- показать risk notes;
- не auto-activate candidate;
- требовать review-card confirmation и при необходимости preflight.

### C. Review-card подтверждён, но preflight провален

Система обязана:

- оставить activation staged or rejected;
- не пускать candidate в normal active mode;
- сохранить audit trace.

### D. Comparison скрывает слабости baseline/candidate

Система обязана:

- не обрезать negative evidence;
- показывать invalidations, weak signals и mismatches;
- не превращать comparison в marketing card.

## 16. Acceptance criteria

Эпик `E11` считается готовым, если выполняются все условия:

1. `Backtesting / replay v1` имеет ограниченный, но ясный scope.
2. Replay workflow позволяет выбрать период и увидеть signals/summary/history link.
3. Validation metrics покрывают не только красивый итог, но и quality/risk semantics.
4. Review-card обязателен перед activation новой модели/стратегии.
5. Activation не может silently bypass confirmation и при необходимости `preflight`.
6. UI-facing contracts позволяют построить replay and activation-review surfaces без ad-hoc parsing.
7. Failure modes around missing history, risky candidates and failed preflight описаны явно.

## 17. Обязательные проверки для `E11`

- проверить replay period selection and result rendering;
- проверить model/strategy comparison rendering;
- проверить visibility invalidated/weak signals in validation summary;
- проверить activation review-card completeness;
- проверить confirmation requirement before activation;
- проверить staged activation when preflight is required;
- проверить blocked activation after failed preflight;
- проверить audit trace for review-card and activation decisions.

## 18. Dependencies и границы с соседними эпиками

### 18.1 Зависимости

`E11` зависит минимум от:

- `E5` model/provider assignments
- `E6` signal semantics
- `E9` review/history evidence layer

### 18.2 Граница с `E10`

`E10` может давать supporting knowledge/research context.

`E11` не должен:

- зависеть от retrieval как hard blocker;
- превращать knowledge hits в единственное основание для activation;
- путать research support с validation evidence.

### 18.3 Граница с `E12`

`E12` отвечает за release readiness and degraded reliability.

`E11` готовит validation and activation discipline, но не закрывает release gates целиком.

### 18.4 Граница с live/demo evidence

Replay не заменяет demo validation.

Он дополняет её и помогает принимать более осторожные решения.

## 19. Артефакты, которые должны следовать после `E11 build-spec`

Сразу после `E11` логично подготовить:

- `E11 implementation plan — Backtesting, Replay And Model/Strategy Activation`
- `E12 build-spec — Reliability, Degraded Mode And Release Readiness`
- при необходимости отдельный runbook по `activation review and staged apply`

Если нужен execution-grade уровень детализации для разработки, следующим артефактом после утверждения этого документа должен стать отдельный `implementation plan` для `E11`.
