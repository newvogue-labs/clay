"""Bybit Spot concrete adapter (ccxt-based, S-ADAPT-5b-2b).

Implements ``ExchangeAdapter`` for Bybit Spot (testnet + production).
ccxt client can be injected for testing; ``None`` -> real ``ccxt.bybit``.

Error-map (safety-critical):
- ``place_order``: ``NetworkError`` -> ``AmbiguousExecutionError`` (not transient).
- ``place_order``: duplicate clientOrderId (12141/170141) -> ``AmbiguousExecutionError``
  (reconcile-before-retry, covers both spot ``BadRequest`` and linear
  ``InvalidOrder`` paths).
- Read methods: ``NetworkError`` -> ``TransientAdapterError`` (retry-safe).

Bybit-specific notes:
- ``defaultType='spot'`` must be set explicitly (default is ``'swap'``).
- ``enable_demo_trading`` and ``set_sandbox_mode`` are mutually exclusive.
- ``limits.price`` is ``None`` for spot markets (price validation guard).
- STOP_LIMIT on Bybit spot = ``orderFilter='StopOrder'`` + ``triggerPrice``,
  not a separate order type -> ``supported_order_types`` omits STOP_LIMIT.
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
    """Detect Bybit duplicate clientOrderId error (codes 12141 / 170141).

    Spot returns ``12141`` -> ``BadRequest``, linear returns ``170141`` ->
    ``InvalidOrder``.  We catch both via message inspection so that the
    upstream ``AmbiguousExecutionError`` path (reconcile-before-retry)
    fires regardless of market type.
    """
    s = str(exc)
    return "12141" in s or "170141" in s


class BybitExecutionAdapter(CcxtExchangeAdapter):
    """Bybit Spot adapter implementing ``ExchangeAdapter``.

    Constructor:
        ``environment`` -- deployment target (``TESTNET`` / ``DEMO`` / ``PRODUCTION``).
        ``api_key`` / ``api_secret`` -- from env, never from TOML/repo.
        ``client`` -- optional injected ccxt instance for testing.

    Environment routing:
        TESTNET     → ``set_sandbox_mode(True)`` (api-testnet.bybit.com)
        DEMO        → ``enable_demo_trading(True)`` (api-demo.bybit.com)
        PRODUCTION  → no-op (live endpoint)
        Other       → ``ConfigError`` (fail-closed)
    """

    supported_order_types: ClassVar[frozenset[OrderType]] = frozenset(
        {OrderType.MARKET, OrderType.LIMIT}
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
        client: ccxt.bybit | Any | None = None,
    ) -> None:
        self.environment = environment
        if client is not None:
            self._client = client
        else:
            if not api_key or not api_secret:
                raise ConfigError(
                    "api_key and api_secret are required when client is not injected"
                )
            self._client = ccxt.bybit(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "options": {
                        "defaultType": "spot",
                    },
                    "timeout": 30000,
                }
            )

        if environment == Environment.TESTNET:
            self._client.set_sandbox_mode(True)
        elif environment == Environment.DEMO:
            self._client.enable_demo_trading(True)
        elif environment == Environment.PRODUCTION:
            pass
        else:
            raise ConfigError(
                f"environment {environment.value!r} not supported by Bybit adapter"
            )

    # -- venue-specific hooks -------------------------------------------------

    def _build_client(self, api_key: str, api_secret: str) -> ccxt.Exchange:
        """Create ccxt.bybit with Spot-specific options."""
        return ccxt.bybit(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "options": {
                    "defaultType": "spot",
                },
                "timeout": 30000,
            }
        )

    def _is_duplicate_cid(self, exc: Exception) -> bool:
        return _is_duplicate_cid(exc)

    def _build_order_params(self, req: OrderRequest) -> dict[str, Any]:
        """Bybit spot: ``clientOrderId`` -> ``orderLinkId`` (ccxt unified).

        Bybit spot has no separate STOP_LIMIT order type; stop orders use
        ``orderFilter='StopOrder'`` + ``triggerPrice``, so ``stopPrice``
        is NOT added here.
        """
        return {"clientOrderId": req.client_order_id}

    def _extract_client_order_id(self, response: dict[str, Any]) -> str:
        """Bybit:优先 info.orderLinkId, fallback на unified clientOrderId (ccxt #23260)."""
        info = response.get("info") or {}
        return str(info.get("orderLinkId") or response.get("clientOrderId", "") or "")

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

        # Bybit spot: ccxt-normalized market fields.
        # limits.price == None for spot (L3 confirmed).
        precision: dict[str, Any] = market.get("precision", {})
        limits: dict[str, Any] = market.get("limits", {})

        amount_step = _dec(precision.get("amount"))
        price_tick = _dec(precision.get("price"))

        cost_limits: dict[str, Any] = limits.get("cost", {})
        min_notional = _dec(cost_limits.get("min"))

        # limits.price is None for Bybit spot — guard, do not raise.
        price_limits: dict[str, Any] = limits.get("price", {})
        min_price = _dec(price_limits.get("min"))
        max_price = _dec(price_limits.get("max"))

        # amount limits
        amount_limits: dict[str, Any] = limits.get("amount", {})
        min_amount = _dec(amount_limits.get("min"))
        max_amount = _dec(amount_limits.get("max"))

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
