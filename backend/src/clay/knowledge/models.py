from typing import Literal

from pydantic import BaseModel


KnowledgeCategory = Literal["note", "strategy_rule", "checklist", "observation"]
KnowledgePriority = Literal["low", "medium", "high"]


class KnowledgeSummarySnapshot(BaseModel):
    total_items: int
    total_chunks: int
    retrieval_mode: str
    retrieval_policy: str
    hot_path_dependency: bool
    operator_message: str


class KnowledgeItemSnapshot(BaseModel):
    item_id: int
    title: str
    category: str
    priority: str
    tags: list[str]
    source_type: str
    content_preview: str
    created_at: str
    updated_at: str
    chunk_count: int


class KnowledgeSearchResultSnapshot(BaseModel):
    item_id: int
    title: str
    category: str
    priority: str
    tags: list[str]
    score: float
    matched_chunk: str
    rationale: str


class KnowledgeSnapshot(BaseModel):
    summary: KnowledgeSummarySnapshot
    recent_items: list[KnowledgeItemSnapshot]
    search_results: list[KnowledgeSearchResultSnapshot]


class KnowledgeCreateCommand(BaseModel):
    title: str
    category: KnowledgeCategory
    priority: KnowledgePriority
    tags: list[str]
    content: str
    source_type: str = "manual"
    external_id: str | None = None


class KnowledgeSearchCommand(BaseModel):
    query: str
    category: str | None = None
