"""Guard: soak-вердикт (D-58) — три обязательные ветки на функции вердикта.

  (1) ЛОВИТ: лог с настоящей деградацией → FAIL (тест доказывает отлов);
  (2) ПУСТОЙ ВХОД: пустой/слишком короткий лог → FAIL, а не пустой PASS;
  (3) НЕТ ВТОРОГО ПУТИ: PASS достижим ТОЛЬКО оценкой сэмплов — нет
      env-флага/устаревшего артефакта, дающего PASS в обход (битый/
      отсутствующий verdict.json ≠ PASS).

Hermetic: только локальные tmp-директории, без сети, без ключей.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime, timedelta

from clay.ops.soak_harness import FAIL, PASS, HealthSample, evaluate_soak, load_verdict

_REPO = pathlib.Path(__file__).resolve().parents[3]
_SRC = _REPO / "backend" / "src"


def _samples(count: int, *, degraded_at: int | None = None) -> list[HealthSample]:
    """Генерирует ``count`` healthy-сэмплов с шагом 600с; ``degraded_at`` — индекс."""
    start = datetime(2026, 8, 2, 0, 0, 0, tzinfo=UTC)
    samples: list[HealthSample] = []
    for index in range(count):
        ts = (start + timedelta(seconds=600 * index)).isoformat()
        degraded = index == degraded_at
        samples.append(
            HealthSample(
                ts=ts,
                overall_status="degraded" if degraded else "healthy",
                components={"runtime-stability": "fail" if degraded else "pass"},
                classification="degraded" if degraded else "healthy",
            )
        )
    return samples


def _evaluate(samples: list[HealthSample]) -> str:
    return evaluate_soak(
        samples,
        required_duration=3_600.0,
        interval=600.0,
        anomaly_threshold=600.0,
    ).verdict


class TestBranch1CatchesRealDegradation:
    def test_healthy_log_passes(self) -> None:
        assert _evaluate(_samples(12)) == PASS

    def test_degraded_episode_fails(self) -> None:
        """Лог с настоящей деградацией → FAIL — охранник ловит."""
        samples = _samples(12)
        # 4 подряд degraded (длительность 1800с >= порог 600с, завершён).
        for index in range(6, 10):
            samples[index] = HealthSample(
                ts=samples[index].ts,
                overall_status="degraded",
                components={"runtime-stability": "fail"},
                classification="degraded",
            )
        assert _evaluate(samples) == FAIL


class TestBranch2EmptyAndShortInputFails:
    def test_empty_log_fails(self) -> None:
        """0 сэмплов → FAIL, а не пустой PASS."""
        assert _evaluate([]) == FAIL

    def test_short_span_fails(self) -> None:
        """Span < требуемой длительности → FAIL."""
        # 4 сэмпла × 600с → span 2400с < 3600с.
        assert _evaluate(_samples(4)) == FAIL

    def test_too_few_samples_fails(self) -> None:
        """Число сэмплов < пола → FAIL (явный ``min_samples``)."""
        verdict = evaluate_soak(
            _samples(12),
            required_duration=3_600.0,
            interval=600.0,
            anomaly_threshold=600.0,
            min_samples=30,
        )
        assert verdict.verdict == FAIL


class TestBranch3NoSecondPathToPass:
    def test_broken_verdict_json_is_not_pass(self, tmp_path) -> None:
        """Битый verdict.json ≠ PASS — только оценка сэмплов даёт PASS."""
        broken = tmp_path / "verdict.json"
        broken.write_text(
            '{"verdict": "PASS", "sample_count": "not-an-int",', encoding="utf-8"
        )
        assert load_verdict(broken) is None

    def test_missing_verdict_json_is_not_pass(self, tmp_path) -> None:
        assert load_verdict(tmp_path / "nope.json") is None

    def test_wrong_verdict_in_file_is_rejected(self, tmp_path) -> None:
        """Даже валидный JSON с чужой схемой не читается как PASS."""
        bogus = tmp_path / "verdict.json"
        bogus.write_text(json.dumps({"ok": True}), encoding="utf-8")
        assert load_verdict(bogus) is None

    def test_no_env_force_flag_in_src(self) -> None:
        """В soak-модуле нет env-флага, форсирующего PASS в обход сэмплов."""
        text = (_SRC / "clay" / "ops" / "soak_harness.py").read_text(encoding="utf-8")
        assert "FORCE" not in text
        assert "SOAK_VERDICT" not in text
        assert "SOAK_PASS" not in text

    def test_cli_never_reads_stale_verdict_as_source(self) -> None:
        """CLI производит вердикт только из ``evaluate_soak``, не из старого файла.

        Единственные вызовы ``evaluate_soak`` — в ``SoakHarness.run`` и в
        ``main`` (обычный путь + ветка KeyboardInterrupt). ``load_verdict``
        существует только как читатель артефакта для человека/инструментов.
        """
        text = (_SRC / "clay" / "ops" / "soak_harness.py").read_text(encoding="utf-8")
        assert (
            text.count("evaluate_soak(") == 3
        )  # def + run() + main()/KeyboardInterrupt
        # main не присваивает PASS напрямую — только из вердикта оценки сэмплов
        # (``verdict = PASS`` легитимно живёт внутри evaluate_soak).
        _, _, main_block = text.partition("def main(")
        assert "verdict = PASS" not in main_block
