from typing import Protocol, runtime_checkable

import httpx

from clay.ingestion.market.models import NormalizedMarketBar


@runtime_checkable
class MarketDataClient(Protocol):
    """Protocol for exchange-agnostic market data access.

    Each exchange adapter implements this protocol to provide
    normalized kline/candlestick data. The pipeline depends on
    this abstraction, not on any specific exchange.

    ``set_http_client`` is optional for adapters that need HTTP
    client lifecycle management (production: FastAPI lifespan).
    Adapters backed by other transports (WebSocket, file, in-memory)
    can keep it as a no-op.
    """

    source: str

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
    ) -> list[NormalizedMarketBar]: ...

    def set_http_client(self, client: httpx.AsyncClient | None) -> None:
        """Override point for late-binding HTTP client injection.

        The default no-op allows non-HTTP adapters (test fakes,
        in-memory, file-backed) to conform without boilerplate.
        """
        return
