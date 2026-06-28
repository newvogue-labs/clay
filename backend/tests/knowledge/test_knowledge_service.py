from pathlib import Path

from clay.audit.writer import AuditWriter
from clay.events.bus import EventBus
from clay.knowledge.models import KnowledgeCreateCommand
from clay.knowledge.service import KnowledgeService


def build_knowledge_service(tmp_path: Path) -> KnowledgeService:
    audit_writer = AuditWriter(tmp_path / "state")
    event_bus = EventBus()
    return KnowledgeService(audit_writer=audit_writer, event_bus=event_bus)


def test_knowledge_service_creates_items_and_chunks(db_session, tmp_path: Path) -> None:
    service = build_knowledge_service(tmp_path)

    snapshot = service.create_item(
        db_session,
        KnowledgeCreateCommand(
            title="Momentum checklist",
            category="checklist",
            priority="high",
            tags=["momentum", "entry"],
            content=(
                "Check liquidity before entry.\n\n"
                "Confirm alignment with higher timeframe structure. "
                "Avoid low-volume chop. Respect invalidation."
            ),
        ),
    )

    assert snapshot.summary.total_items == 1
    assert snapshot.summary.total_chunks >= 1
    assert snapshot.recent_items[0].chunk_count >= 1


def test_knowledge_service_searches_with_keyword_and_priority(
    db_session, tmp_path: Path
) -> None:
    service = build_knowledge_service(tmp_path)
    service.create_item(
        db_session,
        KnowledgeCreateCommand(
            title="Breakout observation",
            category="observation",
            priority="high",
            tags=["breakout", "btc"],
            content="BTC breakout works best when liquidity expands and retests hold.",
        ),
    )
    service.create_item(
        db_session,
        KnowledgeCreateCommand(
            title="General note",
            category="note",
            priority="low",
            tags=["journal"],
            content="Random low-priority note about unrelated market drift.",
        ),
    )

    results = service.search(db_session, query="BTC breakout liquidity", category=None)

    assert results
    assert results[0].title == "Breakout observation"
    assert "advisory" in results[0].rationale
