from collections.abc import Iterable, Sequence
from typing import Any

from clay.db.repositories_market import MarketRepository
from clay.ingestion.market.binance_client import BinanceSpotClient
from clay.ingestion.market.models import NormalizedMarketBar
from clay.ingestion.market.normalizer import normalize_kline_payload


class MarketIngestionService:
    """Coordinates market payload fetch and normalization."""

    def __init__(self, client: BinanceSpotClient) -> None:
        self.client = client

    async def fetch_and_normalize(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
    ) -> list[NormalizedMarketBar]:
        payloads = await self.client.fetch_klines(symbol=symbol, interval=interval, limit=limit)
        return [self._normalize_kline_row(symbol, interval, row) for row in payloads]

    def persist_bars(
        self,
        repository: MarketRepository,
        bars: Iterable[NormalizedMarketBar],
    ) -> tuple[int, int]:
        """Persist bars; return ``(inserted, updated)`` (B5 counter split)."""
        return repository.upsert_market_bars(
            [bar.model_dump(mode="python") for bar in bars],
        )

    def _normalize_kline_row(
        self,
        symbol: str,
        interval: str,
        row: Sequence[Any],
    ) -> NormalizedMarketBar:
        return normalize_kline_payload(
            {
                "symbol": symbol,
                "interval": interval,
                "kline": {
                    "t": row[0],
                    "o": row[1],
                    "h": row[2],
                    "l": row[3],
                    "c": row[4],
                    "v": row[5],
                    "T": row[6],
                    "q": row[7] if len(row) > 7 else None,
                },
            },
        )
