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

from clay.ai_control.runner import (
    AgentRunResult,
    AgentRunner,
    LiteLLMModelClient,
    OllamaNativeClient,
    RoutingModelClient,
    ServiceModelResolver,
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
    ollama = OllamaNativeClient.from_settings(OllamaSettings())
    llm = LiteLLMModelClient(adapter=LLMAdapter(LLMSettings()))
    router = RoutingModelClient(
        local_client=ollama,
        cloud_client=llm,
        transport_lookup=ai_control_service.transport_for,
    )
    resolver = ServiceModelResolver(ai_control_service)
    return AgentRunner(
        model_resolver=resolver,
        model_client=router,
        role_prompts={"chief-agent": CHIEF_AGENT_SYSTEM_PROMPT},
    )


async def _run_eval() -> None:
    runner = _build_runner()

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


def main() -> None:
    asyncio.run(_run_eval())


if __name__ == "__main__":
    main()
