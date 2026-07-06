"""Tests for S3b-chief-B: ranked signals in chief-agent context.

Coverage (6 cases):

1. signals_section:      sorted and capped at 10.
2. signals_empty:        empty list → "".
3. signals_few:          less than 10 not padded.
4. signals_safe_none:    service=None → "".
5. signals_safe_fail:    build_snapshot raises → "".
6. kelly_none:           kelly_fraction=None → "N/A".
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from clay.scheduler.ai_agent_job import (
    AIAgentCycleJob,
    _render_signals_section,
)


def _sig(
    symbol: str = "BTC",
    direction: str = "long",
    rank: float = 0.5,
    conf: float = 0.6,
    kelly: float | None = 0.1,
) -> MagicMock:
    s = MagicMock()
    s.symbol = symbol
    s.direction = direction
    s.ranking_score = rank
    s.confidence = conf
    s.kelly_fraction = kelly
    return s


def _snap(signals: list | None = None) -> MagicMock:
    s = MagicMock()
    s.signals = signals or []
    return s


def _job(*, svc: Any = None) -> AIAgentCycleJob:
    j = AIAgentCycleJob(
        runner=MagicMock(),
        session_factory=MagicMock(),
        role_ids=["chief-agent"],
        ai_control_service=MagicMock(),
    )
    j._signal_engine_service = svc
    return j


# ===================================================================
# TESTS: _render_signals_section (pure)
# ===================================================================


class TestRenderSignalsSection:
    def test_signals_sorted_and_capped(self) -> None:
        snap = _snap([_sig(f"S{i}", rank=i / 20) for i in range(15)])
        out = _render_signals_section(snap)
        assert out.startswith("=== signals ===")
        assert out.count("\n- ") == 10
        # лучший rank первым
        lines = out.splitlines()
        rank_line = next(line for line in lines if line.startswith("- S14"))
        assert "rank=0.700" in rank_line

    def test_signals_empty(self) -> None:
        assert _render_signals_section(_snap([])) == ""

    def test_signals_few(self) -> None:
        snap = _snap([_sig("BTC", rank=0.9), _sig("ETH", rank=0.8)])
        out = _render_signals_section(snap)
        assert out.count("\n- ") == 2

    def test_kelly_none(self) -> None:
        snap = _snap([_sig("BTC", kelly=None)])
        out = _render_signals_section(snap)
        assert "kelly=N/A" in out


# ===================================================================
# TESTS: _render_signals_safe (fail-open)
# ===================================================================


class TestRenderSignalsSafe:
    def test_safe_none(self) -> None:
        assert _job(svc=None)._render_signals_safe(MagicMock()) == ""

    def test_safe_failopen(self) -> None:
        svc = MagicMock()
        svc.build_snapshot.side_effect = RuntimeError("boom")
        assert _job(svc=svc)._render_signals_safe(MagicMock()) == ""
