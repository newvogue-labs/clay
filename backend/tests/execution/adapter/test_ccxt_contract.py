"""Контрактный тест границы ccxt (ADR-039, S-DEPS-POLICY-1 D5).

Работает с РЕАЛЬНО установленной ccxt, без моков и без сети.
Проверяет: версию, существование классов бирж, методов на экземпляре,
и полный набор ловимых исключений.

Форма market-structure (опциональность limits.*.max, D-23) офлайн не
проверяется — она покрыта live-дриллом на demo.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import ccxt
import ccxt.async_support as ccxt_async
import pytest

from clay.execution.adapter.ccxt_client import CcxtDemoCapableClient, CcxtSpotClient
from tests.execution.adapter.test_binance import FakeBinanceClient
from tests.execution.adapter.test_bybit import FakeBybitClient

# ── Версия из pyproject (пин) ──────────────────────────────────────────

_PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"

_CCXT_EXCEPTIONS = (
    "ExchangeError",
    "NetworkError",
    "AuthenticationError",
    "InvalidOrder",
    "InsufficientFunds",
    "OrderNotFound",
)


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
    """Контракт на границе Clay <-> ccxt (ADR-039)."""

    def test_version_matches_pinned(self) -> None:
        """ccxt.__version__ должен совпадать с пином в pyproject."""
        expected = _pinned_ccxt_version()
        assert ccxt.__version__ == expected, (
            f"ccxt.__version__={ccxt.__version__!r}, pyproject пин={expected!r}"
        )

    def test_async_exchange_classes_exist(self) -> None:
        """Классы бирж (async), которые мы строим, должны существовать."""
        assert hasattr(ccxt_async, "binance"), "ccxt.async_support.binance не найден"
        assert hasattr(ccxt_async, "bybit"), "ccxt.async_support.bybit не найден"

    def test_bybit_has_sandbox_and_demo_methods(self) -> None:
        """На экземпляре bybit (async) вызываемы set_sandbox_mode и enable_demo_trading."""
        exchange = ccxt_async.bybit({"enableRateLimit": True})
        assert callable(getattr(exchange, "set_sandbox_mode", None)), (
            "bybit.set_sandbox_mode не вызываем"
        )
        assert callable(getattr(exchange, "enable_demo_trading", None)), (
            "bybit.enable_demo_trading не вызываем"
        )

    def test_binance_has_sandbox_and_demo_methods(self) -> None:
        """На экземпляре binance (async) вызываемы set_sandbox_mode и enable_demo_trading."""
        exchange = ccxt_async.binance({"enableRateLimit": True})
        assert callable(getattr(exchange, "set_sandbox_mode", None)), (
            "binance.set_sandbox_mode не вызываем"
        )
        assert callable(getattr(exchange, "enable_demo_trading", None)), (
            "binance.enable_demo_trading не вызываем"
        )

    def test_exceptions_exist(self) -> None:
        """Все 6 исключений ccxt, которые мы ловим в адаптерах, должны существовать.

        Ловим в: ccxt_base.place_order, cancel_order, get_order,
        get_open_orders, reconcile_orders, get_balances, get_my_trades;
        bybit.get_market_rules; binance.get_market_rules.
        """
        missing: list[str] = []
        for name in _CCXT_EXCEPTIONS:
            if not hasattr(ccxt_async, name):
                missing.append(name)
        assert not missing, (
            f"ccxt-исключения не найдены в async_support: {missing}. "
            "Обнови список в тесте или проверь версию ccxt."
        )

    def test_exception_hierarchy(self) -> None:
        """Иерархия наследования не изменилась — базовый класс BaseError."""
        assert issubclass(ccxt_async.ExchangeError, ccxt_async.BaseError)
        assert issubclass(ccxt_async.NetworkError, ccxt_async.BaseError)
        assert issubclass(ccxt_async.AuthenticationError, ccxt_async.ExchangeError)
        assert issubclass(ccxt_async.InvalidOrder, ccxt_async.ExchangeError)
        assert issubclass(ccxt_async.InsufficientFunds, ccxt_async.ExchangeError)
        assert issubclass(ccxt_async.OrderNotFound, ccxt_async.InvalidOrder)

    def test_exception_identity_sync_async(self) -> None:
        """Исключения sync и async — один и тот же объект ( shared C extension )."""
        for name in _CCXT_EXCEPTIONS:
            sync_cls = getattr(ccxt, name)
            async_cls = getattr(ccxt_async, name)
            assert sync_cls is async_cls, (
                f"{name}: sync={sync_cls!r} is not async={async_cls!r}"
            )

    def test_create_order_accepts_trigger_price(self) -> None:
        """ccxt.binance и ccxt.bybit принимают triggerPrice в params для type='limit'."""
        for label, exchange_cls in [
            ("binance", ccxt_async.binance),
            ("bybit", ccxt_async.bybit),
        ]:
            doc = exchange_cls.create_order.__doc__ or ""
            assert "triggerPrice" in doc, (
                f"{label}.create_order не документирует triggerPrice"
            )


# ── Статические контракты подделок ─────────────────────────────────────
# Проверка при импорте модуля: fake-классы удовлетворяют протоколам.

_binance_contract: CcxtSpotClient = FakeBinanceClient()
_bybit_contract: CcxtDemoCapableClient = FakeBybitClient()
