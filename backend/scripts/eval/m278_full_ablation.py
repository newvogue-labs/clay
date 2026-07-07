"""M278 full ablation: 3 scenarios × off/inject × LLM + M278 scan.

Run:
    cd backend && CLAY_DATABASE_URL=... uv run python scripts/eval/m278_full_ablation.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from clay.scheduler.commands import CommandDetector

_OUTPUT_DIR = Path("/tmp/m278_ablation_2026-07-06")
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===================================================================
# 3 scenario contexts (rendered вручную — различаются signals + summary)
# ===================================================================

_BASE_CTX = """=== summary ===
overall_status=healthy chief_agent_model=gemma-4-31b-it active_conflict_count=0 degraded_role_count=0 fallback_active=False last_reviewed_at={ts}

=== roles ===
  chief-agent: Chief Agent — Final synthesis, operator-facing summary, and final conflict resolution.
  market-scanner: Market Scanner — Scan market structure and shortlist tradable candidates.
  news-sentiment-agent: News/Sentiment Agent — Transform context feeds into operator-readable pressure and narrative.
  forecast-model: Forecast Model — Produce directional forecast hints for ranking and review.

=== models ===
  minimax-m3: MiniMax-M3 (TokenRouter/cloud)
  gemma-4-31b-it: Gemma 4 31B IT (Google AI Studio/cloud)
  forecast-lite-v1: Forecast Lite v1 (Local/local)

=== assignments ===
  chief-agent → gemma-4-31b-it [mode=active health=healthy]
  market-scanner → gemma-4-31b-it [mode=active health=healthy]
  news-sentiment-agent → gemma-4-31b-it [mode=active health=healthy]
  forecast-model → forecast-lite-v1 [mode=active health=healthy]

=== conflicts ===
  none

=== fallback ===
fallback_active=False local_fallback_ready=True degraded_roles=none operator_message=Fallback posture is prepared and currently inactive.

=== pending_review ===
  none"""

SCENARIOS: dict[str, str] = {
    "quiet": _BASE_CTX.format(ts="2026-07-06T10:00:00+00:00")
    + """

=== signals ===
Ranked signals из signal_engine (backend = источник истины; только для справки):
- BTCUSDT bullish | rank=0.010 conf=0.05 kelly=0.000
- ETHUSDT bullish | rank=0.001 conf=0.04 kelly=0.000
- SOLUSDT bearish | rank=0.000 conf=0.03 kelly=0.000

=== subagent_reports ===
  [market-scanner] (5 min ago):
    All symbols show low volume and narrow ranges. No directional setup detected.
  [news-sentiment-agent] (4 min ago):
    Neutral sentiment. No significant news events in the last hour.
  [forecast-model] (3 min ago):
    All forecasts near baseline. No conviction edge above noise threshold.""",
    "strong": _BASE_CTX.format(ts="2026-07-06T14:30:00+00:00")
    + """

=== signals ===
Ranked signals из signal_engine (backend = источник истины; только для справки):
- SOLUSDT bullish | rank=0.720 conf=0.62 kelly=0.035
- BTCUSDT bullish | rank=0.510 conf=0.55 kelly=0.012
- ETHUSDT neutral | rank=0.080 conf=0.20 kelly=0.000

=== subagent_reports ===
  [market-scanner] (2 min ago):
    SOLUSDT: breakout above resistance with above-average volume. MTF confluence bullish.
    BTCUSDT: holding support, trending upward on 1H.
  [news-sentiment-agent] (1 min ago):
    Positive sentiment around SOL ecosystem developments. BTC institutional inflow叙事.
  [forecast-model] (2 min ago):
    SOL directional probability elevated to 0.65. BTC moderate confidence 0.55.""",
    "mixed": _BASE_CTX.format(ts="2026-07-06T18:00:00+00:00")
    + """

=== signals ===
Ranked signals из signal_engine (backend = источник истины; только для справки):
- SOLUSDT bullish | rank=0.490 conf=0.41 kelly=0.000
- BTCUSDT bullish | rank=0.100 conf=0.20 kelly=0.000
- ETHUSDT bearish | rank=0.080 conf=0.05 kelly=0.000

