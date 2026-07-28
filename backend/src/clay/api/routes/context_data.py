from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session
from clay.db.repositories_context import ContextRepository

router = APIRouter(prefix="/context-data", tags=["context-data"])


@router.get("/summary")
async def get_context_summary(
    session: Annotated[Session, Depends(get_db_session)],
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, object]:
    repository = ContextRepository(session)
    news = repository.latest_news(limit=limit)
    sentiment = repository.latest_sentiment(limit=limit)

    return {
        "news": [
            {
                "source_name": row.source_name,
                "headline": row.headline,
                "summary": row.summary,
                "symbol": row.symbol,
                "published_at": row.published_at.isoformat(),
                "source_url": row.source_url,
            }
            for row in news
        ],
        "sentiment": [
            {
                "source_name": row.source_name,
                "symbol": row.symbol,
                "sentiment_label": row.sentiment_label,
                "sentiment_score": row.sentiment_score,
                "captured_at": row.captured_at.isoformat(),
            }
            for row in sentiment
        ],
    }
