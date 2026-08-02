"""Soak-харнесс (D-58): повторяемый 24ч soak-gate для входа в Ring 1.

Назначение: система должна проработать сама, непрерывно healthy 24ч+, без
ручного присмотра. Харнесс — стандалон CLI (НЕ вплетён в lifespan/scheduler),
который оператор запускает на хосте; он опрашивает существующий
health-агрегатор (`GET /reliability/overview`, R1), собирает health-сэмплы
append-only JSONL-логом и выдаёт машинно-проверяемый вердикт PASS/FAIL.

Границы (D-58):
- 0 торговых сетевых вызовов; единственная сетевая зависимость — локальный
  HTTP-опрос собственного health-эндпоинта на 127.0.0.1.
- live-путь (scheduler/lifespan/торговая логика) не затрагивается — модуль
  существует только как новый ops-модуль + read-only обращение к
  ReliabilityService через его HTTP-роут.
- Артефакты пишутся рядом с audit-журналом тем же каноном пути состояния
  (D-45): `<state_dir>/soak/<run-id>.jsonl`, где ``state_dir`` резолвится
  через ``build_xdg_paths`` / ``resolve_audit_journal_path``.

CI охраняет ТОЛЬКО логику харнесса (быстрые юнит-тесты + smoke). Полный 24ч
прогон — ручной веховый запуск на хосте (см. ADR-040): CI-раннеры обрываются
на ~6ч и не ходят к бирже через тоннель, поэтому автоматический 24ч job не
делается.

Вердикт (чистая функция ``evaluate_soak``): PASS только если
- лог непустой, span >= требуемой длительности, число сэмплов >= пола;
- нет разрывов сэмплирования > ``max_gap`` (дефолт 2x интервал);
- нет НЕ-артефактных degraded-эпизодов: аномалия с самовосстановлением
  < ``anomaly_threshold`` вердикт НЕ роняет, но помечается в сводке.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from clay.config.paths import build_xdg_paths
from clay.core.clock import Clock, SystemClock

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 600.0
DEFAULT_DURATION_SECONDS = 86_400.0
DEFAULT_ANOMALY_THRESHOLD_SECONDS = 600.0
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SMOKE_INTERVAL_SECONDS = 5.0
SMOKE_SAMPLE_COUNT = 5

PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class HealthSample:
    """Один health-сэмпл: ts + overall + per-component snapshot + классификация."""

    ts: str
    overall_status: str
    components: dict[str, str]
    classification: str


@dataclass(frozen=True)
class DegradedEpisode:
    """Непрерывная цепочка НЕ-healthy сэмплов.

    ``artifact=True`` — самовосстановление короче ``anomaly_threshold``
    (operator TUN-свитч и т.п.): вердикт не роняет, но помечается.
    """

    start_ts: str
    end_ts: str
    duration_seconds: float
    artifact: bool


@dataclass(frozen=True)
class SoakVerdict:
    """Машинно-читаемый вердикт soak-прогона (PASS/FAIL)."""

    verdict: str
    reasons: list[str]
    sample_count: int
    span_seconds: float
    required_duration: float
    min_samples: int
    anomalies: list[DegradedEpisode]
    degraded_episodes: list[DegradedEpisode]
    evaluated_at: str


class HealthSource(Protocol):
    """Протокол источника health-сэмплов (фейк в юнит-тестах, HTTP на проде)."""

    def sample(self, now: datetime) -> HealthSample: ...


class HttpReliabilitySource:
    """Реальный источник (R1): опрос ``GET /reliability/overview`` на localhost.

    Только read-only обращение к существующему health-агрегатору
    (``ReliabilityService.build_snapshot`` → ``ReliabilitySnapshot``).
    Сетевой доступ к бирже НЕ используется. При недоступности агрегатора
    возвращает degraded-сэмпл с причиной — харнесс не падает mid-soak, а
    «не молчит»: длинный egress/сервисный обрыв отражается как degraded-эпизод
    и валит вердикт.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def sample(self, now: datetime) -> HealthSample:
        # lazy-импорт: ядро харнесса (тесты) не зависит от httpx.
        import httpx

        url = f"{self._base_url}/reliability/overview"
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
        except Exception as exc:  # httpx.HTTPError / OSError / json-ошибки ниже
            error = f"health endpoint unreachable ({url}): {exc}"
            logger.warning("clay.ops.soak: %s", error)
            return HealthSample(
                ts=now.isoformat(),
                overall_status="degraded",
                components={"health-source": "unreachable"},
                classification="degraded",
            )
        try:
            payload: dict[str, Any] = response.json()
            if not isinstance(payload, dict):
                raise ValueError("expected a JSON object")
        except Exception as exc:  # json.JSONDecodeError / TypeError / ValueError
            error = f"health endpoint returned non-object JSON ({url}): {exc}"
            logger.warning("clay.ops.soak: %s", error)
            return HealthSample(
                ts=now.isoformat(),
                overall_status="degraded",
                components={"health-source": "malformed"},
                classification="degraded",
            )
        summary: dict[str, Any] = payload.get("summary") or {}
        overall = str(summary.get("overall_status") or "degraded")
        components: dict[str, str] = {
            str(check.get("check_id") or ""): str(check.get("status") or "fail")
            for check in (payload.get("readiness_checks") or [])
        }
        return HealthSample(
            ts=now.isoformat(),
            overall_status=overall,
            components=components,
            classification="healthy" if overall == "healthy" else "degraded",
        )


