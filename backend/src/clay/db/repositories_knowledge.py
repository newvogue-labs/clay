from datetime import datetime, UTC

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

    def upsert_item_by_external_id(self, payload: dict[str, object]) -> KnowledgeItem:
        now = datetime.now(UTC)
        stmt = pg_insert(KnowledgeItem).values(
            **payload,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_id"],
            set_={
                "title": stmt.excluded.title,
                "category": stmt.excluded.category,
                "priority": stmt.excluded.priority,
                "tags_csv": stmt.excluded.tags_csv,
                "source_type": stmt.excluded.source_type,
                "content": stmt.excluded.content,
                "updated_at": now,
            },
        )
        stmt = stmt.returning(KnowledgeItem)
        item = self.session.scalar(stmt)
        assert item is not None, "ON CONFLICT upsert must return item"
        return item

    def get_item_by_external_id(self, external_id: str) -> KnowledgeItem | None:
        return self.session.scalar(
            select(KnowledgeItem).where(KnowledgeItem.external_id == external_id)
        )

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

    def count_items(self) -> int:
        return int(
            self.session.scalar(select(func.count()).select_from(KnowledgeItem)) or 0
        )

    def count_chunks(self) -> int:
        return int(
            self.session.scalar(select(func.count()).select_from(KnowledgeChunk)) or 0
        )

    def list_chunks_for_item(self, item_id: int) -> list[KnowledgeChunk]:
        query = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.item_id == item_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
        return list(self.session.scalars(query).all())

    def delete_item(self, item_id: int) -> bool:
        item = self.session.get(KnowledgeItem, item_id)
        if item is None:
            return False
        self.session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.item_id == item_id)
        )
        self.session.delete(item)
        return True

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
        return list(self.session.execute(query).tuples().all())
