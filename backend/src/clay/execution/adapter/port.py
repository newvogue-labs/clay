"""ExchangeAdapter port — the contract all venue implementations satisfy.

``validate_order`` and ``quantize_order`` are **sync** (pure domain).
Network-bound methods are **async**.

This deviates from the async-only formulation in ADR-032 §Decision(a):
the correction is noted here and should be patched in a doc-only follow-up.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    Fill,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import CancelResult, Environment
from clay.execution.adapter.rules import MarketRules


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Contract for a venue-specific exchange adapter."""

    environment: Environment

    # -- pure domain (sync) ---------------------------------------------------

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None: ...

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest: ...

    # -- network-bound (async) ------------------------------------------------

    async def get_market_rules(self, symbol: str) -> MarketRules: ...

    async def place_order(self, req: OrderRequest) -> OrderAck: ...

    async def cancel_order(
        self, symbol: str, venue_order_id: str
    ) -> CancelResult: ...

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        """Fetch a single order by venue ID.

        Raises ``OrderNotFoundError`` when the venue reports the order
        does not exist.
        """
        ...

    async def get_open_orders(
        self, symbol: str | None = None
    ) -> list[OrderSnapshot]: ...

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]: ...

    async def get_balances(self) -> list[BalanceSnapshot]: ...

    async def get_my_trades(
        self, symbol: str, *, since: datetime | None = None, from_id: str | None = None
    ) -> list[Fill]:
        """Вернуть трейды аккаунта по символу.

        ``from_id`` — venue-курсор пагинации (id последнего обработанного трейда).
        ``since`` — fallback/инициализация (ms-imestamp начала окна).
        """
        ...

    async def get_by_client_order_id(
        self, symbol: str, client_order_id: str
    ) -> OrderSnapshot | None:
        """Resolve order by client_order_id (for projections with venue_order_id=None).

        Returns OrderSnapshot if found, None if not found.
        Implemented per-venue: Binance uses origClientOrderId, Bybit uses orderLinkId.
        """
        ...
