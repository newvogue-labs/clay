from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from clay.db.models_knowledge import KnowledgeChunk, KnowledgeItem


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_item(self, payload: dict[str, object]) -> KnowledgeItem:
        item = KnowledgeItem(**payload)
        self.session.add(item)
        self.session.flush()
        return item

    def replace_chunks(
        self, *, item_id: int, chunks: list[dict[str, object]]
    ) -> list[KnowledgeChunk]:
        self.session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.item_id == item_id)
        )
        rows = [KnowledgeChunk(item_id=item_id, **chunk) for chunk in chunks]
        self.session.add_all(rows)
        self.session.flush()
        return rows

    def list_recent_items(self, *, limit: int = 20) -> list[KnowledgeItem]:
        query = (
            select(KnowledgeItem).order_by(KnowledgeItem.updated_at.desc()).limit(limit)
        )
        return list(self.session.scalars(query).all())

    def list_chunks_for_item(self, item_id: int) -> list[KnowledgeChunk]:
        query = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.item_id == item_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
        return list(self.session.scalars(query).all())

    def list_search_candidates(
        self,
        *,
        category: str | None = None,
        limit: int = 100,
    ) -> list[tuple[KnowledgeItem, KnowledgeChunk]]:
        query = (
            select(KnowledgeItem, KnowledgeChunk)
            .join(KnowledgeChunk, KnowledgeChunk.item_id == KnowledgeItem.id)
            .order_by(KnowledgeItem.updated_at.desc(), KnowledgeChunk.chunk_index.asc())
            .limit(limit)
        )
        if category is not None:
            query = query.where(KnowledgeItem.category == category)
        return list(self.session.execute(query).all())
