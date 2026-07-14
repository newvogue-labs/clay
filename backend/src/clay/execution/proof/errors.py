"""Исключения Execution Proof-Gate."""


class ProofGateError(Exception):
    """Базовое исключение гейта."""


class ProofGateDeniedError(ProofGateError):
    """Ордер отклонён гейтом (DENY decision). → 422."""

    def __init__(self, reason_codes: tuple[str, ...]) -> None:
        self.reason_codes = reason_codes
        super().__init__(f"execution denied: {', '.join(reason_codes)}")


class ProofGatePersistError(ProofGateError):
    """Persist decision-record не удался → fail-closed, ордер НЕ уходит. → 503."""
