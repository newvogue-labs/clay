"""Finding C: thread-safe writes + corruption-tolerant reads + size-based
rotation for ``AuditWriter`` (hardening #3).

Five test buckets:

1. **Concurrency** — 8 threads × 200 writes to a single shared writer
   must produce exactly 1600 well-formed JSON lines (proves the lock
   prevents byte-level interleaving).
2. **Read resilience** — manually injecting one malformed JSON line
   and one JSON line missing the ``payload`` key must not raise
   inside ``read_recent``; the four well-formed events are returned
   newest-first.
3. **Rotation** — under ``max_bytes=1000``, ``backup_count=2``,
   writing past three rotation thresholds leaves ``audit.jsonl``,
   ``audit.jsonl.1`` and ``audit.jsonl.2`` on disk; ``.3`` must NOT
   exist (oldest is dropped at the cap).
4. **Rotation disabled** — ``max_bytes=0`` never creates a ``.1``
   regardless of total bytes written.
5. **Settings** — ``AuditSettings()`` defaults (5_000_000 / 5) and
   ``CLAY_AUDIT_MAX_BYTES`` / ``CLAY_AUDIT_BACKUP_COUNT`` env
   overrides both take effect.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator

import pytest

from clay.audit.writer import AuditWriter
from clay.settings.audit import AuditSettings


# =========================================================================
#  1) Concurrency: 8 threads × 200 writes — no torn lines
# =========================================================================


def test_concurrent_writes_produce_intact_lines(tmp_path) -> None:
    writer = AuditWriter(tmp_path, max_bytes=0)
    threads = 8
    per_thread = 200

    errors: list[BaseException] = []

    def worker(thread_idx: int) -> None:
        try:
            for i in range(per_thread):
                writer.write(
                    "concurrency.test",
                    {"thread": thread_idx, "i": i},
                )
        except BaseException as exc:  # pragma: no cover - diagnostic only
            errors.append(exc)

    workers = [threading.Thread(target=worker, args=(idx,)) for idx in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()

    assert errors == []

    raw = writer.path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.split("\n") if ln]
    assert len(lines) == threads * per_thread, (
        f"expected {threads * per_thread} lines, got {len(lines)}"
    )

    for ln in lines:
        obj = json.loads(ln)
        assert set(obj.keys()) == {"timestamp", "event_type", "payload"}
        assert obj["event_type"] == "concurrency.test"


# =========================================================================
#  2) Read resilience: malformed + missing-key lines are skipped
# =========================================================================


def test_read_recent_skips_malformed_and_incomplete_lines(tmp_path) -> None:
    writer = AuditWriter(tmp_path, max_bytes=0)

    for i in range(3):
        writer.write("good.event", {"seq": i})

    with writer.path.open("a", encoding="utf-8") as handle:
        handle.write("{ broken json\n")
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-06-04T00:00:00+00:00",
                    "event_type": "missing.payload",
                }
            )
            + "\n"
        )

    writer.write("good.event", {"seq": 3})

    events = writer.read_recent(limit=12)

    assert len(events) == 4
    assert [ev["payload"]["seq"] for ev in events] == [3, 2, 1, 0]
    assert all(ev["event_type"] == "good.event" for ev in events)
    assert all(
        set(ev.keys()) == {"timestamp", "event_type", "payload"} for ev in events
    )


# =========================================================================
#  3) Rotation: cap honoured, oldest dropped
# =========================================================================


def test_rotation_caps_backup_count(tmp_path) -> None:
    writer = AuditWriter(tmp_path, max_bytes=1000, backup_count=2)

    padding = {"padding": "x" * 20}
    for i in range(50):
        writer.write("rotation.test", {"seq": i, **padding})

    assert writer.path.exists()
    assert writer.path.stat().st_size < 1000

    for backup_idx in (1, 2):
        backup = tmp_path / f"audit.jsonl.{backup_idx}"
        assert backup.exists(), f"expected audit.jsonl.{backup_idx} to exist"

    overflow = tmp_path / "audit.jsonl.3"
    assert not overflow.exists(), "audit.jsonl.3 must not exist (oldest dropped)"


# =========================================================================
#  4) Rotation disabled: max_bytes <= 0 keeps a single file
# =========================================================================


def test_rotation_disabled_when_max_bytes_zero(tmp_path) -> None:
    writer = AuditWriter(tmp_path, max_bytes=0, backup_count=2)

    for i in range(200):
        writer.write("norotate.test", {"seq": i, "padding": "y" * 20})

    assert writer.path.exists()
    assert writer.path.stat().st_size > 1000

    for backup_idx in (1, 2, 3):
        backup = tmp_path / f"audit.jsonl.{backup_idx}"
        assert not backup.exists(), f"audit.jsonl.{backup_idx} must not be created"


# =========================================================================
#  5) Settings: defaults + env overrides
# =========================================================================


@pytest.fixture
def clean_audit_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in ("CLAY_AUDIT_MAX_BYTES", "CLAY_AUDIT_BACKUP_COUNT"):
        monkeypatch.delenv(key, raising=False)
    yield


def test_audit_settings_defaults(clean_audit_env) -> None:
    settings = AuditSettings()
    assert settings.max_bytes == 5_000_000
    assert settings.backup_count == 5


def test_audit_settings_env_overrides(
    clean_audit_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAY_AUDIT_MAX_BYTES", "1234")
    monkeypatch.setenv("CLAY_AUDIT_BACKUP_COUNT", "2")

    settings = AuditSettings()
    assert settings.max_bytes == 1234
    assert settings.backup_count == 2
