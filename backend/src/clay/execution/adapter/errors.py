"""Adapter error taxonomy (ADR-032).

Separate from ``execution/exceptions.py`` — adapter-specific,
domain-oriented, no float leakage.
"""


class AdapterError(Exception):
    """Base error for the adapter layer."""


class TransientAdapterError(AdapterError):
    """Retryable / transient failure (network, rate-limit, 5xx)."""


class OrderRejectedError(AdapterError):
    """Venue rejected the order."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InsufficientFundsError(AdapterError):
    """Account has insufficient balance."""


class InvalidOrderError(AdapterError):
    """Order failed validation against market rules."""


class ConfigError(AdapterError):
    """Invalid adapter configuration."""


class AmbiguousExecutionError(AdapterError):
    """Terminal state unknown after submission timeout.

    Not retryable — requires reconcile.
    """


class CircuitOpenError(TransientAdapterError):
    """Circuit breaker is open — venue degraded.

    Subclass of ``TransientAdapterError`` so ``is_retryable`` returns True.
    Raised BEFORE calling the inner operation (fast-fail) — does NOT count
    as an inner failure for CB trip purposes.
    """


class OperationNotAllowedError(AdapterError):
    """Operation not allowed by safety policy.

    For example, hitting a per-order notional hard cap.
    """


class OrderNotFoundError(AdapterError):
    """Venue reports the order does not exist.

    Not retryable — the order was never placed or has been purged.
    """

    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
        venue_order_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.symbol = symbol
        self.venue_order_id = venue_order_id


def is_retryable(exc: BaseException) -> bool:
    """Return ``True`` only for transient / retryable adapter errors."""
    return isinstance(exc, TransientAdapterError)
