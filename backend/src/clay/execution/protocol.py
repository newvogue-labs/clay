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
    ) -> OrderResult:
        """Submit a new order to the exchange.

        Args:
            symbol: Trading pair symbol (e.g. ``"BTCUSDT"``).
            side: Order side — ``"buy"`` or ``"sell"``.
            quantity: Order quantity in base asset units.
            order_type: Exchange order type (e.g. ``"MARKET"``, ``"LIMIT"``).
            price: Limit price.  Required for ``LIMIT`` orders.
            stop_price: Stop price for stop-limit orders.
            time_in_force: Time-in-force policy (default ``"GTC"``).
            client_order_id: Caller-specified order ID for client-side tracking.

        Returns:
            An OrderResult snapshot of the exchange response.

        Raises:
            OrderRejectedError: Exchange rejected the order.
            OrderTimeoutError: Network or timeout error.
            PartialFillError: Order partially filled beyond tolerance.
        """
        ...

    async def cancel_order(self, symbol: str, order_id: str) -> CancelResult:
        """Cancel an open order.

        Args:
            symbol: Trading pair symbol.
            order_id: Exchange order ID to cancel.

        Returns:
            A CancelResult snapshot.  If the order was not found,
            ``status`` is ``"not_found"``.
        """
        ...

    async def get_order_status(self, symbol: str, order_id: str) -> OrderStatus:
        """Fetch the current status of a specific order.

        Args:
            symbol: Trading pair symbol.
            order_id: Exchange order ID.

        Returns:
            An OrderStatus snapshot.  If not found, ``status`` is
            ``"not_found"`` with zeroed quantities.
        """
        ...

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderStatus]:
        """List all open orders, optionally filtered by symbol.

        Args:
            symbol: If provided, only return orders for this pair.

        Returns:
            A list of OrderStatus snapshots for open orders.
        """
        ...

    async def get_balances(self) -> list[Balance]:
        """Fetch all asset balances for the account.

        Returns:
            A list of Balance snapshots for each asset with a non-zero
            total.
        """
        ...

    async def get_recent_trades(
        self, symbol: str, *, limit: int = 500
    ) -> list[TradeFill]:
        """Fetch recent trade fills for a symbol.

        Args:
            symbol: Trading pair symbol.
            limit: Maximum number of fills to return (default 500).

        Returns:
            A list of TradeFill snapshots, most recent first.
        """
        ...
