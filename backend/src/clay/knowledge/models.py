from typing import Literal

from pydantic import BaseModel


KnowledgeCategory = Literal["note", "strategy_rule", "checklist", "observation"]
"""Item category: ``note`` (general), ``strategy_rule`` (trading rule), ``checklist`` (process), ``observation`` (market finding)."""

KnowledgePriority = Literal["low", "medium", "high"]
"""Item priority: ``low`` (background reference), ``medium`` (advisory context), ``high`` (operator-critical)."""


class KnowledgeSummarySnapshot(BaseModel):
    """Aggregate counts and retrieval-policy summary for the knowledge layer.

    The ``retrieval_mode`` is ``keyword_plus_metadata`` (token-match with
    priority bonus). The ``retrieval_policy`` is advisory — review and
    research only — and ``hot_path_dependency`` is ``False``: the knowledge
    layer sits outside the realtime signal path (M278).
    """

    total_items: int
    total_chunks: int
    retrieval_mode: str
    retrieval_policy: str
    hot_path_dependency: bool
    operator_message: str


class KnowledgeItemSnapshot(BaseModel):
    """Serialised knowledge item card for the operator dashboard.

    The ``content_preview`` is truncated to 180 characters. The
    ``chunk_count`` reflects how many text chunks the item was split
    into for retrieval scoring. Tags and dates use ISO-8601 strings.
    """

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
    """Keyword+metadata search result with score and provenance.

    The ``score`` is a composite of token coverage, density, and priority
    bonus — used for advisory ranking only, not live signal scoring. The
    ``rationale`` explains why the chunk matched and restates that
    retrieval remains advisory.
    """

    item_id: int
    title: str
    category: str
    priority: str
    tags: list[str]
    score: float
    matched_chunk: str
    rationale: str


class KnowledgeSnapshot(BaseModel):
    """Composite knowledge snapshot: summary, recent items, and search results.

    Returned by KnowledgeService.build_snapshot as the root response for
    the /api/knowledge endpoint. The ``search_results`` list is empty
    when no query is provided.
    """

    summary: KnowledgeSummarySnapshot
    recent_items: list[KnowledgeItemSnapshot]
    search_results: list[KnowledgeSearchResultSnapshot]


class KnowledgeCreateCommand(BaseModel):
    """Command to create or upsert a knowledge item.

    All fields except ``source_type`` and ``external_id`` are required.
    When ``external_id`` is provided, the service upserts by external ID
    (idempotent); otherwise a new item is created. The ``source_type``
    defaults to ``"manual"`` for operator-entered content.
    """

    title: str
    category: KnowledgeCategory
    priority: KnowledgePriority
    tags: list[str]
    content: str
    source_type: str = "manual"
    external_id: str | None = None


class KnowledgeSearchCommand(BaseModel):
    """Command to search the knowledge layer by keyword.

    The ``query`` is tokenized and matched against title, tags, and chunk
    text. The optional ``category`` filter narrows candidates before
    scoring.
    """

    query: str
    category: str | None = None
