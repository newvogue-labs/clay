"""CcxtExchangeAdapter — shared ccxt logic for all venue adapters.

Extracted from ``BinanceExecutionAdapter`` (S-ADAPT-5b-1) so that
Bybit (and future venues) become thin subclasses without duplicating
the ccxt port implementation.

Subclasses must implement:
- ``_build_client()`` — create and return the venue-specific ccxt client.
- ``get_market_rules()`` — parse venue-specific market data into ``MarketRules``.
- ``_is_duplicate_cid(exc)`` — detect venue-specific duplicate clientOrderId errors.

Subclasses must define class attributes:
- ``supported_order_types`` — ``frozenset[OrderType]``.
- ``supported_tif`` — ``frozenset[TimeInForce]``.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, cast

import ccxt.async_support as ccxt

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    Fill,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import (
    Environment,
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
)
from clay.execution.adapter.errors import (
    AmbiguousExecutionError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OrderNotFoundError,
    OrderRejectedError,
    TransientAdapterError,
)
from clay.execution.adapter.rules import MarketRules


# ccxt status -> OrderState mapping
_STATE_MAP: dict[str, OrderState] = {
    "open": OrderState.NEW,
    "closed": OrderState.FILLED,
    "canceled": OrderState.CANCELED,
    "rejected": OrderState.REJECTED,
    "expired": OrderState.EXPIRED,
}


class CcxtExchangeAdapter:
    """Base adapter — shared ccxt logic for all venues.

    Implements ``ExchangeAdapter`` protocol.  Subclasses supply venue-specific
    hooks (client creation, market-rules parsing, duplicate-CID detection)
    while the base handles all common ccxt interaction patterns.
    """

    environment: Environment

    supported_order_types: ClassVar[frozenset[OrderType]]
    supported_tif: ClassVar[frozenset[TimeInForce]]

    def __init__(
        self,
        environment: Environment,
        *,
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        self.environment = environment
        self._client = self._build_client(api_key, api_secret)
        if environment == Environment.TESTNET:
            self._client.set_sandbox_mode(True)

    # -- pure domain (sync) ---------------------------------------------------

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        from clay.execution.adapter.normalization import validate_order

        validate_order(req, rules)

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        from clay.execution.adapter.normalization import quantize_order

        return quantize_order(req, rules)

    # -- network-bound (async) ------------------------------------------------

    @abstractmethod
    async def get_market_rules(self, symbol: str) -> MarketRules: ...

    async def place_order(self, req: OrderRequest) -> OrderAck:
        params = self._build_order_params(req)

        try:
            response = await self._client.create_order(
                symbol=req.symbol,
                type=cast(Any, req.order_type.value),
                side=req.side.value,
                amount=cast(Any, str(req.quantity)),
                price=str(req.price) if req.price is not None else None,
                params=params,
            )
        except ccxt.InsufficientFunds as exc:
            raise InsufficientFundsError(str(exc)) from exc
        except ccxt.InvalidOrder as exc:
            if self._is_duplicate_cid(exc):
                raise AmbiguousExecutionError(
                    f"duplicate clientOrderId ({self._dup_cid_code}): order may "
                    f"already exist, reconcile required (cid={req.client_order_id!r})"
                ) from exc
            raise InvalidOrderError(str(exc)) from exc
        except ccxt.NetworkError as exc:
            raise AmbiguousExecutionError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            if self._is_duplicate_cid(exc):
                raise AmbiguousExecutionError(
                    f"duplicate clientOrderId ({self._dup_cid_code}): order may "
                    f"already exist, reconcile required (cid={req.client_order_id!r})"
                ) from exc
            raise OrderRejectedError(str(exc)) from exc

        return self._ack_from_response(
            req.client_order_id, cast("dict[str, Any]", response)
        )

    async def cancel_order(self, symbol: str, venue_order_id: str) -> None:
        try:
            await self._client.cancel_order(id=venue_order_id, symbol=symbol)
        except ccxt.OrderNotFound:
            return
        except ccxt.NetworkError as exc:
            raise TransientAdapterError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc)) from exc

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        try:
            response = await self._client.fetch_order(id=venue_order_id, symbol=symbol)
        except ccxt.OrderNotFound as exc:
            raise OrderNotFoundError(
                f"order not found (venue_order_id={venue_order_id!r}, symbol={symbol!r})",
                symbol=symbol,
                venue_order_id=venue_order_id,
            ) from exc
        except ccxt.NetworkError as exc:
            raise TransientAdapterError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc)) from exc

        return self._snapshot_from_response(cast("dict[str, Any]", response))

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        try:
            orders = await self._client.fetch_open_orders(symbol=symbol)
        except ccxt.NetworkError as exc:
            raise TransientAdapterError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc)) from exc

        return [self._snapshot_from_response(cast("dict[str, Any]", o)) for o in orders]

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        since_ms = int(since.timestamp() * 1000)
        try:
            orders = await self._client.fetch_orders(symbol=symbol, since=since_ms)
        except ccxt.NetworkError as exc:
            raise TransientAdapterError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc)) from exc

        return [self._snapshot_from_response(cast("dict[str, Any]", o)) for o in orders]

    async def get_balances(self) -> list[BalanceSnapshot]:
        try:
            response = await self._client.fetch_balance()
        except ccxt.NetworkError as exc:
            raise TransientAdapterError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc)) from exc

        response_dict = cast("dict[str, Any]", response)
        balances: list[BalanceSnapshot] = []
        total: dict[str, Any] = response_dict.get("total", {})
        free: dict[str, Any] = response_dict.get("free", {})
        used: dict[str, Any] = response_dict.get("used", {})
        for asset, t in total.items():
            balances.append(
                BalanceSnapshot(
                    asset=asset,
                    free=_dec(free.get(asset)),
                    locked=_dec(used.get(asset)),
                    total=_dec(t),
                )
            )
        return balances

    async def close(self) -> None:
        await self._client.close()

    # -- venue-specific hooks -------------------------------------------------

    @abstractmethod
    def _build_client(self, api_key: str, api_secret: str) -> ccxt.Exchange:
        """Create and return the venue-specific ccxt client."""
        ...

    @abstractmethod
    def _is_duplicate_cid(self, exc: Exception) -> bool:
        """Detect venue-specific duplicate clientOrderId error."""
        ...

    _dup_cid_code: ClassVar[str] = ""

    @abstractmethod
    def _build_order_params(self, req: OrderRequest) -> dict[str, Any]:
        """Venue-specific create_order params (client-order-id key, stop encoding)."""
        ...

    # -- private helpers ------------------------------------------------------

    def _ack_from_response(
        self, client_order_id: str, response: dict[str, Any]
    ) -> OrderAck:
        fills = self._fills_from_trades(response)
        filled_qty = _dec(response.get("filled"))
        status = str(response.get("status", "open"))
        state = _map_state(status, filled_qty)

        price_raw = response.get("price")
        price = (
            _dec(price_raw) if price_raw is not None and _dec(price_raw) != 0 else None
        )
        return OrderAck(
            client_order_id=str(response.get("clientOrderId", client_order_id)),
            venue_order_id=str(response.get("id", "")),
            symbol=str(response.get("symbol", "")),
            side=OrderSide(str(response.get("side", "buy"))),
            order_type=OrderType(str(response.get("type", "limit"))),
            state=state,
            quantity=_dec(response.get("amount")),
            price=price,
            transact_time=int(response.get("timestamp", 0)),
            fills=tuple(fills),
        )

    def _snapshot_from_response(self, response: dict[str, Any]) -> OrderSnapshot:
        fills = self._fills_from_trades(response)
        filled_qty = _dec(response.get("filled"))
        status = str(response.get("status", "open"))
        state = _map_state(status, filled_qty)

        price_raw = response.get("price")
        price = (
            _dec(price_raw) if price_raw is not None and _dec(price_raw) != 0 else None
        )
        return OrderSnapshot(
            client_order_id=str(response.get("clientOrderId", "")),
            venue_order_id=str(response.get("id", "")),
            symbol=str(response.get("symbol", "")),
            side=OrderSide(str(response.get("side", "buy"))),
            order_type=OrderType(str(response.get("type", "limit"))),
            state=state,
            quantity=_dec(response.get("amount")),
            executed_qty=filled_qty,
            price=price,
            transact_time=int(response.get("timestamp", 0)),
            fills=tuple(fills),
        )

    def _fills_from_trades(self, response: dict[str, Any]) -> list[Fill]:
        trades = response.get("trades", [])
        if not trades:
            return []
        symbol = str(response.get("symbol", ""))
        venue_order_id = str(response.get("id", ""))
        return [
            Fill(
                trade_id=str(fill.get("id", "")),
                venue_order_id=venue_order_id,
                symbol=symbol,
                side=OrderSide(str(fill.get("side", "buy"))),
                quantity=_dec(fill.get("amount")),
                price=_dec(fill.get("price")),
                commission=_dec(fill.get("commission")),
                commission_asset=str(fill.get("commissionAsset", "")),
                transact_time=int(fill.get("timestamp", 0)),
            )
            for fill in trades
        ]


# -- module-level helpers (shared) -------------------------------------------


def _dec(val: Any) -> Decimal:
    """Safely convert a ccxt value to ``Decimal`` — never ``Decimal(float)``."""
    if val is None:
        return Decimal("0")
    s = str(val).strip()
    if not s:
        return Decimal("0")
    return Decimal(s)


def _map_state(status: str, filled: Decimal) -> OrderState:
    """Map ccxt order status to domain ``OrderState``.

    ``open`` with ``filled > 0`` -> ``PARTIALLY_FILLED``.
    """
    if status == "open":
        return OrderState.PARTIALLY_FILLED if filled > 0 else OrderState.NEW
    return _STATE_MAP.get(status, OrderState.NEW)
