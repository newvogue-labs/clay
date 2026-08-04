"""Tests for smoke_bybit_demo._compute_tier1_order and _compute_stop_order (pure, no network)."""

from __future__ import annotations

from decimal import Decimal

from scripts.smoke_bybit_demo import _compute_stop_order, _compute_tier1_order


class TestComputeTier1Order:
    def test_basic_case(self) -> None:
        """ref=64000, notional=10, factor=0.5, min_cost=5, min_amount=0.000048."""
        qty, price = _compute_tier1_order(
            ref_price=Decimal("64000"),
            notional_target=Decimal("10"),
            price_factor=Decimal("0.5"),
            min_cost=Decimal("5"),
            min_amount=Decimal("0.000048"),
        )
        assert price == Decimal("32000")
        assert qty * price >= Decimal("10")
        assert price < Decimal("64000")
        assert qty >= Decimal("0.000048")

    def test_large_min_amount_bumps_qty(self) -> None:
        """min_amount=1 forces qty up, notional stays >= floor_cost."""
        qty, price = _compute_tier1_order(
            ref_price=Decimal("64000"),
            notional_target=Decimal("10"),
            price_factor=Decimal("0.5"),
            min_cost=Decimal("5"),
            min_amount=Decimal("1"),
        )
        assert qty >= Decimal("1")
        assert qty * price >= Decimal("5")

    def test_min_cost_exceeds_notional_target(self) -> None:
        """min_cost=50 > notional_target=10 → floor_cost=50, qty adjusted."""
        qty, price = _compute_tier1_order(
            ref_price=Decimal("64000"),
            notional_target=Decimal("10"),
            price_factor=Decimal("0.5"),
            min_cost=Decimal("50"),
            min_amount=Decimal("0"),
        )
        assert qty * price >= Decimal("50")

    def test_price_factor_above_one(self) -> None:
        """factor>1 (BUY above market) — still produces valid params."""
        qty, price = _compute_tier1_order(
            ref_price=Decimal("100"),
            notional_target=Decimal("20"),
            price_factor=Decimal("1.5"),
            min_cost=Decimal("5"),
            min_amount=Decimal("0"),
        )
        assert price == Decimal("150")
        assert qty * price >= Decimal("20")

    def test_zero_min_amount_and_min_cost(self) -> None:
        """Zero floors — qty derived purely from notional_target / price."""
        qty, price = _compute_tier1_order(
            ref_price=Decimal("1000"),
            notional_target=Decimal("5"),
            price_factor=Decimal("0.5"),
            min_cost=Decimal("0"),
            min_amount=Decimal("0"),
        )
        assert price == Decimal("500")
        assert qty * price >= Decimal("5")


class TestComputeStopOrder:
    def test_untriggered_above_market(self) -> None:
        """ref=64000 → trigger=80000 (above market), limit slightly above trigger."""
        trigger, lim, qty = _compute_stop_order(
            ref_price=Decimal("64000"),
            notional_target=Decimal("10"),
            min_cost=Decimal("5"),
            min_amount=Decimal("0"),
        )
        # trigger > ref → untriggered
        assert trigger > Decimal("64000")
        assert trigger == Decimal("80000")
        # limit > trigger
        assert lim > trigger
        assert lim == Decimal("80080")
        # notional >= target
        assert qty * lim >= Decimal("10")

    def test_min_amount_bump(self) -> None:
        """min_amount=0.001 forces qty up."""
        trigger, lim, qty = _compute_stop_order(
            ref_price=Decimal("64000"),
            notional_target=Decimal("10"),
            min_cost=Decimal("5"),
            min_amount=Decimal("0.001"),
        )
        assert qty >= Decimal("0.001")
        assert qty * lim >= Decimal("5")

    def test_min_cost_floor(self) -> None:
        """min_cost=50 > notional_target=10 → floor_cost=50."""
        trigger, lim, qty = _compute_stop_order(
            ref_price=Decimal("64000"),
            notional_target=Decimal("10"),
            min_cost=Decimal("50"),
            min_amount=Decimal("0"),
        )
        assert qty * lim >= Decimal("50")

    def test_custom_factors(self) -> None:
        """Custom trigger_factor and limit_slip."""
        trigger, lim, qty = _compute_stop_order(
            ref_price=Decimal("3500"),
            notional_target=Decimal("10"),
            min_cost=Decimal("5"),
            min_amount=Decimal("0"),
            trigger_factor=Decimal("1.50"),
            limit_slip=Decimal("1.005"),
        )
        assert trigger == Decimal("5250")
        assert lim == Decimal("5276.25")
        assert qty * lim >= Decimal("10")
