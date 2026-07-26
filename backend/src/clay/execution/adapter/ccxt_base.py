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

Fail-closed env routing:
- ``_apply_sandbox_routing()`` handles TESTNET/PRODUCTION for adapters
  without demo mode.  Demo-capable adapters (Bybit) override ``__init__``.
"""

from __future__ import annotations

import logging
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
    CancelResult,
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

logger = logging.getLogger(__name__)


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
        _apply_sandbox_routing(self._client, environment)

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
                    f"duplicate clientOrderId: order may already exist, "
                    f"reconcile required (cid={req.client_order_id!r}); "
                    f"venue error: {exc}"
                ) from exc
            raise InvalidOrderError(str(exc)) from exc
        except ccxt.NetworkError as exc:
            raise AmbiguousExecutionError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            if self._is_duplicate_cid(exc):
                raise AmbiguousExecutionError(
                    f"duplicate clientOrderId: order may already exist, "
                    f"reconcile required (cid={req.client_order_id!r}); "
                    f"venue error: {exc}"
                ) from exc
            raise OrderRejectedError(str(exc)) from exc

        try:
            return self._ack_from_response(
                req.client_order_id,
                cast("dict[str, Any]", response),
                requested=req,
            )
        except Exception as exc:
            resp_dict = cast("dict[str, Any]", response)
            logger.warning(
                "clay.place_order: response parse failed after successful create_order "
                "(keys=%s, types=%s) — order may exist, reconcile required (cid=%s)",
                list(resp_dict.keys()),
                {k: type(v).__name__ for k, v in resp_dict.items()},
                req.client_order_id,
            )
            raise AmbiguousExecutionError(
                f"order may have been placed but response could not be parsed "
                f"(reconcile required, cid={req.client_order_id!r}): {exc}"
            ) from exc

    async def cancel_order(self, symbol: str, venue_order_id: str) -> CancelResult:
        try:
            await self._client.cancel_order(id=venue_order_id, symbol=symbol)
            return CancelResult.CANCELED
        except ccxt.OrderNotFound:
            return CancelResult.NOT_FOUND
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
        total: dict[str, Any] = response_dict.get("total") or {}
        free: dict[str, Any] = response_dict.get("free") or {}
        used: dict[str, Any] = response_dict.get("used") or {}
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

    async def get_my_trades(
        self, symbol: str, *, since: datetime | None = None, from_id: str | None = None
    ) -> list[Fill]:
        """Fetch account trades via ccxt ``fetch_my_trades``.

        Error-map mirrors read-ops: Network→Transient, Auth→Config, Exchange→Rejected.
        """
        params: dict[str, Any] = {}
        if from_id is not None:
            params["fromId"] = from_id
        since_ms = int(since.timestamp() * 1000) if since is not None else None
        try:
            trades = await self._client.fetch_my_trades(
                symbol=symbol, since=since_ms, params=params
            )
        except ccxt.NetworkError as exc:
            raise TransientAdapterError(str(exc)) from exc
        except ccxt.AuthenticationError as exc:
            raise ConfigError(str(exc)) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc)) from exc

        return [_fill_from_my_trade(cast("dict[str, Any]", t)) for t in trades]

    async def get_by_client_order_id(
        self, symbol: str, client_order_id: str
    ) -> OrderSnapshot | None:
        """Resolve order by client_order_id.

        Default implementation: search through open orders and reconcile history.
        Subclasses may override with venue-specific optimised paths.

        Taxonomy-aware fallback chain lives in
        ``ResilientExecutionAdapter`` when ``ReadFallbackPolicy.enabled``.
        """
        # Try open orders first (fast path)
        try:
            open_orders = await self.get_open_orders(symbol)
            for snap in open_orders:
                if snap.client_order_id == client_order_id:
                    return snap
        except Exception:
            pass

        # Fallback: search reconcile history (slower path)
        try:
            from datetime import timedelta

            since = datetime.now() - timedelta(hours=24)
            reconcile_orders = await self.reconcile_orders(symbol, since)
            for snap in reconcile_orders:
                if snap.client_order_id == client_order_id:
                    return snap
        except Exception:
            pass

        return None

    async def close(self) -> None:
        await self._client.close()

    # -- venue-specific hooks -------------------------------------------------

    def _extract_client_order_id(self, response: dict[str, Any]) -> str:
        """Venue-overridable: извлечь наш client_order_id из ccxt-ответа."""
        return _str_or_empty(response.get("clientOrderId"))

    @abstractmethod
    def _build_client(self, api_key: str, api_secret: str) -> ccxt.Exchange:
        """Create and return the venue-specific ccxt client."""
        ...

    @abstractmethod
    def _is_duplicate_cid(self, exc: Exception) -> bool:
        """Detect venue-specific duplicate clientOrderId error."""
        ...

    @abstractmethod
    def _build_order_params(self, req: OrderRequest) -> dict[str, Any]:
        """Venue-specific create_order params (client-order-id key, stop encoding)."""
        ...

    # -- private helpers ------------------------------------------------------

    def _ack_from_response(
        self,
        client_order_id: str,
        response: dict[str, Any],
        *,
        requested: OrderRequest | None = None,
    ) -> OrderAck:
        fills = self._fills_from_trades(response)
        filled_qty = _dec(response.get("filled"))
        status = _status_from_response(response)
        state = _map_state(status, filled_qty)

        price_raw = response.get("price")
        price = (
            _dec(price_raw) if price_raw is not None and _dec(price_raw) != 0 else None
        )

        # D-26: venue-truth priority; fill gaps from OrderRequest when venue omits fields.
        venue_amount = response.get("amount")
        quantity = (
            _dec(venue_amount)
            if venue_amount is not None
            else (requested.quantity if requested is not None else _dec(None))
        )

        if price is None and requested is not None and requested.price is not None:
            price = requested.price

        venue_side = response.get("side")
        side = (
            OrderSide(_str_or_empty(venue_side))
            if venue_side
            else (requested.side if requested is not None else OrderSide.BUY)
        )

        venue_type = response.get("type")
        order_type = (
            OrderType(_str_or_empty(venue_type))
            if venue_type
            else (requested.order_type if requested is not None else OrderType.LIMIT)
        )

        venue_symbol = response.get("symbol")
        symbol = (
            _str_or_empty(venue_symbol)
            if venue_symbol
            else (requested.symbol if requested is not None else "")
        )

        return OrderAck(
            client_order_id=self._extract_client_order_id(response) or client_order_id,
            venue_order_id=_str_or_empty(response.get("id")),
            symbol=symbol,
            side=side,
            order_type=order_type,
            state=state,
            quantity=quantity,
            price=price,
            transact_time=int(response.get("timestamp") or 0),
            fills=tuple(fills),
        )

    def _snapshot_from_response(self, response: dict[str, Any]) -> OrderSnapshot:
        fills = self._fills_from_trades(response)
        filled_qty = _dec(response.get("filled"))
        status = _status_from_response(response)
        state = _map_state(status, filled_qty)

        price_raw = response.get("price")
        price = (
            _dec(price_raw) if price_raw is not None and _dec(price_raw) != 0 else None
        )
        return OrderSnapshot(
            client_order_id=self._extract_client_order_id(response),
            venue_order_id=_str_or_empty(response.get("id")),
            symbol=_str_or_empty(response.get("symbol")),
            side=OrderSide(str(response.get("side") or "buy")),
            order_type=OrderType(str(response.get("type") or "limit")),
            state=state,
            quantity=_dec(response.get("amount")),
            executed_qty=filled_qty,
            price=price,
            transact_time=int(response.get("timestamp") or 0),
            fills=tuple(fills),
        )

    def _fills_from_trades(self, response: dict[str, Any]) -> list[Fill]:
        trades = response.get("trades") or []
        if not trades:
            return []
        symbol = _str_or_empty(response.get("symbol"))
        venue_order_id = _str_or_empty(response.get("id"))
        return [
            Fill(
                trade_id=_str_or_empty(fill.get("id")),
                venue_order_id=venue_order_id,
                symbol=symbol,
                side=OrderSide(str(fill.get("side") or "buy")),
                quantity=_dec(fill.get("amount")),
                price=_dec(fill.get("price")),
                commission=_dec(fill.get("commission")),
                commission_asset=_str_or_empty(fill.get("commissionAsset")),
                transact_time=int(fill.get("timestamp") or 0),
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


def _str_or_empty(value: object) -> str:
    """Coerce venue-provided value to ``str``; ``None`` and empty → ``""``."""
    if value is None:
        return ""
    return str(value)


def _dec_upper_bound(
    val: Any, *, field: str, symbol: str, venue: str
) -> Decimal | None:
    """Parse an upper-bound value from ccxt market data (D-23).

    Returns ``None`` when the venue does not publish the limit — this is
    the **documented sentinel** for "not applicable" (see ``MarketRules``).

    A zero or negative value is treated as missing-data (almost certainly
    wrong for a traded market) and logged as a warning.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    d = Decimal(s)
    if d <= 0:
        logger.warning(
            "clay.adapter: %s/%s %s returned non-positive upper bound %s "
            "— treating as absent (venue does not publish this limit)",
            venue,
            symbol,
            field,
            d,
        )
        return None
    return d


