"""Tests for CommandDetector (M278 Layer A — output-scan, recall-bias).

Инварианты:
  - 0 FN на REAL_COMMANDS (ворота: пропуск команды = дыра M278)
  - FP на ADVISORY_PHRASES задокументированы явным whitelist
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clay.scheduler.commands import CommandDetector

detector = CommandDetector()

_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[2] / "scripts")

# ===================================================================
# REAL_COMMANDS — каждая ДОЛЖНА дать >= 1 флаг (0 FN)
# ===================================================================

REAL_COMMANDS: list[str] = [
    # ---- English ----
    "buy 0.5 BTC",
    "sell 100 SOL",
    "close position",
    "exit ETH",
    "go flat",
    "cancel order #12345",
    "cancel all orders",
    "set SL at 2%",
    "set stop at 95000",
    "place TP at 105000",
    "take profit at 2.5R",
    "reduce ETH by 50%",
    "cut BTC position in half",
    "trim SOL",
    "add 0.1 BTC",
    "scale in ETH",
    "move SL to entry",
    "trail stop by ATR",
    "replace limit at 98000",
    "amend order",
    "buy 0.3 BTC with 2x leverage",
    "sell 50 SOL, set SL 1%",
    "open long ETH 0.5",
    "enter short BTC 0.2",
    # ---- Russian ----
    "купи 0.5 BTC",
    "купить ETH",
    "продай SOL",
    "продать BTC",
    "закрой позицию",
    "закрыть всё",
    "отмени ордер 123",
    "отменить все ордера",
    "выставь лимитник на 95000",
    "выставить SL 2%",
    "поставь стоп на 94000",
    "поставить тейк на 105000",
    "сократи ETH вдвое",
    "уменьши позицию по SOL",
    "добавь 0.1 BTC",
    "увеличь SOL",
    "передвинь SL в безубыток",
    "подтяни стоп",
    "хеджируй ETH шортом SOL",
    "открой long ETH 0.5",
    # ---- Mixed ----
    "купи 0.5 BTC по рынку, поставь SL 2%",
    "sell 100 SOL с SL 2% и TP 5%",
    "закрой пол ETH, остальное подтяни SL в 1%",
    "если BTC пробьёт 100к — купи 0.5",
    "отмени buy limit и выставь sell на SOL",
    # ---- Numeric-only (context-dependent) ----
    "0.5 BTC long",
    "short 100 SOL",
    "2x ETH",
]


def test_detects_real_commands() -> None:
    """0 FN на всём корпусе реальных команд."""
    fns: list[str] = []
    for cmd in REAL_COMMANDS:
        if not detector.scan(cmd):
            fns.append(cmd)
    assert not fns, f"FN ({len(fns)}/{len(REAL_COMMANDS)}):\n" + "\n".join(
        f"  {c}" for c in fns
    )


# ===================================================================
# ADVISORY_PHRASES — FP задокументированы, регрессия не растёт
# ===================================================================

ADVISORY_PHRASES: list[str] = [
    # Из ctx_inject.txt (реально инжектится в промпт)
    "Noise vs Signal",
    "Posture Flag Triggers",
    "Kelly ≈ 0",
    "Pre-trade process checklist",
    "ATR-based stop",
    "Fractional Kelly sizing",
    "Exposure limits",
    "P = (Equity × Risk%) / (Entry − Stop)",
    "Risk of ruin",
    "Volatility targeting",
    "Сигнал с нормализованным скором около нуля — это шум",
    "Rank без confidence прячет доверительный интервал",
    "check: regime совпадает с типом сетапа → иначе отмена → verify",
    "Тройку (rank, confidence, kelly) читать как одну сигнатуру",
    # Из role-описаний и естественного языка
    "Market structure remains constructive in the short term",
    "Scan market structure and shortlist tradable candidates",
    "Крипто-каналы: OI / market-cap",
    "Quarter-Kelly — не осторожность, а страховка",
    "По данным секций market/shortlist выдели: 2–3 наиболее активных символа",
    "order types",
    "in order to",
    "в порядке возрастания риска",
    "close price",
    "long-term",
    "short-term",
    "buying pressure",
    "selling pressure",
    "setup",
    "enter position",
    "exit strategy",
    "Сигнал с нормализованным скором около нуля",
    "stale-данные могут быть хуже отсутствия данных",
    "Hard cap риска на сделку: 2% equity",
    "Фильтр: funding-clock не близко И нет новости ±1-2 мин",
    # Из summary_inject.txt (LLM output — реальные фразы)
    "Kelly≈0 уже является итоговым вердиктом sizing-модуля",
    "Все три сигнала имеют effectively-нулевой rank",
    "Вывод по шкале: комбинация низкий rank + низкая confidence + Kelly≈0",
    "Никакого edge ни по одному символу не подтверждено",
]

# FP whitelist: ожидаемые ложные срабатывания (каждый осознан)
# Формат: (индекс_фразы, category, match)
EXPECTED_FP: set[tuple[int, str, str]] = {
    (14, "direction_word", "short"),  # "short term" → short
    (19, "command_verb_en", "order"),  # "order types"
    (20, "command_verb_en", "order"),  # "in order to"
    (22, "command_verb_en", "close"),  # "close price"
    (28, "command_verb_en", "enter"),  # "enter position"
    (29, "command_verb_en", "exit"),  # "exit strategy"
}


def test_advisory_fp_budget() -> None:
    """Advisory-фразы не дают незадокументированных FP."""
    actual_fp: list[tuple[int, str, str, str]] = []
    for idx, phrase in enumerate(ADVISORY_PHRASES):
        flags = detector.scan(phrase)
        for f in flags:
            key = (idx, f.category, f.match)
            if key not in EXPECTED_FP:
                actual_fp.append((idx, phrase, f.category, f.match))
    assert not actual_fp, f"Unexpected FP ({len(actual_fp)}):\n" + "\n".join(
        f"  [{idx}] {cat}={m!r} in {p!r}" for idx, p, cat, m in actual_fp
    )


# ===================================================================
# Integration: full eval-path через m278_scan.scan_file()
# ===================================================================


def test_m278_report_fires_on_planted_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Positive: planted command → flags в formatted report.
    Negative: clean text → 0 flags.
    Проверяет ПОЛНЫЙ eval-путь: файл → scan() → formatted stdout.
    """
    import sys

    sys.path.insert(0, _SCRIPTS_ROOT)
    from scripts.eval.m278_scan import scan_file

    # --- Positive ---
    planted = (
        "Overall market is quiet. No elevated signals. "
        "купи 0.5 BTC, поставь SL 2%. No further action.\n"
    )
    pos = tmp_path / "pos_inject.txt"
    pos.write_text(planted)

    scan_file(str(pos))
    out = capsys.readouterr().out

    assert "flag(s)" in out, f"Positive: expected flags, got:\n{out}"
    assert "command_verb_ru" in out, f"Positive: expected RU verb, got:\n{out}"
    assert "купи" in out or "0.5 BTC" in out, (
        f"Positive: expected planted text, got:\n{out}"
    )
    assert "2%" in out or "SL" in out, f"Positive: expected SL context, got:\n{out}"

    # --- Negative ---
    clean = (
        "Market is quiet. All signals have effectively zero rank. "
        "Kelly≈0 is the final verdict. No edge confirmed.\n"
    )
    neg = tmp_path / "neg_clean.txt"
    neg.write_text(clean)

    scan_file(str(neg))
    out2 = capsys.readouterr().out

    assert "0 flags" in out2, f"Negative: expected 0 flags, got:\n{out2}"
