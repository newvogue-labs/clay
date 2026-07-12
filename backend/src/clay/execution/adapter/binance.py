"""Binance Spot concrete adapter (ccxt-based, S-ADAPT-2).

Implements ``ExchangeAdapter`` for Binance Spot (testnet + production).
ccxt client can be injected for testing; ``None`` → real ``ccxt.binance``.

Error-map (safety-critical):
- ``place_order``: ``NetworkError`` → ``AmbiguousExecutionError`` (not transient).
- Read methods: ``NetworkError`` → ``TransientAdapterError`` (retry-safe).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast

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
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.errors import (
    AmbiguousExecutionError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OrderRejectedError,
    TransientAdapterError,
)
from clay.execution.adapter.normalization import quantize_order, validate_order
from clay.execution.adapter.rules import MarketRules

# Binance Spot supported order types and TIF policies
_SPOT_ORDER_TYPES: frozenset[OrderType] = frozenset(
    {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
)
_SPOT_TIF: frozenset[TimeInForce] = frozenset(
    {TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}
)

# ccxt status → OrderState mapping
_STATE_MAP: dict[str, OrderState] = {
    "open": OrderState.NEW,
    "closed": OrderState.FILLED,
    "canceled": OrderState.CANCELED,
    "rejected": OrderState.REJECTED,
    "expired": OrderState.EXPIRED,
}


def _map_state(status: str, filled: Decimal) -> OrderState:
    """Map ccxt order status to domain ``OrderState``.

    ``open`` with ``filled > 0`` → ``PARTIALLY_FILLED``.
    """
    if status == "open":
        return OrderState.PARTIALLY_FILLED if filled > 0 else OrderState.NEW
    return _STATE_MAP.get(status, OrderState.NEW)


def _dec(val: Any) -> Decimal:
    """Safely convert a ccxt value to ``Decimal`` — never ``Decimal(float)``."""
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


class BinanceExecutionAdapter:
    """Binance Spot adapter implementing ``ExchangeAdapter``.

    Constructor:
        ``environment`` — deployment target (``TESTNET`` / ``PRODUCTION``).
        ``api_key`` / ``api_secret`` — from env, never from TOML/repo.
        ``client`` — optional injected ccxt instance for testing.
    """

    environment: Environment

    def __init__(
        self,
        environment: Environment,
        *,
        api_key: str = "",
        api_secret: str = "",
        client: ccxt.binance | None = None,
    ) -> None:
        self.environment = environment
        if client is not None:
            self._client = client
        else:
            if not api_key or not api_secret:
                raise ConfigError(
                    "api_key and api_secret are required when client is not injected"
                )
            self._client = ccxt.binance(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "options": {
                        "defaultType": "spot",
                        "adjustForTimeDifference": True,
                    },
                    "timeout": 30000,
                }
            )

        if environment == Environment.TESTNET:
            self._client.set_sandbox_mode(True)

    # -- pure domain (sync) ---------------------------------------------------

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        validate_order(req, rules)

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        return quantize_order(req, rules)

    # -- network-bound (async) ------------------------------------------------

    async def get_market_rules(self, symbol: str) -> MarketRules:
        try:
            markets = await self._client.load_markets()
        except ccxt.NetworkError as exc:
            raise TransientAdapterError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc)) from exc

        market = markets.get(symbol)
        if market is None:
            raise InvalidOrderError(f"unknown symbol: {symbol}")

        info: dict[str, Any] = market.get("info", {})
        filters: list[dict[str, Any]] = info.get("filters", [])

        lot_size = next((f for f in filters if f.get("filterType") == "LOT_SIZE"), {})
        price_filter = next(
            (f for f in filters if f.get("filterType") == "PRICE_FILTER"), {}
        )
        notional_filter = next(
            (f for f in filters if f.get("filterType") == "NOTIONAL"), {}
        )

        amount_step = _dec(lot_size.get("stepSize"))
        min_amount = _dec(lot_size.get("minQty"))
        max_amount = _dec(lot_size.get("maxQty"))
        price_tick = _dec(price_filter.get("tickSize"))
        min_price = _dec(price_filter.get("minPrice"))
        max_price = _dec(price_filter.get("maxPrice"))
        min_notional = _dec(notional_filter.get("minNotional"))

        return MarketRules(
            min_amount=min_amount,
            max_amount=max_amount,
            min_price=min_price,
            max_price=max_price,
            min_notional=min_notional,
            amount_step=amount_step,
            price_tick=price_tick,
            precision_mode=PrecisionMode.TICK_SIZE,
            supported_order_types=_SPOT_ORDER_TYPES,
            supported_tif=_SPOT_TIF,
        )

    async def place_order(self, req: OrderRequest) -> OrderAck:
        params: dict[str, Any] = {"newClientOrderId": req.client_order_id}
        if req.stop_price is not None:
            params["stopPrice"] = str(req.stop_price)

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
            raise InvalidOrderError(str(exc)) from exc
        except ccxt.NetworkError as exc:
            raise AmbiguousExecutionError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
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
        except ccxt.OrderNotFound:
            return OrderSnapshot(
                client_order_id="",
                venue_order_id=venue_order_id,
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                state=OrderState.NEW,
                quantity=Decimal("0"),
                executed_qty=Decimal("0"),
                price=None,
                transact_time=0,
            )
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

    # -- private helpers ------------------------------------------------------

    def _ack_from_response(
        self, client_order_id: str, response: dict[str, Any]
    ) -> OrderAck:
        fills = self._fills_from_trades(response)
        filled_qty = _dec(response.get("filled"))
        status = str(response.get("status", "open"))
        state = _map_state(status, filled_qty)

        return OrderAck(
            client_order_id=str(response.get("clientOrderId", client_order_id)),
            venue_order_id=str(response.get("id", "")),
            symbol=str(response.get("symbol", "")),
            side=OrderSide(str(response.get("side", "buy"))),
            order_type=OrderType(str(response.get("type", "limit"))),
            state=state,
            quantity=_dec(response.get("amount")),
            price=_dec(response.get("price")) if response.get("price") else None,
            transact_time=int(response.get("timestamp", 0)),
            fills=tuple(fills),
        )

    def _snapshot_from_response(self, response: dict[str, Any]) -> OrderSnapshot:
        fills = self._fills_from_trades(response)
        filled_qty = _dec(response.get("filled"))
        status = str(response.get("status", "open"))
        state = _map_state(status, filled_qty)

        return OrderSnapshot(
            client_order_id=str(response.get("clientOrderId", "")),
            venue_order_id=str(response.get("id", "")),
            symbol=str(response.get("symbol", "")),
            side=OrderSide(str(response.get("side", "buy"))),
            order_type=OrderType(str(response.get("type", "limit"))),
            state=state,
            quantity=_dec(response.get("amount")),
            executed_qty=filled_qty,
            price=_dec(response.get("price")) if response.get("price") else None,
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
