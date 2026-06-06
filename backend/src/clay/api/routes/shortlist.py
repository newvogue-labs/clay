from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_ingestion_settings
from clay.db.repositories_market import MarketRepository
from clay.settings.ingestion import IngestionSettings
from clay.shortlist.read_models import build_shortlist_metrics


router = APIRouter(prefix="/shortlist", tags=["shortlist"])


@router.get("/metrics")
async def get_shortlist_metrics(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[IngestionSettings, Depends(get_ingestion_settings)],
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    repository = MarketRepository(session)
    bars = repository.list_latest_bars(limit=limit)
    freshness_rows = repository.list_freshness_statuses()
    items = build_shortlist_metrics(
        bars,
        freshness_rows,
        low_quote_volume_threshold=settings.low_quote_volume_threshold,
    )

    return {
        "items": [
            row.model_dump(mode="json")
            for row in items
        ],
    }
