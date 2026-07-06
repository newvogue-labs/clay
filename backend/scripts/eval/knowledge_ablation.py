"""E-KNOW S3b-C2: context-diff ablation (off vs inject), без LLM.

Сравнивает rendered context chief-agent в режимах off / inject на одном
снимке. Печатает разницу в символах и сохраняет оба контекста в /tmp/.

Run:
    python scripts/eval/knowledge_ablation.py

Требует работающий PostgreSQL с данными (см. .env / CLAY_DATABASE_URL).
"""

from __future__ import annotations

from clay.bootstrap import (
    ai_control_service,
    knowledge_service,
    session_factory,
    signal_engine_service,
)
from unittest.mock import MagicMock

from clay.scheduler.ai_agent_job import (
    AIAgentCycleJob,
    _render_context,
    _render_signals_section,
)


def _job(mode: str) -> AIAgentCycleJob:
    return AIAgentCycleJob(
        runner=MagicMock(),
        session_factory=session_factory,
        role_ids=["chief-agent"],
        ai_control_service=ai_control_service,
        knowledge_service=knowledge_service,
        knowledge_mode=mode,
        signal_engine_service=signal_engine_service,
    )


def main() -> None:
    with session_factory() as s:
        snap = ai_control_service.build_snapshot(s)
        sig = signal_engine_service.build_snapshot(s)

        # заморозили снимок для повторяемости
        with open("/tmp/eval_snapshot.json", "w") as f:
            f.write(snap.model_dump_json())

        signals_section = _render_signals_section(sig)
        base_ctx = _render_context(
            snap,
            "chief-agent",
            session=s,
            signals_section=signals_section,
        )
        off = _job("off")._maybe_apply_knowledge(s, base_ctx)
        inject = _job("inject")._maybe_apply_knowledge(s, base_ctx)

    for name, txt in (("off", off), ("inject", inject)):
        with open(f"/tmp/ctx_{name}.txt", "w") as f:
            f.write(txt)

    print(
        f"off={len(off)} chars | inject={len(inject)} chars | "
        f"added={len(inject) - len(off)}"
    )

    # diff: секции, которые есть в inject, но нет в off
    if "=== advisory_context ===" in inject:
        adv = inject.split("=== advisory_context ===")[1]
        print(f"\n=== advisory_context ({len(adv)} chars) ===")
        print(adv.strip()[:2000])


if __name__ == "__main__":
    main()
