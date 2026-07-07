# Отчёт: сессия 2026-07-06 — M278 detector + ablation eval

## Что сделано

### M278 детектор (Layer A output-scan) — PR #21
- **CommandDetector** в `backend/src/clay/scheduler/commands.py` — verb sets EN+RU, excluded compounds (shortlist/long-term/orderbook/buying/selling/setup/stop-loss), numeric direction/leverage regex
- **scan(text) → list[MatchFlag]** — (match, category, span)
- **0 FN** на 52 реальных командах, **6 FP** задокументированы
- **Тест-корпус** — REAL_COMMANDS (52) + ADVISORY_PHRASES (38)
- **Integration test** — `test_m278_report_fires_on_planted_command` (positive + negative control через `m278_scan.scan_file()`)
- **m278_scan.py** — standalone scanner для любого текстового файла
- **knowledge_ablation_llm.py** — +M278 report после off/inject LLM-прогона
- **Makefile** — `backend-eval-m278`, `backend-eval-ablation`
- **114/114 pass**, ruff 0, pyright 0
- **PR #21 merged → main @ `444482f`**

### Full ablation eval (minimax-m3)
- **3 сценария** (quiet, strong, mixed) × off vs inject = 6 LLM-прогонов
- **Обнаружен и починен баг:** `CLAY_LLM_TIMEOUT_SECONDS=30` не хватало (minimax-m3 отвечает за 40-70s) → установлен 180s
- **M278: 0 violations** на всём корпусе
- **kn-91 (pre-trade checklist) цитирован** в quiet/inject — полезен
- **kn-92 execution — НЕ появляется** нигде (EXCLUDED_TAGS работает)
- **interp cards:** kn-84 (3/3), kn-95 (3/3), kn-96 (3/3)
- **Inject лучше off:** структурированные таблицы, framework (kn-84), provenance
- **Замечание:** strong/mixed inject обрезаны (max_tokens=512 мало)

## Следующий шаг

Очередь: карта 7 → Q5-GO → valve. Layer B отложен. Жду выбора Emma.
