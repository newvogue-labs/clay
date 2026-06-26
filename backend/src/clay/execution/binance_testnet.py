from __future__ import annotations

from typing import Any

import ccxt.async_support as ccxt

from clay.execution.exceptions import (
    ExecutionConfigError,
    OrderRejectedError,
    OrderTimeoutError,
    PartialFillError,
)
from clay.execution.models import Balance, OrderResult, OrderStatus, TradeFill


class BinanceTestnetExecutionClient:
    """Binance Spot testnet execution client (ccxt-based).

    Safety constraints:
    - ``mode`` must be ``testnet`` or ``dry_run``. ``live`` is rejected
      at instantiation (this slice does not introduce live path).
    - Credentials are loaded from env, never from TOML/repo.
    """

    SOURCE = "testnet"
    BASE_URL = "https://testnet.binance.vision"

    def __init__(self, *, api_key: str, api_secret: str, recv_window: int = 5000) -> None:
        if not api_key or not api_secret:
            raise ExecutionConfigError(
                "CLAY_BINANCE_TESTNET_API_KEY / CLAY_BINANCE_TESTNET_API_SECRET "
                "are required for testnet execution"
            )

        self._client = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "options": {
                    "defaultType": "spot",
                    "adjustForTimeDifference": True,
                    "recvWindow": recv_window,
                },
            }
        )
        self._client.set_sandbox_mode(True)
        self._client.urls["api"] = self.BASE_URL

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
        params: dict[str, Any] = {"newClientOrderId": client_order_id} if client_order_id else {}
        try:
            response = await self._client.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=quantity,
                price=price,
                params={**params, "timeInForce": time_in_force, "stopPrice": stop_price}
                if stop_price
                else {**params, "timeInForce": time_in_force},
            )
        except ccxt.InsufficientFunds as exc:
            raise OrderRejectedError("insufficient funds", raw=getattr(exc, "args", {})) from exc
        except ccxt.InvalidOrder as exc:
            raise OrderRejectedError("invalid order", raw={"msg": str(exc)}) from exc
        except ccxt.NetworkError as exc:
            raise OrderTimeoutError(f"network error: {exc}") from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc), raw={"msg": str(exc)}) from exc

        client_order_id = response.get("clientOrderId") or client_order_id or ""
        fills = [
            TradeFill(
                trade_id=str(fill.get("id", "")),
                order_id=str(response.get("id", "")),
                symbol=symbol,
                side=side,
                quantity=float(fill.get("amount", 0.0)),
                price=float(fill.get("price", 0.0)),
                commission=float(fill.get("commission", 0.0)),
                commission_asset=str(fill.get("commissionAsset", "")),
                transact_time=int(fill.get("timestamp", 0)),
            )
            for fill in response.get("trades", [])
        ]

        result = OrderResult(
            client_order_id=client_order_id,
            exchange_order_id=str(response.get("id", "")),
            symbol=symbol,
            side=side,
            quantity=float(response.get("amount", quantity)),
            order_type=order_type,
            status=response.get("status", ""),
            transact_time=int(response.get("timestamp", 0)),
            price=float(response.get("price", 0.0)) if response.get("price") else None,
            stop_price=float(response.get("stopPrice", 0.0)) if response.get("stopPrice") else None,
            fills=fills,
        )

        executed = float(response.get("filled", 0.0))
        if executed > 0 and executed < quantity:
            raise PartialFillError(filled=executed, requested=quantity)

        return result

    async def cancel_order(self, symbol: str, order_id: str) -> Any:
        try:
            response = await self._client.cancel_order(symbol=symbol, order_id=order_id)
        except ccxt.OrderNotFound:
            return {"status": "not_found", "order_id": order_id, "symbol": symbol}
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc), raw={"msg": str(exc)}) from exc
        return response

    async def get_order_status(self, symbol: str, order_id: str) -> OrderStatus:
        try:
            response = await self._client.fetch_order(order_id=order_id, symbol=symbol)
        except ccxt.OrderNotFound:
            return OrderStatus(
                client_order_id=str(response.get("clientOrderId", "")),
                exchange_order_id=order_id,
                symbol=symbol,
                side=str(response.get("side", "")),
                order_type=str(response.get("type", "")),
                status="not_found",
                quantity=float(response.get("amount", 0.0)),
                executed_qty=float(response.get("filled", 0.0)),
                price=float(response.get("price", 0.0)) if response.get("price") else None,
                stop_price=float(response.get("stopPrice", 0.0)) if response.get("stopPrice") else None,
                transact_time=int(response.get("timestamp", 0)),
            )
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc), raw={"msg": str(exc)}) from exc
        return self._map_order_status(response)

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderStatus]:
        try:
            orders = await self._client.fetch_open_orders(symbol=symbol)
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc), raw={"msg": str(exc)}) from exc
        return [self._map_order_status(o) for o in orders]

    async def get_balances(self) -> list[Balance]:
        try:
            response = await self._client.fetch_balance()
        except ccxt.AuthenticationError as exc:
            raise ExecutionConfigError("binance auth failed",) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc), raw={"msg": str(exc)}) from exc

        balances: list[Balance] = []
        total: dict[str, Any] = response.get("total", {})
        free: dict[str, Any] = response.get("free", {})
        used: dict[str, Any] = response.get("used", {})
        for asset, t in total.items():
            balances.append(
                Balance(
                    asset=asset,
                    free=float(free.get(asset, 0.0)),
                    locked=float(used.get(asset, 0.0)),
                    total=float(t),
                )
            )
        return balances

    async def get_recent_trades(self, symbol: str, *, limit: int = 500) -> list[TradeFill]:
        try:
            trades = await self._client.fetch_my_trades(symbol=symbol, limit=limit)
        except ccxt.AuthenticationError as exc:
            raise ExecutionConfigError("binance auth failed",) from exc
        except ccxt.ExchangeError as exc:
            raise OrderRejectedError(str(exc), raw={"msg": str(exc)}) from exc

        return [
            TradeFill(
                trade_id=str(t.get("id", "")),
                order_id=str(t.get("order", "")),
                symbol=symbol,
                side=str(t.get("side", "")),
                quantity=float(t.get("amount", 0.0)),
                price=float(t.get("price", 0.0)),
                commission=float(t.get("fee", {}).get("cost", 0.0)),
                commission_asset=str(t.get("fee", {}).get("currency", "")),
                transact_time=int(t.get("timestamp", 0)),
            )
            for t in trades
        ]

    async def close(self) -> None:
        await self._client.close()

    def _map_order_status(self, response: dict[str, Any]) -> OrderStatus:
        return OrderStatus(
            client_order_id=str(response.get("clientOrderId", "")),
            exchange_order_id=str(response.get("id", "")),
            symbol=str(response.get("symbol", "")),
            side=str(response.get("side", "")),
            order_type=str(response.get("type", "")),
            status=str(response.get("status", "")),
            quantity=float(response.get("amount", 0.0)),
            executed_qty=float(response.get("filled", 0.0)),
            price=float(response.get("price", 0.0)) if response.get("price") else None,
            stop_price=float(response.get("stopPrice", 0.0)) if response.get("stopPrice") else None,
            transact_time=int(response.get("timestamp", 0)),
        )