def _apply_sandbox_routing(client: Any, environment: Environment) -> None:
    """Fail-closed env routing для венью без demo-режима.

    TESTNET → sandbox; PRODUCTION → no-op; иначе (DEMO/PAPER/unknown) → ConfigError.
    Demo-capable венью (Bybit) переопределяют ``__init__`` и сюда не заходят.
    """
    if environment == Environment.TESTNET:
        client.set_sandbox_mode(True)
    elif environment == Environment.PRODUCTION:
        pass
    else:
        raise ConfigError(
            f"environment {environment.value!r} not supported by this adapter "
            f"(no demo/sandbox mapping)"
        )


def _fill_from_my_trade(trade: dict[str, Any]) -> Fill:
    """Map ccxt unified ``fetch_my_trades`` item → domain ``Fill``.

    Separate from ``_fills_from_trades`` (order-embedded shape).
    ``fee`` dict uses ``cost``/``currency`` keys.
    """
    fee = trade.get("fee") or {}
    return Fill(
        trade_id=_str_or_empty(trade.get("id")),
        venue_order_id=_str_or_empty(trade.get("order")),
        symbol=_str_or_empty(trade.get("symbol")),
        side=OrderSide(str(trade.get("side") or "buy")),
        quantity=_dec(trade.get("amount")),
        price=_dec(trade.get("price")),
        commission=_dec(fee.get("cost")),
        commission_asset=_str_or_empty(fee.get("currency")),
        transact_time=int(trade.get("timestamp") or 0),
    )


def _map_state(status: str, filled: Decimal) -> OrderState:
    """Map ccxt order status to domain ``OrderState``.

    ``open`` with ``filled > 0`` -> ``PARTIALLY_FILLED``.
    Unknown statuses map to ``UNKNOWN`` (not ``NEW``) — F-D12-2.
    """
    if status == "open":
        return OrderState.PARTIALLY_FILLED if filled > 0 else OrderState.NEW
    return _STATE_MAP.get(status, OrderState.UNKNOWN)


def _status_from_response(response: dict[str, Any]) -> str:
    """Extract status from ccxt response with None-safe semantics.

    Key absent → ``"open"`` (current default).
    Key present, value None or empty → ``""`` (maps to UNKNOWN via ``_map_state``).
    Key present, non-empty value → as-is.
    """
    if "status" not in response:
        return "open"
    return response["status"] or ""
