"""In-memory degraded-heartbeat for O(1) degraded-probe reads.

Replaces the per-call ``build_snapshot`` probe on
``OverrideService.is_degraded()`` / kill-switch execution gate.
The heartbeat is written by ``ReliabilityService.recheck`` on its
cadence (B4 scheduler job) plus one eager-seed at bootstrap.

Fail-closed: cold (never written) and stale (writer too slow) both
read as ``degraded=True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from clay.core.clock import Clock, SystemClock


@dataclass(frozen=True)
class DegradedHeartbeatState:
    """Snapshot of the last ``DegradedHeartbeat.write`` call."""

    degraded: bool
    updated_at: datetime


class DegradedHeartbeat:
    """O(1) degraded-probe backed by an in-memory heartbeat.

    The holder owns a single clock for both writes and reads so that
    staleness comparison is monotonic.

    Typical ``max_age``: ``2 × reliability_recheck_interval_seconds``
    (allows one missed cadence before fail-closed).
    """

    def __init__(self, *, max_age: timedelta, clock: Clock = SystemClock()) -> None:
        self._max_age = max_age
        self._clock = clock
        self._state: DegradedHeartbeatState | None = None

    def write(self, *, degraded: bool) -> None:
        """Record the latest degraded evaluation with a timestamp."""
        self._state = DegradedHeartbeatState(
            degraded=degraded,
            updated_at=self._clock.now(),
        )

    def is_degraded(self) -> bool:
        """Return current degraded status — fail-closed on cold / stale.

        - ``None`` (never written) → ``True``
        - ``now - updated_at > max_age`` (stale) → ``True``
        - Otherwise → stored ``degraded`` value
        """
        if self._state is None:
            return True
        now = self._clock.now()
        if (now - self._state.updated_at) > self._max_age:
            return True
        return self._state.degraded
