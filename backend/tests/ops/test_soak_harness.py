"""Unit-тесты soak-харнесса (D-58): D1 сэмплер, D2 вердикт, D3 resume/gap.

Герметичность: фейковые часы (``VirtualClock``) + фейковый health-источник,
без сети и без торговых вызовов. ``sleep_fn`` двигает виртуальные часы вперёд,
поэтому полный прогон выполняется мгновенно.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from clay.core.clock import VirtualClock
from clay.ops.soak_harness import (
    DEFAULT_INTERVAL_SECONDS,
    FAIL,
    PASS,
    HealthSample,
    SoakHarness,
    SoakLogFile,
    evaluate_soak,
    load_verdict,
    resolve_soak_dir,
    write_verdict_artifacts,
)

START = datetime(2026, 8, 2, 0, 0, 0, tzinfo=UTC)


class FakeHealthSource:
    """Фейковый источник: выдаёт заданную последовательность статусов."""

    def __init__(self, statuses: list[str]) -> None:
        self._statuses = statuses
        self.calls = 0

    def sample(self, now: datetime) -> HealthSample:
        status = self._statuses[min(self.calls, len(self._statuses) - 1)]
        self.calls += 1
        return HealthSample(
            ts=now.isoformat(),
            overall_status="healthy" if status == "healthy" else "degraded",
            components={"runtime-stability": status, "data-freshness": "pass"},
            classification=status,
        )


class InterruptingSource:
    """Источник, эмулирующий прерывание харнесса после N сэмплов."""

    def __init__(self, status: str, interrupt_after: int) -> None:
        self._status = status
        self._interrupt_after = interrupt_after
        self.calls = 0

    def sample(self, now: datetime) -> HealthSample:
        if self.calls >= self._interrupt_after:
            raise KeyboardInterrupt
        self.calls += 1
        return HealthSample(
            ts=now.isoformat(),
            overall_status="healthy",
            components={"runtime-stability": "pass"},
            classification="healthy",
        )


def _mk(
    statuses: list[str],
    *,
    start: datetime = START,
    interval_s: float = 600.0,
) -> list[HealthSample]:
    """Строит лог сэмплов с шагом ``interval_s`` от ``start``."""
    now = start
    samples: list[HealthSample] = []
    for status in statuses:
        samples.append(
            HealthSample(
                ts=now.isoformat(),
                overall_status="healthy" if status == "healthy" else "degraded",
                components={"runtime-stability": status},
                classification=status,
            )
        )
        now = now + timedelta(seconds=interval_s)
    return samples


def _run(
    tmp_path: Path,
    *,
    statuses: list[str],
    interval: float = 100.0,
    duration: float = 300.0,
    start: datetime = START,
    anomaly_threshold: float = DEFAULT_INTERVAL_SECONDS,
    max_gap: float | None = None,
    min_samples: int | None = None,
) -> tuple[SoakHarness, SoakLogFile, VirtualClock, FakeHealthSource]:
    clock = VirtualClock(start)
    source = FakeHealthSource(statuses)
    log = SoakLogFile(tmp_path / "soak" / "run.jsonl")

    def fake_sleep(delta: float) -> None:
        clock.tick(timedelta(seconds=delta))

    harness = SoakHarness(
        health_source=source,
        log=log,
        interval=interval,
        duration=duration,
        anomaly_threshold=anomaly_threshold,
        max_gap=max_gap,
        min_samples=min_samples,
        clock=clock,
        sleep_fn=fake_sleep,
    )
    return harness, log, clock, source


class TestD1HarnessSampler:
    def test_n_samples_over_n_intervals(self, tmp_path: Path) -> None:
        """Ровно N сэмплов за N интервалов (Приёмка D1)."""
        harness, log, _, source = _run(
            tmp_path,
            statuses=["healthy"] * 10,
            interval=100.0,
            duration=300.0,
        )
        verdict = harness.run()

        samples = log.read()
        assert len(samples) == 3
        assert source.calls == 3
        assert verdict.verdict == PASS
        assert [s.ts for s in samples] == [
            START.isoformat(),
            (START + timedelta(seconds=100)).isoformat(),
            (START + timedelta(seconds=200)).isoformat(),
        ]

    def test_append_only_jsonl(self, tmp_path: Path) -> None:
        """Лог — append-only JSONL, по строке на сэмпл (D1)."""
        harness, log, _, _ = _run(
            tmp_path,
            statuses=["healthy"] * 10,
            interval=100.0,
            duration=200.0,
        )
        harness.run()

        raw_lines = log.path.read_text(encoding="utf-8").strip().splitlines()
        assert len(raw_lines) == 2
        assert all(line.startswith("{") and line.endswith("}") for line in raw_lines)

    def test_default_min_samples_is_duration_over_interval(
        self, tmp_path: Path
    ) -> None:
        """Пол по умолчанию = required_duration // interval (D2)."""
        harness, _, _, _ = _run(
            tmp_path,
            statuses=["healthy"] * 10,
            interval=100.0,
            duration=300.0,
        )
        verdict = harness.run()
        assert verdict.min_samples == 3
        assert verdict.verdict == PASS


