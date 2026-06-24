"""Tests for ``MarketDataClient`` Protocol conformance (E1).

The Protocol is the exchange-agnostic contract — every exchange
adapter must conform structurally (duck-typed). These tests pin
the conformance for ``BinanceSpotClient`` and verify the runtime
type-checker accepts it via ``runtime_checkable``.

Why ``runtime_checkable`` is enough for E1:

* ``isinstance(client, MarketDataClient)`` lets us assert the
  structural contract at module import time (cheap contract pin).
* The Protocol itself is the source of truth for pyright/mypy
  static checks.
* A second exchange (Bybit, E4) will get the same conformance
  test — the test file is the seam for that future addition.
"""

from __future__ import annotations


from clay.ingestion.market.binance_client import BinanceSpotClient
from clay.ingestion.market.bybit_client import BybitClient
from clay.ingestion.market.protocol import MarketDataClient


def test_binance_spot_client_conforms_to_market_data_client() -> None:
    """``BinanceSpotClient`` structurally conforms to ``MarketDataClient``.

    The Protocol requires ``source: str`` and ``fetch_klines(...)``.
    ``set_http_client`` is provided as a default no-op in the
    Protocol; ``BinanceSpotClient`` has its own implementation
    (lifespan-injection path).
    """
    client = BinanceSpotClient()
    assert isinstance(client, MarketDataClient)
    assert client.source == "binance_spot"


def test_binance_spot_client_source_is_overridable() -> None:
    """``source`` is an instance attribute — the constructor overrides the default."""
    custom = BinanceSpotClient(source="test_fixture")
    assert custom.source == "test_fixture"
    assert isinstance(custom, MarketDataClient)


def test_bybit_client_conforms_to_market_data_client() -> None:
    """E4: ``BybitClient`` structurally conforms to ``MarketDataClient``."""
    client = BybitClient()
    assert isinstance(client, MarketDataClient)
    assert client.source == "bybit_spot"


def test_bybit_client_source_is_overridable() -> None:
    """E4: BybitClient source is overridable via constructor."""
    custom = BybitClient(source="test_bybit")
    assert custom.source == "test_bybit"
    assert isinstance(custom, MarketDataClient)