class SoakLogFile:
    """Append-only JSONL-лог сэмплов (по строке на сэмпл).

    Открывается в режиме ``append`` при каждой записи — процесс никогда не
    переписывает существующие строки (возобновляемость, D3).
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, sample: HealthSample) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(sample), sort_keys=True) + "\n")

    def read(self) -> list[HealthSample]:
        if not self.path.exists():
            return []
        samples: list[HealthSample] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    # Хвостовая битая строка после kill -9 в середине записи.
                    # Сэмпл теряется; разрыв времени всё равно виден по ts,
                    # поэтому лог не «молчит» (D3).
                    logger.warning("clay.ops.soak: skipped broken JSONL line")
                    continue
                samples.append(
                    HealthSample(
                        ts=str(data.get("ts") or ""),
                        overall_status=str(data.get("overall_status") or "degraded"),
                        components={
                            str(key): str(value)
                            for key, value in (data.get("components") or {}).items()
                        },
                        classification=str(data.get("classification") or ""),
                    )
                )
        return samples


def resolve_soak_dir(state_dir: Path | None = None) -> Path:
    """Каталог soak-артефактов рядом с audit-журналом (единый канон пути состояния).

    Канон D-45: ``state_dir`` резолвится через ``build_xdg_paths`` /
    ``resolve_audit_journal_path`` (база из ``XDG_STATE_HOME``, дефолт —
    XDG-дефолт под домашним каталогом, плюс app-name). Soak-логи живут в
    ``<state_dir>/soak/`` — путь НЕ хардкодится, резолвер один.
    """
    if state_dir is None:
        state_dir = build_xdg_paths().state_dir
    return state_dir / "soak"


def _parse_ts(ts: str) -> datetime:
    value = datetime.fromisoformat(ts)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _build_episodes(
    ordered: list[tuple[datetime, HealthSample]],
    *,
    anomaly_threshold: float,
) -> list[DegradedEpisode]:
    """Выделяет непрерывные degraded-эпизоды и классифицирует их artifact/real.

    Эпизод = максимальная цепочка подряд идущих НЕ-healthy сэмплов.
    ``artifact`` = эпизод завершился (после него есть healthy) И длительность
    < ``anomaly_threshold``. Эпизод, обрывающийся на конце лога (система не
    восстановилась к концу наблюдения) — НЕ артефакт (консервативно валит).
    """
    episodes: list[DegradedEpisode] = []
    index = 0
    count = len(ordered)
    while index < count:
        if ordered[index][1].overall_status == "healthy":
            index += 1
            continue
        start = index
        while index < count and ordered[index][1].overall_status != "healthy":
            index += 1
        end = index - 1
        start_ts = ordered[start][0]
        end_ts = ordered[end][0]
        duration_seconds = (end_ts - start_ts).total_seconds()
        resolved = (end + 1) < count
        episodes.append(
            DegradedEpisode(
                start_ts=start_ts.isoformat(),
                end_ts=end_ts.isoformat(),
                duration_seconds=duration_seconds,
                artifact=resolved and duration_seconds < anomaly_threshold,
            )
        )
    return episodes


def evaluate_soak(
    samples: list[HealthSample],
    *,
    required_duration: float,
    interval: float,
    anomaly_threshold: float,
    max_gap: float | None = None,
    min_samples: int | None = None,
    now: datetime | None = None,
) -> SoakVerdict:
    """Чистая функция вердикта: сэмплы → PASS/FAIL. Единственный путь к PASS.

    Пороги (все обязательны):
    - лог непустой (0 сэмплов = FAIL, а не пустой PASS);
    - span = (last - first) + один интервал >= ``required_duration``;
    - число сэмплов >= ``min_samples`` (пол; дефолт ``required//interval``);
    - разрыв между соседними сэмплами <= ``max_gap`` (дефолт 2x interval);
    - НЕ-артефактных degraded-эпизодов нет.

    Артефакт (самовосстановление < ``anomaly_threshold``) PASS не роняет, но
    попадает в ``anomalies`` и в человекочитаемую сводку.
    """
    evaluated_at = (now or datetime.now(UTC)).isoformat()
    if max_gap is None:
        max_gap = 2 * interval
    if min_samples is None:
        min_samples = max(1, int(required_duration / interval))

    reasons: list[str] = []

    # (2) ПУСТОЙ ВХОД: 0 сэмплов или span < требуемого → FAIL, не пустой PASS.
    if not samples:
        return SoakVerdict(
            verdict=FAIL,
            reasons=["no samples recorded"],
            sample_count=0,
            span_seconds=0.0,
            required_duration=required_duration,
            min_samples=min_samples,
            anomalies=[],
            degraded_episodes=[],
            evaluated_at=evaluated_at,
        )

    try:
        ordered = sorted(
            ((_parse_ts(sample.ts), sample) for sample in samples),
            key=lambda pair: pair[0],
        )
    except ValueError:
        return _fail_verdict(
            reasons=["invalid sample timestamp in log"],
            evaluated_at=evaluated_at,
            required_duration=required_duration,
            min_samples=min_samples,
        )

    span_seconds = (ordered[-1][0] - ordered[0][0]).total_seconds() + interval
    if span_seconds < required_duration:
        reasons.append(f"span {span_seconds:.1f}s < required {required_duration:.1f}s")

    if len(ordered) < min_samples:
        reasons.append(f"only {len(ordered)} samples < min {min_samples}")

    # (D3) Разрыв сэмплирования > max_gap = провал («не молчит»).
    for previous, current in zip(ordered, ordered[1:], strict=False):
        gap = (current[0] - previous[0]).total_seconds()
        if gap > max_gap:
            reasons.append(
                f"sampling gap {gap:.1f}s > max_gap {max_gap:.1f}s "
                f"({previous[0].isoformat()} -> {current[0].isoformat()})"
            )

    episodes = _build_episodes(ordered, anomaly_threshold=anomaly_threshold)
    real_episodes = [episode for episode in episodes if not episode.artifact]
    anomalies = [episode for episode in episodes if episode.artifact]
    for episode in real_episodes:
        reasons.append(
            f"degraded episode {episode.start_ts}->{episode.end_ts} "
            f"({episode.duration_seconds:.1f}s) not an artifact"
        )

    verdict = PASS if not reasons else FAIL
    return SoakVerdict(
        verdict=verdict,
        reasons=reasons,
        sample_count=len(ordered),
        span_seconds=span_seconds,
        required_duration=required_duration,
        min_samples=min_samples,
        anomalies=anomalies,
        degraded_episodes=episodes,
        evaluated_at=evaluated_at,
    )


def _fail_verdict(
    *,
    reasons: list[str],
    evaluated_at: str,
    required_duration: float,
    min_samples: int,
) -> SoakVerdict:
    return SoakVerdict(
        verdict=FAIL,
        reasons=reasons,
        sample_count=0,
        span_seconds=0.0,
        required_duration=required_duration,
        min_samples=min_samples,
        anomalies=[],
        degraded_episodes=[],
        evaluated_at=evaluated_at,
    )


def load_verdict(path: Path) -> SoakVerdict | None:
    """Читает вердикт из verdict.json; битый/отсутствующий файл → None.

    Охранник (3): битый/отсутствующий артефакт НИКОГДА не равен PASS —
    вердикт производится только оценкой сэмплов (``evaluate_soak``).
    """
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return SoakVerdict(
            verdict=str(data["verdict"]),
            reasons=[str(reason) for reason in data.get("reasons", [])],
            sample_count=int(data["sample_count"]),
            span_seconds=float(data["span_seconds"]),
            required_duration=float(data["required_duration"]),
            min_samples=int(data["min_samples"]),
            anomalies=[
                DegradedEpisode(
                    start_ts=str(episode["start_ts"]),
                    end_ts=str(episode["end_ts"]),
                    duration_seconds=float(episode["duration_seconds"]),
                    artifact=bool(episode["artifact"]),
                )
                for episode in data.get("anomalies", [])
            ],
            degraded_episodes=[
                DegradedEpisode(
                    start_ts=str(episode["start_ts"]),
                    end_ts=str(episode["end_ts"]),
                    duration_seconds=float(episode["duration_seconds"]),
                    artifact=bool(episode["artifact"]),
                )
                for episode in data.get("degraded_episodes", [])
            ],
            evaluated_at=str(data["evaluated_at"]),
        )
    except KeyError, TypeError, ValueError, OSError, json.JSONDecodeError:
        return None


def _format_summary(verdict: SoakVerdict, run_id: str) -> str:
    lines = [
        f"SOAK VERDICT: {verdict.verdict}",
        f"run_id: {run_id}",
        f"samples: {verdict.sample_count} (min {verdict.min_samples})",
        f"span: {verdict.span_seconds:.1f}s (required {verdict.required_duration:.1f}s)",
        f"evaluated_at: {verdict.evaluated_at}",
    ]
    if verdict.reasons:
        lines.append("reasons:")
        lines.extend(f"  - {reason}" for reason in verdict.reasons)
    if verdict.anomalies:
        lines.append("anomalies (artifact, PASS not dropped):")
        for episode in verdict.anomalies:
            lines.append(
                f"  - {episode.start_ts} -> {episode.end_ts} "
                f"({episode.duration_seconds:.1f}s)"
            )
    if verdict.degraded_episodes:
        lines.append("degraded episodes:")
        for episode in verdict.degraded_episodes:
            marker = "artifact" if episode.artifact else "REAL"
            lines.append(
                f"  - {episode.start_ts} -> {episode.end_ts} "
                f"({episode.duration_seconds:.1f}s, {marker})"
            )
    return "\n".join(lines) + "\n"


def write_verdict_artifacts(
    verdict: SoakVerdict,
    *,
    out_dir: Path,
    run_id: str,
) -> None:
    """Пишет машинно-читаемый verdict.json + человекочитаемую сводку (D2)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "verdict.json").write_text(
        json.dumps(asdict(verdict), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "verdict.txt").write_text(
        _format_summary(verdict, run_id),
        encoding="utf-8",
    )


class SoakHarness:
    """Сэмплер: опрашивает health-источник каждый ``interval`` в течение ``duration``.

    Стандалон, НЕ вплетён в lifespan/scheduler. Возобновляемость (D3):
    при старте читает существующий лог и продолжает до первой метки + duration;
    вердикт считается по объединению существующих и новых сэмплов.

    ``clock`` и ``sleep_fn`` инъектируемы (фейковые часы в юнит-тестах;
    live — ``SystemClock`` + ``time.sleep``).
    """

    def __init__(
        self,
        *,
        health_source: HealthSource,
        log: SoakLogFile,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        duration: float = DEFAULT_DURATION_SECONDS,
        anomaly_threshold: float = DEFAULT_ANOMALY_THRESHOLD_SECONDS,
        max_gap: float | None = None,
        min_samples: int | None = None,
        clock: Clock | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._health_source = health_source
        self._log = log
        self._interval = interval
        self._duration = duration
        self._anomaly_threshold = anomaly_threshold
        self._max_gap = max_gap
        self._min_samples = min_samples
        self._clock: Clock = clock or SystemClock()
        self._sleep: Callable[[float], None] = sleep_fn or time.sleep

    def run(self) -> SoakVerdict:
        start = self._clock.now()
        existing = self._log.read()
        if existing:
            end = _parse_ts(existing[0].ts) + timedelta(seconds=self._duration)
        else:
            end = start + timedelta(seconds=self._duration)
        while self._clock.now() < end:
            sample = self._health_source.sample(self._clock.now())
            self._log.append(sample)
            self._sleep(self._interval)
        return evaluate_soak(
            self._log.read(),
            required_duration=self._duration,
            interval=self._interval,
            anomaly_threshold=self._anomaly_threshold,
            max_gap=self._max_gap,
            min_samples=self._min_samples,
        )


def _positive_float(value: str, name: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be > 0, got {value!r}")
    return parsed


def _optional_positive_float(value: str, name: str) -> float | None:
    if value == "" or value is None:
        return None
    parsed = _positive_float(value, name)
    return parsed


def _run_id_now() -> str:
    return time.strftime("soak-%Y%m%d-%H%M%S")


def main(argv: list[str] | None = None) -> int:
    """CLI-энтрипоинт: ``python -m clay.ops.soak_harness``.

    Коды возврата: 0 = PASS, 1 = FAIL, 2 = usage/runtime-ошибка.
    """
    parser = argparse.ArgumentParser(
        description="Soak harness for Clay Ring-1 24h gate (D-58)"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SOAK_BASE_URL", DEFAULT_BASE_URL),
        help="Local Clay API base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--interval",
        default=os.environ.get("SOAK_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS),
        help="Sampling interval in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--duration",
        default=os.environ.get("SOAK_DURATION_SECONDS", DEFAULT_DURATION_SECONDS),
        help="Total soak duration in seconds (default: %(default)s = 24h)",
    )
    parser.add_argument(
        "--anomaly-threshold",
        default=os.environ.get(
            "SOAK_ANOMALY_THRESHOLD_SECONDS", DEFAULT_ANOMALY_THRESHOLD_SECONDS
        ),
        help="Artifact self-recovery threshold in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--max-gap",
        default=os.environ.get("SOAK_MAX_GAP_SECONDS", ""),
        help="Max sampling gap in seconds, default 2x interval",
    )
    parser.add_argument(
        "--min-samples",
        default=os.environ.get("SOAK_MIN_SAMPLES", ""),
        help="Min sample count floor, default duration/interval",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run id (default: soak-<timestamp>); log = <state_dir>/soak/<run-id>.jsonl",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Override state dir (default: XDG_STATE_HOME/clay or XDG default under HOME)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Smoke mode: ~5 samples over ~25s (CI e2e launch check)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        interval = _positive_float(str(args.interval), "--interval")
        duration = _positive_float(str(args.duration), "--duration")
        anomaly_threshold = _positive_float(
            str(args.anomaly_threshold), "--anomaly-threshold"
        )
        max_gap = _optional_positive_float(str(args.max_gap), "--max-gap")
        min_samples_raw = str(args.min_samples).strip()
        min_samples = int(min_samples_raw) if min_samples_raw else None
        if min_samples is not None and min_samples < 1:
            raise ValueError("--min-samples must be >= 1")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.smoke:
        interval = SMOKE_INTERVAL_SECONDS
        duration = SMOKE_INTERVAL_SECONDS * SMOKE_SAMPLE_COUNT

    run_id = args.run_id or _run_id_now()
    soak_dir = resolve_soak_dir(args.state_dir)
    log_path = soak_dir / f"{run_id}.jsonl"
    harness = SoakHarness(
        health_source=HttpReliabilitySource(base_url=args.base_url),
        log=SoakLogFile(log_path),
        interval=interval,
        duration=duration,
        anomaly_threshold=anomaly_threshold,
        max_gap=max_gap,
        min_samples=min_samples,
    )

    logger.info(
        "clay.ops.soak: start run_id=%s base_url=%s interval=%.0fs "
        "duration=%.0fs log=%s",
        run_id,
        args.base_url,
        interval,
        duration,
        log_path,
    )

    try:
        verdict = harness.run()
    except KeyboardInterrupt:
        logger.info("clay.ops.soak: interrupted; verdict over partial log")
        verdict = evaluate_soak(
            SoakLogFile(log_path).read(),
            required_duration=duration,
            interval=interval,
            anomaly_threshold=anomaly_threshold,
            max_gap=max_gap,
            min_samples=min_samples,
        )

    write_verdict_artifacts(verdict, out_dir=soak_dir, run_id=run_id)
    print(_format_summary(verdict, run_id), end="")
    logger.info(
        "clay.ops.soak: done verdict=%s artifacts=%s %s",
        verdict.verdict,
        soak_dir / "verdict.json",
        soak_dir / "verdict.txt",
    )
    return 0 if verdict.verdict == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
