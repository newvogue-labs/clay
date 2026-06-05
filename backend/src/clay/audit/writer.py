"""FIX-C: thread-safe audit writer with size-based rotation.

The single shared ``AuditWriter`` instance is constructed in
``clay.bootstrap.build_services`` and written to from many
call-sites: ~9 services, scheduler jobs on the default
``ThreadPoolExecutor`` (health-tick, reliability-recheck,
ops-retention), the ingestion loop, and request handlers.
Concurrent appends to the same file from different threads can
interleave bytes and produce torn JSON lines. The previous
implementation appended under no lock and parsed on read with a
bare ``json.loads`` — so a single truncated line at the tail (from
an in-flight write, a crash, or manual inspection) would crash the
entire ``ControlCenterService`` snapshot.

This module fixes three things without changing the on-disk
format or the semantics of the JSON event:

1. ``write()`` is guarded by an in-process ``threading.Lock`` and
   runs ``_maybe_rotate()`` before each append.
2. ``read_recent()`` co-locates the JSONL parsing and is
   best-effort: malformed lines and entries missing the three
   canonical keys (``timestamp``, ``event_type``, ``payload``) are
   logged and skipped — the reader NEVER raises.
3. Rotation is size-based: when ``audit.jsonl`` exceeds
   ``max_bytes`` it is renamed to ``audit.jsonl.1`` and previous
   backups are shifted up to ``.N`` (the oldest is dropped).
   ``max_bytes <= 0`` disables rotation.

Scope notes (per FIX-C gate):

* Cross-process file locking is OUT of scope (ADR-007 single-worker
  contract — one ``uvicorn`` worker per process). The
  ``threading.Lock`` is the entire concurrency story.
* The Windows ``replace-while-open`` caveat is a known limit; the
  production target is Linux.
* ``_maybe_rotate()`` MUST be called under ``self._lock`` — the
  rename sequence is not atomic across rotations.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("clay.audit")


class AuditWriter:
    """Writes append-only audit events as JSON lines with thread-safe rotation."""

    def __init__(
        self,
        state_dir: Path,
        *,
        max_bytes: int = 5_000_000,
        backup_count: int = 5,
    ) -> None:
        self.path = state_dir / "audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._lock = threading.Lock()

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        line = json.dumps(event) + "\n"
        with self._lock:
            self._maybe_rotate()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def _maybe_rotate(self) -> None:
        """Rotate ``audit.jsonl`` if it has grown past ``max_bytes``.

        MUST be called under ``self._lock``: the cascade rename is
        not atomic across rotations.

        * ``max_bytes <= 0`` → no rotation (the file grows unbounded).
        * ``backup_count <= 0`` → the active file is deleted on
          rotation (no backups kept).
        * Otherwise: ``audit.jsonl.N`` is dropped,
          ``audit.jsonl.i`` → ``audit.jsonl.(i+1)`` for
          ``i = backup_count-1 .. 1``, and the active file becomes
          ``audit.jsonl.1``. The next ``open(..., "a")`` creates a
          fresh ``audit.jsonl``.
        """
        if self._max_bytes <= 0:
            return
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return
        if size < self._max_bytes:
            return

        if self._backup_count <= 0:
            self.path.unlink(missing_ok=True)
            return

        oldest = self.path.with_suffix(f"{self.path.suffix}.{self._backup_count}")
        oldest.unlink(missing_ok=True)
        try:
            for i in range(self._backup_count - 1, 0, -1):
                src = self.path.with_suffix(f"{self.path.suffix}.{i}")
                dst = self.path.with_suffix(f"{self.path.suffix}.{i + 1}")
                if src.exists():
                    src.replace(dst)
            self.path.replace(self.path.with_suffix(f"{self.path.suffix}.1"))
        except OSError:
            logger.warning("audit rotation failed for %s", self.path, exc_info=True)

    def read_recent(self, *, limit: int) -> list[dict[str, Any]]:
        """Read up to ``limit`` most-recent events as dicts, newest-first.

        Best-effort: malformed lines and entries missing the three
        canonical keys (``timestamp``, ``event_type``, ``payload``)
        are logged and skipped — the reader NEVER raises.

        Read intentionally does NOT take ``self._lock``. Rotation
        is an atomic ``Path.replace``; a concurrent reader holds
        its own ``fd`` and sees either the pre- or post-rotate
        file. A partial trailing line from an in-flight ``write``
        is dropped by ``json.loads`` → ``JSONDecodeError``.
        """
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                lines = deque(handle, maxlen=limit)
        except OSError:
            logger.warning("audit read failed for %s", self.path, exc_info=True)
            return []

        events: list[dict[str, Any]] = []
        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("audit: skipping malformed line in %s", self.path)
                continue
            if not isinstance(obj, dict):
                logger.warning("audit: skipping non-object line in %s", self.path)
                continue
            if not all(key in obj for key in ("timestamp", "event_type", "payload")):
                logger.warning(
                    "audit: skipping line missing canonical keys in %s", self.path
                )
                continue
            events.append(obj)
        return events
