"""Tests for DegradedHeartbeat — O(1) degraded-probe via in-memory heartbeat.

Unit tests use VirtualClock for deterministic time control.
Integration test uses the production build_services factory on file-based SQLite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from clay.core.clock import VirtualClock
from clay.reliability.heartbeat import DegradedHeartbeat, DegradedHeartbeatState


# ── Unit tests ────────────────────────────────────────────────────────────────


class TestDegradedHeartbeatUnit:
    def test_cold_returns_true(self) -> None:
        """No write yet → fail-closed → True."""
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5))
        assert hb.is_degraded() is True

    def test_fresh_false_returns_false(self) -> None:
        """Fresh write(degraded=False) → False."""
        clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5), clock=clock)
        hb.write(degraded=False)
        assert hb.is_degraded() is False

    def test_fresh_true_returns_true(self) -> None:
        """Fresh write(degraded=True) → True."""
        clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5), clock=clock)
        hb.write(degraded=True)
        assert hb.is_degraded() is True

    def test_stale_returns_true_for_both_values(self) -> None:
        """After max_age → True regardless of stored value."""
        clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5), clock=clock)

        hb.write(degraded=False)
        clock.tick(timedelta(minutes=6))
        assert hb.is_degraded() is True

        hb.write(degraded=True)
        clock.tick(timedelta(minutes=6))
        assert hb.is_degraded() is True

    def test_exactly_max_age_not_stale(self) -> None:
        """Exactly max_age → not stale (<= boundary)."""
        clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5), clock=clock)
        hb.write(degraded=False)
        clock.tick(timedelta(minutes=5))
        assert hb.is_degraded() is False

    def test_max_age_plus_epsilon_stale(self) -> None:
        """max_age + 1 second → stale."""
        clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5), clock=clock)
        hb.write(degraded=False)
        clock.tick(timedelta(minutes=5, seconds=1))
        assert hb.is_degraded() is True

    def test_rewrite_after_stale_re_vivifies(self) -> None:
        """Fresh write after stale period → reflects new value."""
        clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5), clock=clock)

        hb.write(degraded=True)
        clock.tick(timedelta(minutes=6))
        assert hb.is_degraded() is True  # stale → True

        hb.write(degraded=False)
        assert hb.is_degraded() is False  # fresh → False

    def test_state_snapshot(self) -> None:
        """write() stores correct DegradedHeartbeatState."""
        clock = VirtualClock(start=datetime(2026, 1, 1, tzinfo=UTC))
        hb = DegradedHeartbeat(max_age=timedelta(minutes=5), clock=clock)
        hb.write(degraded=True)
        assert hb._state == DegradedHeartbeatState(
            degraded=True, updated_at=datetime(2026, 1, 1, tzinfo=UTC)
        )


# ── Integration test (production build_services) ─────────────────────────────


class TestDegradedHeartbeatIntegration:
    def test_bootstrap_wiring_and_o1(self, tmp_path) -> None:
        """Eager-seed + is_degraded is O(1) + recheck updates heartbeat."""
        from tests.integration._helpers import (
            build_services_for_integration,
            seed_all_areas,
        )

        services = build_services_for_integration(tmp_path)
        override_service = services["override_service"]
        reliability_service = services["reliability_service"]
        degraded_heartbeat = services["degraded_heartbeat"]
        session_factory = services["session_factory"]

        # (a) probe delegates to heartbeat (behavioral — bound methods aren't identity-comparable)
        assert override_service.is_degraded() is degraded_heartbeat.is_degraded()

        # (c) eager-seed: is_degraded gives a value consistent with snapshot
        is_deg = override_service.is_degraded()
        with session_factory() as session:
            snap = reliability_service.build_snapshot(session)
        expected = snap.summary.overall_status == "degraded"
        assert is_deg is expected

        # (b) O(1): is_degraded does NOT call build_snapshot
        build_snapshot_spy = MagicMock(wraps=reliability_service.build_snapshot)
        original_build = reliability_service.build_snapshot
        reliability_service.build_snapshot = build_snapshot_spy  # type: ignore[assignment]
        try:
            override_service.is_degraded()
            override_service.is_degraded()
            override_service.is_degraded()
            assert build_snapshot_spy.call_count == 0
        finally:
            reliability_service.build_snapshot = original_build  # type: ignore[assignment]

        # (d) recheck updates heartbeat
        with session_factory() as session:
            seed_all_areas(session)
            reliability_service.recheck(session, emit=False)
        is_deg_after = override_service.is_degraded()
        with session_factory() as session:
            snap_after = reliability_service.build_snapshot(session)
        expected_after = snap_after.summary.overall_status == "degraded"
        assert is_deg_after is expected_after
