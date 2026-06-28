import asyncio
from pathlib import Path

from clay.api.routes.knowledge import create_knowledge_item, get_knowledge_overview
from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.knowledge.models import KnowledgeCreateCommand
from clay.knowledge.service import KnowledgeService


def build_knowledge_service(tmp_path: Path) -> KnowledgeService:
    return KnowledgeService(
        audit_writer=AuditWriter(tmp_path / "state"),
        event_bus=EventBus(),
    )


def test_knowledge_overview_route_returns_snapshot(db_session, tmp_path: Path) -> None:
    service = build_knowledge_service(tmp_path)
    service.create_item(
        db_session,
        KnowledgeCreateCommand(
            title="Risk checklist",
            category="checklist",
            priority="medium",
            tags=["risk"],
            content="Review invalidation before the entry.",
        ),
    )

    payload = asyncio.run(get_knowledge_overview(db_session, service))

    assert payload["summary"]["hot_path_dependency"] is False
    assert payload["recent_items"][0]["title"] == "Risk checklist"


def test_knowledge_create_route_and_search(db_session, tmp_path: Path) -> None:
    service = build_knowledge_service(tmp_path)
    asyncio.run(
        create_knowledge_item(
            KnowledgeCreateCommand(
                title="Strategy rule",
                category="strategy_rule",
                priority="high",
                tags=["trend", "momentum"],
                content="Use momentum continuation only when higher timeframe is aligned.",
            ),
            db_session,
            service,
        )
    )

    payload = asyncio.run(
        get_knowledge_overview(
            db_session, service, query="higher timeframe momentum", category=None
        )
    )

    assert payload["search_results"]
    assert payload["search_results"][0]["title"] == "Strategy rule"
