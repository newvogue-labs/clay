"""Tests for scheduler prompt constants (lightweight, no side-effect imports)."""

from clay.scheduler.prompts import CHIEF_AGENT_SYSTEM_PROMPT


class TestChiefAgentPrompt:
    def test_provenance_citation(self) -> None:
        assert "[kn-" in CHIEF_AGENT_SYSTEM_PROMPT

    def test_advisory_role(self) -> None:
        low = CHIEF_AGENT_SYSTEM_PROMPT.lower()
        assert "совет" in low

    def test_no_trade_commands(self) -> None:
        low = CHIEF_AGENT_SYSTEM_PROMPT.lower()
        assert "не отдаёшь" in low

    def test_russian_language(self) -> None:
        assert "советник-аналитик" in CHIEF_AGENT_SYSTEM_PROMPT
