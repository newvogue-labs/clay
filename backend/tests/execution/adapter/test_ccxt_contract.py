"""Контрактный тест границы ccxt (ADR-039, S-DEPS-POLICY-1 D5).

Работает с РЕАЛЬНО установленной ccxt, без моков и без сети.
Проверяет: версию, существование классов交易所, методов на экземпляре,
и полный набор ловимых исключений.

Форма market-structure (опциональность limits.*.max, D-23) офлайн не
проверяется — она покрыта live-дриллом на demo.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
import ccxt
import pytest

# ── Версия из pyproject (пин) ──────────────────────────────────────────

_PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def _pinned_ccxt_version() -> str:
    """Извлечь ==X.Y.Z для ccxt из pyproject.toml."""
    with open(_PYPROJECT, "rb") as f:
        data = tomllib.load(f)
    for group in (
        data.get("project", {}).get("dependencies", []),
        data.get("dependency-groups", {}).get("dev", []) or [],
    ):
        for raw in group:
            if raw.startswith("ccxt=="):
                return raw[len("ccxt==") :]
    pytest.fail("ccxt==X.Y.Z не найден в pyproject.toml")


# ── Тесты ──────────────────────────────────────────────────────────────


class TestCcxtContract:
    """Контракт на границе Clay ↔ ccxt (ADR-039)."""

    def test_version_matches_pinned(self) -> None:
        """ccxt.__version__ должен совпадать с пином в pyproject."""
        expected = _pinned_ccxt_version()
        assert ccxt.__version__ == expected, (
            f"ccxt.__version__={ccxt.__version__!r}, pyproject пин={expected!r}"
        )

    def test_async_exchange_classes_exist(self) -> None:
        """Классы交易所, которые мы строим, должны существовать."""
        assert hasattr(ccxt.async_support, "binance"), (  # type: ignore[reportAttributeAccessIssue]
            "ccxt.async_support.binance не найден"
        )
        assert hasattr(ccxt.async_support, "bybit"), (  # type: ignore[reportAttributeAccessIssue]
            "ccxt.async_support.bybit не найден"
        )

    def test_bybit_has_sandbox_and_demo_methods(self) -> None:
        """На экземпляре bybit вызываемы set_sandbox_mode и enable_demo_trading."""
        exchange = ccxt.async_support.bybit({"enableRateLimit": True})  # type: ignore[reportAttributeAccessIssue]
        try:
            assert callable(getattr(exchange, "set_sandbox_mode", None)), (
                "bybit.set_sandbox_mode не вызываем"
            )
            assert callable(getattr(exchange, "enable_demo_trading", None)), (
                "bybit.enable_demo_trading не вызываем"
            )
        finally:
            # async close — но не await (тест синхронный, просто hasattr/callable)
            pass

    def test_binance_has_sandbox_and_demo_methods(self) -> None:
        """На экземпляре binance вызываемы set_sandbox_mode и enable_demo_trading."""
        exchange = ccxt.async_support.binance({"enableRateLimit": True})  # type: ignore[reportAttributeAccessIssue]
        try:
            assert callable(getattr(exchange, "set_sandbox_mode", None)), (
                "binance.set_sandbox_mode не вызываем"
            )
            assert callable(getattr(exchange, "enable_demo_trading", None)), (
                "binance.enable_demo_trading не вызываем"
            )
        finally:
            pass

    def test_exceptions_exist(self) -> None:
        """Все 6 исключений ccxt, которые мы ловим в адаптерах, должны существовать.

        Ловим в: ccxt_base.place_order, cancel_order, get_order,
        get_open_orders, reconcile_orders, get_balances, get_my_trades;
        bybit.get_market_rules; binance.get_market_rules.
        """
        expected = (
            "ExchangeError",
            "NetworkError",
            "AuthenticationError",
            "InvalidOrder",
            "InsufficientFunds",
            "OrderNotFound",
        )
        missing: list[str] = []
        for name in expected:
            if not hasattr(ccxt, name):
                missing.append(name)
        assert not missing, (
            f"ccxt-исключения не найдены: {missing}. "
            "Обнови список в тесте или проверь версию ccxt."
        )

    def test_exception_hierarchy(self) -> None:
        """Иерархия наследования не изменилась — базовый класс BaseError."""
        assert issubclass(ccxt.ExchangeError, ccxt.BaseError)
        assert issubclass(ccxt.NetworkError, ccxt.BaseError)
        assert issubclass(ccxt.AuthenticationError, ccxt.ExchangeError)
        assert issubclass(ccxt.InvalidOrder, ccxt.ExchangeError)
        assert issubclass(ccxt.InsufficientFunds, ccxt.ExchangeError)
        assert issubclass(ccxt.OrderNotFound, ccxt.InvalidOrder)
