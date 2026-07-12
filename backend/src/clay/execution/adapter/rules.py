"""Market rules and capability overlays (ADR-032).

Frozen — once built for a symbol/market-type, never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from clay.execution.adapter.enums import OrderType, PrecisionMode, TimeInForce


@dataclass(frozen=True)
class MarketRules:
    """Venue-specific constraints for a single symbol.

    ``precision_mode`` controls how ``amount_step`` / ``price_tick``
    are interpreted by the quantizer.
    """

    min_amount: Decimal
    max_amount: Decimal
    min_price: Decimal
    max_price: Decimal
    min_notional: Decimal
    amount_step: Decimal
    price_tick: Decimal
    precision_mode: PrecisionMode
    supported_order_types: frozenset[OrderType]
    supported_tif: frozenset[TimeInForce]
