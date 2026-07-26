"""Собственный интерфейс над внешней ccxt-библиотекой (ADR-039 §1).

Протокол ``CcxtSpotClient`` задаёт контракт клиента биржи, который
ожидает ``CcxtExchangeAdapter``.  ``CcxtDemoCapableClient`` добавляет
``enable_demo_trading`` для венью с demo-режимом (Bybit).

Протокол существует **только** для статического контроля типов (pyright).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol


class CcxtSpotClient(Protocol):
    """Базовый контракт клиента биржи (ccxt async)."""

    async def create_order(
        self,
        symbol: str,
        type: Literal["limit", "market"],
        side: Literal["buy", "sell"],
        amount: float,
        price: str | float | int | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any: ...

    async def cancel_order(
        self, id: str, symbol: str | None = None, params: dict[str, Any] | None = None
    ) -> Any: ...

    async def fetch_order(
        self, id: str, symbol: str | None = None, params: dict[str, Any] | None = None
    ) -> Any: ...

    async def fetch_open_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any: ...

    async def fetch_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any: ...

    async def fetch_balance(self, params: dict[str, Any] | None = None) -> Any: ...

    async def fetch_my_trades(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any: ...

    async def load_markets(
        self, reload: bool = False, params: dict[str, Any] | None = None
    ) -> Any: ...

    async def close(self, clean_instance_data: bool = False) -> None: ...

    def set_sandbox_mode(self, enabled: bool, /) -> None: ...


class CcxtDemoCapableClient(CcxtSpotClient, Protocol):
    """Расширяет ``CcxtSpotClient`` для венью с demo-режимом (Bybit)."""

    def enable_demo_trading(self, enable: bool, /) -> None: ...
