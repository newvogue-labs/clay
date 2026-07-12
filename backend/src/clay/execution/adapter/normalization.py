"""Pure domain functions: validate + quantize (ADR-032).

No I/O, no network, no float — sync only.
"""

from decimal import Decimal

from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import OrderType
from clay.execution.adapter.errors import InvalidOrderError
from clay.execution.adapter.rules import MarketRules


def validate_order(req: OrderRequest, rules: MarketRules) -> None:
    """Validate *req* against *rules*; raise on first violation."""

    if req.order_type not in rules.supported_order_types:
        raise InvalidOrderError(
            f"order_type {req.order_type!r} not supported; "
            f"allowed: {sorted(rules.supported_order_types)}"
        )

    if req.time_in_force not in rules.supported_tif:
        raise InvalidOrderError(
            f"time_in_force {req.time_in_force!r} not supported; "
            f"allowed: {sorted(rules.supported_tif)}"
        )

    if req.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and req.price is None:
        raise InvalidOrderError(f"{req.order_type} order requires a price")

    if req.quantity < rules.min_amount:
        raise InvalidOrderError(
            f"quantity {req.quantity} < min_amount {rules.min_amount}"
        )

    if req.quantity > rules.max_amount:
        raise InvalidOrderError(
            f"quantity {req.quantity} > max_amount {rules.max_amount}"
        )

    if req.price is not None:
        if req.price < rules.min_price:
            raise InvalidOrderError(f"price {req.price} < min_price {rules.min_price}")
        if req.price > rules.max_price:
            raise InvalidOrderError(f"price {req.price} > max_price {rules.max_price}")

    if req.price is not None:
        notional = req.quantity * req.price
        if notional < rules.min_notional:
            raise InvalidOrderError(
                f"notional {notional} < min_notional {rules.min_notional}"
            )


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    """Floor *value* to the nearest multiple of *step* (divide-floor-multiply)."""
    if step <= 0:
        return value
    return (value // step) * step


def _round_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    """Floor *value* to the nearest tick grid point.

    Uses divide-floor-multiply — correct for non-power-of-10 ticks
    (0.05, 0.25, 2.5) where ``Decimal.quantize`` silently misrounds.
    """
    if tick <= 0:
        return value
    return (value // tick) * tick


def _round_to_sig_digits(value: Decimal, step: Decimal) -> Decimal:
    """Floor *value* to the number of significant digits in *step*.

    Not yet implemented — no current venue requires SIGNIFICANT_DIGITS.
    Will be completed when a venue with this precision mode is added.
    """
    raise NotImplementedError(
        "SIGNIFICANT_DIGITS precision mode is not yet implemented"
    )


def quantize_order(req: OrderRequest, rules: MarketRules) -> OrderRequest:
    """Round *req* quantities to the venue grid.

    Returns a new frozen ``OrderRequest`` with quantized values.
    ``quantity`` is floored to avoid exceeding available balance;
    ``price``/``stop_price`` are floored to the tick grid.

    ``precision_mode`` controls quantity quantization:
    - ``TICK_SIZE`` / ``DECIMAL_PLACES``: floor to ``amount_step``.
    - ``SIGNIFICANT_DIGITS``: floor to N significant digits derived
      from ``amount_step``.
    """
    from clay.execution.adapter.enums import PrecisionMode

    if rules.precision_mode == PrecisionMode.SIGNIFICANT_DIGITS:
        quantized_qty = _round_to_sig_digits(req.quantity, rules.amount_step)
    else:
        quantized_qty = _floor_to_step(req.quantity, rules.amount_step)

    quantized_price = (
        _round_to_tick(req.price, rules.price_tick) if req.price is not None else None
    )
    quantized_stop = (
        _round_to_tick(req.stop_price, rules.price_tick)
        if req.stop_price is not None
        else None
    )

    if (
        quantized_qty != req.quantity
        or quantized_price != req.price
        or quantized_stop != req.stop_price
    ):
        return OrderRequest(
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            quantity=quantized_qty,
            time_in_force=req.time_in_force,
            client_order_id=req.client_order_id,
            price=quantized_price,
            stop_price=quantized_stop,
        )

    return req
