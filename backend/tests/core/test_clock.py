"""Tests for clay.core.clock — Clock protocol, SystemClock, VirtualClock."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from clay.core.clock import SystemClock, VirtualClock


class TestSystemClock:
    def test_now_returns_utc_aware(self) -> None:
        t = SystemClock().now()
        assert t.tzinfo is UTC

    def test_now_reasonable_delta(self) -> None:
        t0 = datetime.now(UTC)
        t1 = SystemClock().now()
        delta = abs((t1 - t0).total_seconds())
        assert delta < 5.0, f"SystemClock.now() differed by {delta}s"


REF_TS = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)


class TestVirtualClock:
    def test_default_init_uses_utc_aware_now(self) -> None:
        t0 = datetime.now(UTC)
        vc = VirtualClock()
        t1 = vc.now()
        assert t1.tzinfo is UTC
        delta = abs((t1 - t0).total_seconds())
        assert delta < 5.0, f"VirtualClock() default now differed by {delta}s"

    def test_init_with_explicit_start(self) -> None:
        vc = VirtualClock(start=REF_TS)
        assert vc.now() == REF_TS

    def test_init_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="naive datetime"):
            VirtualClock(start=datetime(2026, 6, 25, 12, 0, 0))

    def test_now_idempotent_without_tick(self) -> None:
        vc = VirtualClock(start=REF_TS)
        assert vc.now() is vc.now()
        assert vc.now() == REF_TS

    def test_tick_forward(self) -> None:
        vc = VirtualClock(start=REF_TS)
        result = vc.tick(timedelta(hours=1))
        assert result == datetime(2026, 6, 25, 13, 0, 0, tzinfo=UTC)
        assert vc.now() == result

    def test_multiple_ticks_accumulate(self) -> None:
        vc = VirtualClock(start=REF_TS)
        vc.tick(timedelta(minutes=30))
        vc.tick(timedelta(seconds=90))
        expected = REF_TS + timedelta(minutes=31, seconds=30)
        assert vc.now() == expected

    def test_tick_zero_delta_is_noop(self) -> None:
        vc = VirtualClock(start=REF_TS)
        vc.tick(timedelta())
        assert vc.now() == REF_TS

    def test_negative_tick_raises(self) -> None:
        vc = VirtualClock(start=REF_TS)
        with pytest.raises(ValueError, match="tick delta must be non-negative"):
            vc.tick(timedelta(seconds=-1))

    def test_set_fixes_time(self) -> None:
        vc = VirtualClock(start=REF_TS)
        new_ts = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
        vc.set(new_ts)
        assert vc.now() == new_ts

    def test_set_rejects_naive_datetime(self) -> None:
        vc = VirtualClock(start=REF_TS)
        with pytest.raises(ValueError, match="naive datetime"):
            vc.set(datetime(2026, 6, 25, 12, 0, 0))

    def test_set_after_tick_overwrites(self) -> None:
        vc = VirtualClock(start=REF_TS)
        vc.tick(timedelta(days=1))
        earlier = datetime(2026, 6, 25, 0, 0, 0, tzinfo=UTC)
        vc.set(earlier)
        assert vc.now() == earlier
