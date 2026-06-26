class ExecutionError(Exception):
    """Base execution error."""


class ExecutionConfigError(ExecutionError):
    """Invalid configuration (missing keys, unknown mode)."""


class OrderRejectedError(ExecutionError):
    """Order rejected by exchange."""

    def __init__(self, reason: str, raw: dict | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw = raw or {}


class OrderTimeoutError(ExecutionError):
    """Order did not reach terminal state within expected window."""


class PartialFillError(ExecutionError):
    """Order partially filled beyond tolerance."""

    def __init__(self, filled: float, requested: float) -> None:
        super().__init__(f"partial fill {filled}/{requested}")
        self.filled = filled
        self.requested = requested
