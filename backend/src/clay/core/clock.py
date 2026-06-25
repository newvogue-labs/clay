from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class VirtualClock:
    def __init__(self, start: datetime | None = None) -> None:
        if start is not None:
            self._validate_aware(start)
            self._now = start
        else:
            self._now = datetime.now(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, ts: datetime) -> None:
        self._validate_aware(ts)
        self._now = ts

    def tick(self, delta: timedelta) -> datetime:
        if delta.total_seconds() < 0:
            raise ValueError(f"tick delta must be non-negative, got {delta}")
        self._now += delta
        return self._now

    @staticmethod
    def _validate_aware(dt: datetime) -> None:
        if dt.tzinfo is None:
            raise ValueError(f"naive datetime is not allowed in VirtualClock: {dt!r}")
