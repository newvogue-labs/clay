"""Tests for adapter error hierarchy and is_retryable."""

from __future__ import annotations

import pytest

from clay.execution.adapter.errors import (
    AdapterError,
    AmbiguousExecutionError,
    ConfigError,
    InsufficientFundsError,
    InvalidOrderError,
    OrderRejectedError,
    TransientAdapterError,
    is_retryable,
)


class TestHierarchy:
    def test_base_is_exception(self) -> None:
        assert issubclass(AdapterError, Exception)

    @pytest.mark.parametrize(
        "exc_cls",
        [
            TransientAdapterError,
            OrderRejectedError,
            InsufficientFundsError,
            InvalidOrderError,
            ConfigError,
            AmbiguousExecutionError,
        ],
    )
    def test_subclass_of_adapter_error(self, exc_cls: type[Exception]) -> None:
        assert issubclass(exc_cls, AdapterError)

    def test_order_rejected_has_reason(self) -> None:
        exc = OrderRejectedError("bad price")
        assert exc.reason == "bad price"
        assert str(exc) == "bad price"


class TestIsRetryable:
    def test_transient_true(self) -> None:
        assert is_retryable(TransientAdapterError("timeout")) is True

    @pytest.mark.parametrize(
        "exc",
        [
            OrderRejectedError("reason"),
            InsufficientFundsError("no funds"),
            InvalidOrderError("bad qty"),
            ConfigError("missing key"),
            AmbiguousExecutionError("state unknown"),
            AdapterError("base"),
        ],
    )
    def test_non_transient_false(self, exc: Exception) -> None:
        assert is_retryable(exc) is False

    def test_non_adapter_exception_false(self) -> None:
        assert is_retryable(ValueError("boom")) is False
