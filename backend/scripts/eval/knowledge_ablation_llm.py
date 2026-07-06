"""E-KNOW S3b-C2: A/B прогон chief-agent на реальном LLM (off vs inject).

Безопасно: read-only, никакого исполнения сделок; вне торгового пути (M278).
Флаги в проде не трогаем — раннер создаётся локально на тех же настройках.

Run:
    python scripts/eval/knowledge_ablation_llm.py

Требует:
    - Работающий PostgreSQL (CLAY_DATABASE_URL)
    - Доступ к LLM (CLAY_LLM_* / Ollama)
    - ~30-60 сек на ответ
"""

from __future__ import annotations

import asyncio
import os

from clay.ai_control.runner import (
    AgentRunResult,
    AgentRunner,
    LiteLLMModelClient,
    OllamaNativeClient,
    RoutingModelClient,
)
from clay.bootstrap import (
    ai_control_service,
    knowledge_service,
    session_factory,
    signal_engine_service,
)
from clay.llm import LLMAdapter
from clay.scheduler.ai_agent_job import (
    _render_context,
    _render_signals_section,
)
from clay.scheduler.prompts import CHIEF_AGENT_SYSTEM_PROMPT
from clay.settings.llm import LLMSettings
from clay.settings.ollama import OllamaSettings


def _build_runner() -> AgentRunner:
    model_id = os.environ.get("CHIEF_AGENT_MODEL", "minimax-m3")
    ollama = OllamaNativeClient.from_settings(OllamaSettings())
    llm = LiteLLMModelClient(adapter=LLMAdapter(LLMSettings()))
    router = RoutingModelClient(
        local_client=ollama,
        cloud_client=llm,
        transport_lookup=ai_control_service.transport_for,
    )

    # bypass resolver for eval: force minimax-m3 (gemma-4-31b via Gemini
    # returns null content when think=True, which breaks our eval)
    class _EvalModelResolver:
        def resolve_model_id(self, role_id: str) -> str:
            return model_id

    runner = AgentRunner(
        model_resolver=_EvalModelResolver(),
        model_client=router,
        role_prompts={"chief-agent": CHIEF_AGENT_SYSTEM_PROMPT},
    )
    return runner


def _lite_llm_is_alive() -> bool:
    """Check production LiteLLM at :4000 with auth."""
    import httpx

    mk = os.environ.get("LITELLM_MASTER_KEY", "")
    if not mk:
        return False
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(
                "http://127.0.0.1:4000/health",
                headers={"Authorization": f"Bearer {mk}"},
            )
            return r.is_success
    except Exception:
        return False


class _FixedModelResolver:
    """Always returns the same model_id — bypasses AI-control assignments."""

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    def resolve_model_id(self, role_id: str) -> str:
        return self._model_id


def _build_local_runner() -> AgentRunner:
    """Simplified runner that always uses the local Ollama model.

    Use when the cloud transport (LiteLLM) is unavailable in the current
    environment. Assumes ``gemma4:e2b-it-qat`` exists locally.
    """
    ollama = OllamaNativeClient.from_settings(OllamaSettings())
    return AgentRunner(
        model_resolver=_FixedModelResolver("gemma4:e2b-it-qat"),
        model_client=ollama,
        role_prompts={"chief-agent": CHIEF_AGENT_SYSTEM_PROMPT},
    )


async def _try_cloud_runner() -> AgentRunner | None:
    """Build cloud runner if production LiteLLM is reachable, else return None."""
    if not _lite_llm_is_alive():
        return None
    return _build_runner()


async def _run_eval() -> None:
    cloud = await _try_cloud_runner()
    if cloud is not None:
        runner = cloud
        print("=== Using cloud model (LiteLLM) ===", flush=True)
    else:
        runner = _build_local_runner()
        print("=== Using local model (gemma4:e2b-it-qat) ===", flush=True)

    # --- один снимок на две ветки -------------------------------------------
    with session_factory() as s:
        snap = ai_control_service.build_snapshot(s)
        sig = signal_engine_service.build_snapshot(s)
        signals_section = _render_signals_section(sig)

        # off
        ctx_off = _render_context(
            snap,
            "chief-agent",
            session=s,
            signals_section=signals_section,
        )

        # inject: через заглушку AIAgentCycleJob (runner не нужен —
        # вызываем только _retrieve_advisory_cards + _append_advisory_section)
        ctx_inject = _render_context(
            snap,
            "chief-agent",
            session=s,
            signals_section=signals_section,
        )

        from unittest.mock import MagicMock
        from clay.scheduler.ai_agent_job import AIAgentCycleJob

        dummy = AIAgentCycleJob(
            runner=MagicMock(),
            session_factory=session_factory,
            role_ids=["chief-agent"],
            ai_control_service=ai_control_service,
            knowledge_service=knowledge_service,
            knowledge_mode="inject",
            signal_engine_service=signal_engine_service,
        )
        ctx_inject = dummy._maybe_apply_knowledge(s, ctx_inject)

    # --- прогон LLM ---------------------------------------------------------
    print("=== OFF === calling LLM ...", flush=True)
    off = await runner.run_agent("chief-agent", ctx_off)

    print("=== INJECT === calling LLM ...", flush=True)
    inject = await runner.run_agent("chief-agent", ctx_inject)

    # --- вывод --------------------------------------------------------------
    def _show(label: str, result: AgentRunResult) -> None:
        print(f"\n{'=' * 60}")
        print(f"  {label}")
        print(f"  model_id: {result.model_id}")
        print(f"  content ({len(result.content)} chars)")
        print(f"{'=' * 60}")
        print(result.content)
        if result.thinking:
            print(f"\n  --- thinking ({len(result.thinking)} chars) ---")
            print(result.thinking[:500])

    _show("OFF SUMMARY", off)
    _show("INJECT SUMMARY", inject)

    with open("/tmp/summary_off.txt", "w") as f:
        f.write(off.content)
    with open("/tmp/summary_inject.txt", "w") as f:
        f.write(inject.content)
    print("\nSaved to /tmp/summary_off.txt and /tmp/summary_inject.txt")

    # --- M278 report ---------------------------------------------------------
    def _m278_report(label: str, text: str) -> None:
        from clay.scheduler.commands import CommandDetector

        flags = CommandDetector().scan(text)
        if not flags:
            print(f"\n  M278 [{label}]: 0 flags ✅")
            return
        print(f"\n  M278 [{label}]: {len(flags)} flag(s)")
        for f in flags:
            ctx_start = max(0, f.span_start - 20)
            ctx_end = min(len(text), f.span_end + 20)
            ctx = text[ctx_start:ctx_end].replace("\n", "↵")
            print(f"    {f.category:22s} {f.match!r:20s} ...{ctx}...")

    _m278_report("off", off.content)
    _m278_report("inject", inject.content)


def main() -> None:
    asyncio.run(_run_eval())


if __name__ == "__main__":
    main()
