from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from clay.execution.models import (
        Balance,
        CancelResult,
        OrderResult,
        OrderStatus,
        TradeFill,
    )


@runtime_checkable
class ExecutionClient(Protocol):
    """Exchange-agnostic protocol for order execution.

    Independent from ``MarketDataClient`` (ADR-008). Responsible for
    order lifecycle, balances, and trade fills — not market data.
    """

    source: str

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        *,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "GTC",
        client_order_id: str | None = None,
    ) -> OrderResult: ...

    async def cancel_order(self, symbol: str, order_id: str) -> CancelResult: ...

    async def get_order_status(self, symbol: str, order_id: str) -> OrderStatus: ...

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderStatus]: ...

    async def get_balances(self) -> list[Balance]: ...

    async def get_recent_trades(
        self, symbol: str, *, limit: int = 500
    ) -> list[TradeFill]: ...
