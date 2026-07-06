"""Tests for S3b-i #knowledge advisory retrieval (dark-launch).

Coverage (8+ cases — D9 matrix):

1. present:   retrieval returns cards, deduped, ranked.
2. empty:     search returns [] → [].
3. failure:   search raises → fail-open [].
4. dedup+cap: dedup by item_id, ≤10, token-cap.
5. mode=off:  search NOT called (full no-op).
6. service=None: no-op, no crash.
7. boost:     strategy_rule ranked above note at same score.
8. terms:     alias expansion + ticker extraction.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from clay.knowledge.models import KnowledgeSearchResultSnapshot
from clay.scheduler.ai_agent_job import (
    AIAgentCycleJob,
    _extract_terms,
    _log_would_inject,
    _merge_dedup_boost,
)


def _card(
    item_id: int,
    category: str = "note",
    priority: str = "medium",
    score: float = 0.5,
    chunk: str = "x",
) -> KnowledgeSearchResultSnapshot:
    return KnowledgeSearchResultSnapshot(
        item_id=item_id,
        title=f"t{item_id}",
        category=category,
        priority=priority,
        tags=[],
        score=score,
        matched_chunk=chunk,
        rationale="r",
    )


def _job(*, ks: Any = None, mode: str = "off") -> AIAgentCycleJob:
    return AIAgentCycleJob(
        runner=MagicMock(),
        session_factory=MagicMock(),
        role_ids=["chief-agent"],
        ai_control_service=MagicMock(),
        knowledge_service=ks,
        knowledge_mode=mode,
    )


# ===================================================================
# TESTS
# ===================================================================


class TestRetrieveAdvisoryCards:
    def test_present_returns_cards(self) -> None:
        ks = MagicMock()
        ks.search.side_effect = [[_card(1, "strategy_rule", score=0.4)], [], []]
        out = _job(ks=ks, mode="darklaunch")._retrieve_advisory_cards(
            MagicMock(), "BTC-USDT"
        )
        assert [c.item_id for c in out] == [1]

    def test_empty(self) -> None:
        ks = MagicMock()
        ks.search.return_value = []
        out = _job(ks=ks, mode="darklaunch")._retrieve_advisory_cards(MagicMock(), "")
        assert out == []

    def test_failure_degrade(self) -> None:
        ks = MagicMock()
        ks.search.side_effect = RuntimeError("boom")
        out = _job(ks=ks, mode="darklaunch")._retrieve_advisory_cards(MagicMock(), "x")
        assert out == []

    def test_mode_off_noop(self) -> None:
        ks = MagicMock()
        _job(ks=ks, mode="off")._maybe_darklaunch_knowledge(MagicMock(), "BTC")
        ks.search.assert_not_called()

    def test_service_none_noop(self) -> None:
        _job(ks=None, mode="darklaunch")._maybe_darklaunch_knowledge(MagicMock(), "BTC")


class TestMergeDedupBoost:
    def test_dedup_and_cap(self) -> None:
        cards = [_card(i % 3, score=i / 20) for i in range(15)]
        out = _merge_dedup_boost(cards)
        assert len(out) == 3
        assert len({c.item_id for c in out}) == 3

    def test_category_boost_ordering(self) -> None:
        out = _merge_dedup_boost(
            [
                _card(1, "note", score=0.5),
                _card(2, "strategy_rule", score=0.5),
            ]
        )
        assert out[0].item_id == 2

    def test_token_cap(self) -> None:
        cards = [_card(i, chunk="a" * 1500) for i in range(3)]
        out = _merge_dedup_boost(cards)
        assert len(out) == 1


class TestExtractTerms:
    def test_alias_and_ticker(self) -> None:
        terms = _extract_terms("сигнал по BTC-USDT, режем OI и ставим SL")
        assert "BTC-USDT" in terms
        assert "open-interest" in terms
        assert "stop-loss" in terms

    def test_max_terms(self) -> None:
        terms = _extract_terms("A B C D E F G H")
        assert len(terms) <= 5


class TestLogWouldInject:
    def test_logs_zero_cards(self) -> None:
        with patch("clay.scheduler.ai_agent_job.logger.info") as mock_info:
            _log_would_inject([], query_terms=["BTC"])
            mock_info.assert_called_once_with(
                "clay.knowledge.darklaunch: 0 cards (terms=%s)",
                ["BTC"],
            )

    def test_logs_cards(self) -> None:
        card = _card(1, "strategy_rule", "high", 0.9, "risk content")
        with patch("clay.scheduler.ai_agent_job.logger.info") as mock_info:
            _log_would_inject([card], query_terms=["risk"])
            mock_info.assert_called_once()
            _, kwargs = mock_info.call_args
            assert any("kn-1" in str(a) for a in mock_info.call_args.args)
