from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session
from clay.db.repositories_market import MarketRepository

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/bars/latest")
async def get_latest_market_bars(
    session: Annotated[Session, Depends(get_db_session)],
    symbol: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    repository = MarketRepository(session)
    items = repository.list_latest_bars(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )

    return {
        "items": [
            {
                "symbol": row.symbol,
                "timeframe": row.timeframe,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "quote_volume": row.quote_volume,
                "source": row.source,
                "bar_open_time": row.bar_open_time.isoformat(),
                "bar_close_time": row.bar_close_time.isoformat(),
            }
            for row in items
        ],
    }
