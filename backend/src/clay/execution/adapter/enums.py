"""Adapter-level enumerations for exchange execution (ADR-032).

All enums are ``StrEnum`` — str-comparable, serialisable, immutable.
"""

from enum import StrEnum


class Environment(StrEnum):
    """Deployment environment set once at adapter construction."""

    PRODUCTION = "production"
    TESTNET = "testnet"
    DEMO = "demo"
    PAPER = "paper"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderState(StrEnum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PrecisionMode(StrEnum):
    TICK_SIZE = "tick_size"
    SIGNIFICANT_DIGITS = "significant_digits"
    DECIMAL_PLACES = "decimal_places"