class TestD2Verdict:
    def test_golden_healthy_pass(self) -> None:
        """Golden-лог healthy → PASS (Приёмка D2)."""
        samples = _mk(["healthy"] * 144, interval_s=600.0)
        verdict = evaluate_soak(
            samples,
            required_duration=86_400.0,
            interval=600.0,
            anomaly_threshold=600.0,
        )
        assert verdict.verdict == PASS
        assert verdict.sample_count == 144
        assert verdict.span_seconds == pytest.approx(86_400.0)
        assert verdict.reasons == []
        assert verdict.anomalies == []
        assert verdict.degraded_episodes == []

    def test_real_degradation_fails(self) -> None:
        """Лог с настоящей деградацией → FAIL (Приёмка D2)."""
        samples = _mk(
            ["healthy"] * 3 + ["degraded"] * 4 + ["healthy"] * 3,
            interval_s=600.0,
        )
        verdict = evaluate_soak(
            samples,
            required_duration=3_600.0,
            interval=600.0,
            anomaly_threshold=600.0,
        )
        assert verdict.verdict == FAIL
        assert any("not an artifact" in reason for reason in verdict.reasons)
        assert verdict.degraded_episodes and not verdict.anomalies

    def test_quick_artifact_passes_with_anomaly(self) -> None:
        """Быстрый артефакт → PASS с пометкой аномалии (Приёмка D2)."""
        samples = _mk(
            ["healthy"] * 3 + ["degraded"] + ["healthy"] * 6,
            interval_s=600.0,
        )
        verdict = evaluate_soak(
            samples,
            required_duration=3_600.0,
            interval=600.0,
            anomaly_threshold=600.0,
        )
        assert verdict.verdict == PASS
        assert len(verdict.anomalies) == 1
        assert verdict.anomalies[0].artifact is True

    def test_degraded_at_log_tail_is_not_artifact(self) -> None:
        """Эпизод, не восстановившийся к концу лога, — НЕ артефакт → FAIL."""
        samples = _mk(
            ["healthy"] * 5 + ["degraded"],
            interval_s=600.0,
        )
        verdict = evaluate_soak(
            samples,
            required_duration=3_600.0,
            interval=600.0,
            anomaly_threshold=600.0,
        )
        assert verdict.verdict == FAIL
        assert verdict.degraded_episodes and not verdict.anomalies

    def test_write_and_load_verdict_artifacts(self, tmp_path: Path) -> None:
        """verdict.json (машинно) + verdict.txt (человекочитаемо) (D2)."""
        verdict = evaluate_soak(
            _mk(["healthy"] * 10, interval_s=100.0),
            required_duration=600.0,
            interval=100.0,
            anomaly_threshold=600.0,
        )
        write_verdict_artifacts(verdict, out_dir=tmp_path / "soak", run_id="run1")

        loaded = load_verdict(tmp_path / "soak" / "verdict.json")
        assert loaded is not None
        assert loaded.verdict == PASS
        assert loaded.sample_count == 10
        assert loaded.min_samples == 6

        summary = (tmp_path / "soak" / "verdict.txt").read_text(encoding="utf-8")
        assert "SOAK VERDICT: PASS" in summary
        assert "run_id: run1" in summary


class TestD3ResumeAndIntegrity:
    def test_interrupt_then_resume_merges_log(self, tmp_path: Path) -> None:
        """Прерывание → рестарт: лог дописывается, вердикт по объединению (D3)."""
        clock = VirtualClock(START)
        source = InterruptingSource(status="healthy", interrupt_after=2)
        log = SoakLogFile(tmp_path / "soak" / "run.jsonl")

        def fake_sleep(delta: float) -> None:
            clock.tick(timedelta(seconds=delta))

        harness = SoakHarness(
            health_source=source,
            log=log,
            interval=100.0,
            duration=300.0,
            clock=clock,
            sleep_fn=fake_sleep,
        )
        with pytest.raises(KeyboardInterrupt):
            harness.run()
        assert len(log.read()) == 2

        # Рестарт после перерыва в 100с (сэмплирование не молчало — gap=100).
        clock2 = VirtualClock(START + timedelta(seconds=200))
        source2 = FakeHealthSource(["healthy"] * 10)

        def fake_sleep2(delta: float) -> None:
            clock2.tick(timedelta(seconds=delta))

        harness2 = SoakHarness(
            health_source=source2,
            log=log,
            interval=100.0,
            duration=300.0,
            clock=clock2,
            sleep_fn=fake_sleep2,
        )
        verdict = harness2.run()

        samples = log.read()
        assert len(samples) == 3
        assert verdict.verdict == PASS
        assert verdict.sample_count == 3

    def test_sampling_gap_fails(self, tmp_path: Path) -> None:
        """Разрыв сэмплирования > max_gap = FAIL («не молчит») (D3)."""
        samples = _mk(["healthy"] * 5, interval_s=100.0)
        # Пропуск: следующий сэмпл через 1200с после последнего — gap 700с.
        samples.append(
            HealthSample(
                ts=(START + timedelta(seconds=1_200)).isoformat(),
                overall_status="healthy",
                components={"runtime-stability": "pass"},
                classification="healthy",
            )
        )
        verdict = evaluate_soak(
            samples,
            required_duration=300.0,
            interval=100.0,
            anomaly_threshold=600.0,
            max_gap=200.0,
        )
        assert verdict.verdict == FAIL
        assert any("sampling gap" in reason for reason in verdict.reasons)


class TestResolveSoakDir:
    def test_uses_xdg_state_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Soak-артефакты рядом с audit-журналом через XDG_STATE_HOME (R2/D-45)."""
        monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-soak")
        assert resolve_soak_dir() == Path("/tmp/xdg-soak/clay/soak")

    def test_explicit_state_dir_override(self, tmp_path: Path) -> None:
        assert resolve_soak_dir(tmp_path / "state") == tmp_path / "state" / "soak"