=== subagent_reports ===
  [market-scanner] (8 min ago):
    Mixed signals across timeframe. SOL showing short-term momentum but conflicting on 4H.
  [news-sentiment-agent] (6 min ago):
    Mixed sentiment. Some positive crypto headlines balanced by macro uncertainty.
  [forecast-model] (7 min ago):
    No clear edge on any symbol. SOL short-term only with low conviction.""",
}


def _make_runner() -> "AgentRunner":  # noqa: F821
    """Build cloud runner for minimax-m3 через LiteLLM.

    Falls back to local only if LiteLLM is unreachable.
    """
    from clay.ai_control.runner import (
        AgentRunner,
        LiteLLMModelClient,
        OllamaNativeClient,
        RoutingModelClient,
    )
    from clay.bootstrap import ai_control_service
    from clay.llm import LLMAdapter
    from clay.scheduler.prompts import CHIEF_AGENT_SYSTEM_PROMPT
    from clay.settings.llm import LLMSettings
    from clay.settings.ollama import OllamaSettings

    class _EvalResolver:
        def resolve_model_id(self, role_id: str) -> str:
            return "minimax-m3"

    ollama = OllamaNativeClient.from_settings(OllamaSettings())
    llm = LiteLLMModelClient(adapter=LLMAdapter(LLMSettings()))
    router = RoutingModelClient(
        local_client=ollama,
        cloud_client=llm,
        transport_lookup=ai_control_service.transport_for,
    )
    return AgentRunner(
        model_resolver=_EvalResolver(),
        model_client=router,
        role_prompts={"chief-agent": CHIEF_AGENT_SYSTEM_PROMPT},
    )


def _build_inject_context(base_ctx: str) -> str:
    """Build inject context: retrieve cards + append advisory section."""
    from unittest.mock import MagicMock
    from clay.bootstrap import knowledge_service, session_factory
    from clay.scheduler.ai_agent_job import AIAgentCycleJob

    dummy = AIAgentCycleJob(
        runner=MagicMock(),
        session_factory=session_factory,
        role_ids=["chief-agent"],
        ai_control_service=MagicMock(),
        knowledge_service=knowledge_service,
        knowledge_mode="inject",
        signal_engine_service=None,
    )
    with session_factory() as s:
        return dummy._maybe_apply_knowledge(s, base_ctx)


async def _run() -> None:
    runner = _make_runner()

    for sname in ["quiet", "strong", "mixed"]:
        ctx = SCENARIOS[sname]
        ctx_inject = _build_inject_context(ctx)
        print(f"\n{'=' * 60}")
        print(f"  SCENARIO: {sname}")
        print(f"{'=' * 60}")

        for mode, text in [("off", ctx), ("inject", ctx_inject)]:
            print(f"\n  --- {mode.upper()} --- calling LLM ...", flush=True)
            result = await runner.run_agent("chief-agent", text)
            out_path = _OUTPUT_DIR / f"{sname}_{mode}.txt"
            out_path.write_text(result.content)
            print(f"  Saved to {out_path} ({len(result.content)} chars)")

    # M278 scan
    print(f"\n\n{'=' * 60}")
    print("  M278 SCAN — ALL OUTPUTS")
    print(f"{'=' * 60}")
    detector = CommandDetector()
    for sname in ["quiet", "strong", "mixed"]:
        for mode in ["off", "inject"]:
            path = _OUTPUT_DIR / f"{sname}_{mode}.txt"
            text = path.read_text()
            flags = detector.scan(text)
            if not flags:
                print(f"\n  [{sname}/{mode}] 0 flags ✅")
            else:
                print(f"\n  [{sname}/{mode}] {len(flags)} flag(s):")
                for f in flags:
                    ctx_s = max(0, f.span_start - 30)
                    ctx_e = min(len(text), f.span_end + 30)
                    ctx = text[ctx_s:ctx_e].replace("\n", "↵")
                    print(f"    {f.category:22s} {f.match!r:20s} ...{ctx}...")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
