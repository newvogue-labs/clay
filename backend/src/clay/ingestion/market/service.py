from collections.abc import Iterable

import httpx

from clay.db.repositories_market import MarketRepository
from clay.ingestion.market.exchange_config import ExchangeConfig
from clay.ingestion.market.models import NormalizedMarketBar
from clay.ingestion.market.protocol import MarketDataClient


class MarketIngestionService:
    """Coordinates market payload fetch and normalization across exchanges.

    E3: holds a dict of ``exchange_id → (client, config)`` — one entry
    per enabled exchange.  The outer loop in ``IngestionCycleService``
    iterates over exchanges then per-symbol/timeframe inside each,
    using the appropriate client for fetches.
    """

    def __init__(
        self,
        exchange_clients: dict[str, tuple[MarketDataClient, ExchangeConfig]],
    ) -> None:
        self.exchange_clients = exchange_clients

    def set_http_client(self, client: httpx.AsyncClient | None) -> None:
        """Inject the shared lifespan-owned HTTP client into every adapter."""
        for c, _ in self.exchange_clients.values():
            c.set_http_client(client)

    def persist_bars(
        self,
        repository: MarketRepository,
        bars: Iterable[NormalizedMarketBar],
    ) -> tuple[int, int]:
        """Persist bars; return ``(inserted, updated)`` (B5 counter split)."""
        return repository.upsert_market_bars(
            [bar.model_dump(mode="python") for bar in bars],
        )
