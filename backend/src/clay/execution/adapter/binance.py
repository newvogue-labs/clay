"""Binance Spot concrete adapter (ccxt-based, S-ADAPT-2).

Implements ``ExchangeAdapter`` for Binance Spot (testnet + production).
ccxt client can be injected for testing; ``None`` -> real ``ccxt.binance``.

Error-map (safety-critical):
- ``place_order``: ``NetworkError`` -> ``AmbiguousExecutionError`` (not transient).
- ``place_order``: duplicate clientOrderId (-4116) -> ``AmbiguousExecutionError``
  (reconcile-before-retry, covers both spot ``ExchangeError`` and futures
  ``InvalidOrder`` paths).
- Read methods: ``NetworkError`` -> ``TransientAdapterError`` (retry-safe).
"""

from __future__ import annotations

from typing import Any, ClassVar

import ccxt.async_support as ccxt

from clay.execution.adapter.ccxt_base import (
    CcxtExchangeAdapter,
    _dec,
)
from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    Environment,
    OrderType,
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.errors import (
    ConfigError,
    InvalidOrderError,
    OrderRejectedError,
    TransientAdapterError,
)
from clay.execution.adapter.rules import MarketRules


def _is_duplicate_cid(exc: Exception) -> bool:
    """Detect Binance duplicate clientOrderId error (code -4116).

    On Binance Spot ccxt maps ``-4116`` -> ``ExchangeError`` (not
    ``InvalidOrder``), while futures maps it -> ``InvalidOrder``.  We
    catch both via message inspection so that the upstream
    ``AmbiguousExecutionError`` path (reconcile-before-retry) fires
    regardless of venue type.
    """
    s = str(exc)
    return "-4116" in s or "DUPLICATED_CLIENT_ORDER_ID" in s


class BinanceExecutionAdapter(CcxtExchangeAdapter):
    """Binance Spot adapter implementing ``ExchangeAdapter``.

    Constructor:
        ``environment`` -- deployment target (``TESTNET`` / ``PRODUCTION``).
        ``api_key`` / ``api_secret`` -- from env, never from TOML/repo.
        ``client`` -- optional injected ccxt instance for testing.
    """

    supported_order_types: ClassVar[frozenset[OrderType]] = frozenset(
        {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
    )
    supported_tif: ClassVar[frozenset[TimeInForce]] = frozenset(
        {TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}
    )

    def __init__(
        self,
        environment: Environment,
        *,
        api_key: str = "",
        api_secret: str = "",
        client: ccxt.binance | Any | None = None,
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

    # -- venue-specific hooks -------------------------------------------------

    def _build_client(self, api_key: str, api_secret: str) -> ccxt.Exchange:
        """Create ccxt.binance with Spot-specific options."""
        return ccxt.binance(
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

    def _is_duplicate_cid(self, exc: Exception) -> bool:
        return _is_duplicate_cid(exc)

    def _build_order_params(self, req: OrderRequest) -> dict[str, Any]:
        params: dict[str, Any] = {"newClientOrderId": req.client_order_id}
        if req.stop_price is not None:
            params["stopPrice"] = str(req.stop_price)
        return params

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
        if not notional_filter:
            notional_filter = next(
                (f for f in filters if f.get("filterType") == "MIN_NOTIONAL"), {}
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
            supported_order_types=self.supported_order_types,
            supported_tif=self.supported_tif,
        )