class DryRunExecutionClient:
    """No-op execution client for dry-run mode.

    Returns successful empty results without contacting the exchange.
    """

    SOURCE = "dry_run"

    async def place_order(self, *args: Any, **kwargs: Any) -> OrderResult:
        client_order_id = (kwargs.get("client_order_id") or "")
        return OrderResult(
            client_order_id=client_order_id,
            exchange_order_id="",
            symbol=kwargs.get("symbol", args[0] if args else ""),
            side=kwargs.get("side", args[1] if len(args) > 1 else ""),
            quantity=float(kwargs.get("quantity", args[2] if len(args) > 2 else 0.0)),
            order_type=kwargs.get("order_type", args[3] if len(args) > 3 else "MARKET"),
            status="dry_run",
            transact_time=0,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, str]:
        return {"status": "dry_run", "order_id": order_id, "symbol": symbol}

    async def get_order_status(self, symbol: str, order_id: str) -> OrderStatus:
        return OrderStatus(
            client_order_id="",
            exchange_order_id=order_id,
            symbol=symbol,
            side="",
            order_type="",
            status="dry_run",
            quantity=0.0,
            executed_qty=0.0,
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderStatus]:
        return []

    async def get_balances(self) -> list[Balance]:
        return []

    async def get_recent_trades(self, symbol: str, *, limit: int = 500) -> list[TradeFill]:
        return []

    async def close(self) -> None:
        return None


class NotImplementedLiveClient:
    """Placeholder for live execution.

    ``live`` mode is intentionally not implemented in this slice.
    """

    SOURCE = "live"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ExecutionConfigError(
            "Live execution is not implemented yet. "
            "Switch to testnet or dry_run."
        )

    async def place_order(self, *args: Any, **kwargs: Any) -> OrderResult:
        raise ExecutionConfigError("Live execution is disabled")
