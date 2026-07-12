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


def is_retryable(exc: BaseException) -> bool:
    """Return ``True`` only for transient / retryable adapter errors."""
    return isinstance(exc, TransientAdapterError)
