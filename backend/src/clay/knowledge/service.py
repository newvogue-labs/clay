from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
import re

from sqlalchemy.orm import Session

from clay.audit.writer import AuditWriter
from clay.db.repositories_knowledge import KnowledgeRepository
from clay.events.bus import EventBus
from clay.knowledge.models import (
    KnowledgeCreateCommand,
    KnowledgeItemSnapshot,
    KnowledgeSearchResultSnapshot,
    KnowledgeSnapshot,
    KnowledgeSummarySnapshot,
)


@dataclass(frozen=True)
class ScoredChunk:
    item_id: int
    title: str
    category: str
    priority: str
    tags: list[str]
    matched_chunk: str
    score: float


class KnowledgeService:
    def __init__(
        self,
        *,
        audit_writer: AuditWriter,
        event_bus: EventBus,
    ) -> None:
        self.audit_writer = audit_writer
        self.event_bus = event_bus

    def build_snapshot(
        self,
        session: Session,
        *,
        query: str | None = None,
        category: str | None = None,
    ) -> KnowledgeSnapshot:
        repository = KnowledgeRepository(session)
        items = repository.list_recent_items(limit=20)
        search_results: list[KnowledgeSearchResultSnapshot] = []
        if query:
            search_results = self.search(session, query=query, category=category)

        return KnowledgeSnapshot(
            summary=self._build_summary(session, items),
            recent_items=[self._serialize_item(session, item) for item in items],
            search_results=search_results,
        )

    def create_item(
        self,
        session: Session,
        command: KnowledgeCreateCommand,
    ) -> KnowledgeSnapshot:
        repository = KnowledgeRepository(session)
        now = datetime.now(UTC)
        item = repository.create_item(
            {
                "title": command.title,
                "category": command.category,
                "priority": command.priority,
                "tags_csv": ",".join(command.tags),
                "source_type": command.source_type,
                "content": command.content,
                "created_at": now,
                "updated_at": now,
            }
        )
        chunks = self._chunk_content(command.content)
        repository.replace_chunks(
            item_id=item.id,
            chunks=[
                {
                    "chunk_index": index,
                    "chunk_text": chunk_text,
                    "chunk_type": chunk_type,
                    "token_estimate": self._token_estimate(chunk_text),
                }
                for index, (chunk_type, chunk_text) in enumerate(chunks)
            ],
        )
        session.commit()
        self.audit_writer.write(
            "knowledge.item.created",
            {
                "item_id": item.id,
                "title": item.title,
                "category": item.category,
                "priority": item.priority,
            },
        )
        self.event_bus.publish(
            "knowledge.updated",
            {
                "event_type": "knowledge.item.created",
                "item_id": item.id,
                "category": item.category,
            },
        )
        return self.build_snapshot(session)

    def search(
        self,
        session: Session,
        *,
        query: str,
        category: str | None = None,
    ) -> list[KnowledgeSearchResultSnapshot]:
        repository = KnowledgeRepository(session)
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        candidates = repository.list_search_candidates(category=category, limit=200)
        scored: list[ScoredChunk] = []
        for item, chunk in candidates:
            score = self._score_chunk(
                query_tokens=query_tokens,
                title=item.title,
                tags=item.tags_csv.split(",") if item.tags_csv else [],
                chunk_text=chunk.chunk_text,
                priority=item.priority,
            )
            if score <= 0:
                continue
            scored.append(
                ScoredChunk(
                    item_id=item.id,
                    title=item.title,
                    category=item.category,
                    priority=item.priority,
                    tags=item.tags_csv.split(",") if item.tags_csv else [],
                    matched_chunk=chunk.chunk_text,
                    score=round(score, 4),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        deduped: dict[int, ScoredChunk] = {}
        for row in scored:
            deduped.setdefault(row.item_id, row)

        return [
            KnowledgeSearchResultSnapshot(
                item_id=row.item_id,
                title=row.title,
                category=row.category,
                priority=row.priority,
                tags=[tag for tag in row.tags if tag],
                score=row.score,
                matched_chunk=row.matched_chunk,
                rationale=self._build_rationale(row),
            )
            for row in list(deduped.values())[:10]
        ]

    def _build_summary(self, session: Session, items) -> KnowledgeSummarySnapshot:
        repository = KnowledgeRepository(session)
        total_chunks = sum(
            len(repository.list_chunks_for_item(item.id)) for item in items
        )
        return KnowledgeSummarySnapshot(
            total_items=len(items),
            total_chunks=total_chunks,
            retrieval_mode="keyword_plus_metadata",
            retrieval_policy="review and research only",
            hot_path_dependency=False,
            operator_message=(
                "Knowledge layer is available for research and review, "
                "but it stays outside the realtime signal path."
            ),
        )

    def _serialize_item(self, session: Session, item) -> KnowledgeItemSnapshot:
        repository = KnowledgeRepository(session)
        chunks = repository.list_chunks_for_item(item.id)
        return KnowledgeItemSnapshot(
            item_id=item.id,
            title=item.title,
            category=item.category,
            priority=item.priority,
            tags=[tag for tag in item.tags_csv.split(",") if tag],
            source_type=item.source_type,
            content_preview=item.content[:180],
            created_at=item.created_at.isoformat(),
            updated_at=item.updated_at.isoformat(),
            chunk_count=len(chunks),
        )

    def _chunk_content(self, content: str) -> list[tuple[str, str]]:
        normalized = content.strip()
        if not normalized:
            return [("paragraph", "")]
        paragraphs = [
            part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()
        ]
        chunks: list[tuple[str, str]] = []
        for paragraph in paragraphs:
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
                if sentence.strip()
            ]
            if len(sentences) <= 2:
                chunks.append(("paragraph", paragraph))
                continue
            current: list[str] = []
            for sentence in sentences:
                current.append(sentence)
                if len(current) == 2:
                    chunks.append(("semantic_window", " ".join(current)))
                    current = [current[-1]]
            if current:
                chunks.append(("semantic_window", " ".join(current)))
        return chunks

    def _token_estimate(self, text: str) -> float:
        words = len(self._tokenize(text))
        return round(words * 1.35, 2)

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if token]

    def _score_chunk(
        self,
        *,
        query_tokens: list[str],
        title: str,
        tags: list[str],
        chunk_text: str,
        priority: str,
    ) -> float:
        haystack_tokens = self._tokenize(f"{title} {' '.join(tags)} {chunk_text}")
        if not haystack_tokens:
            return 0.0
        hit_count = sum(haystack_tokens.count(token) for token in query_tokens)
        coverage = len(
            {token for token in query_tokens if token in haystack_tokens}
        ) / len(query_tokens)
        priority_bonus = {"low": 0.0, "medium": 0.15, "high": 0.3}.get(priority, 0.0)
        density = hit_count / max(math.sqrt(len(haystack_tokens)), 1)
        return (coverage * 1.4) + density + priority_bonus

    def _build_rationale(self, row: ScoredChunk) -> str:
        return (
            f"{row.category} content matched the query with priority {row.priority}; "
            "retrieval remains advisory and does not affect live signal ranking."
        )
