"""Unit-тесты для execution/proof — checker, reason-codes, decision-record.

Покрытие: каждый reason-code, happy ADMIT, off-by-default cap, fail-closed,
collect-all, детерминизм хешей.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest


from clay.execution.adapter.domain import BalanceSnapshot, OrderRequest, OrderSnapshot
from clay.execution.adapter.enums import (
    OrderSide,
    OrderState,
    OrderType,
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.rules import MarketRules
from clay.execution.proof.checker import admit
from clay.execution.proof.decision import Decision
from clay.execution.proof.reason_codes import ReasonCode
from clay.execution.proof.snapshot import (
    AccountSnapshot,
    FreshnessPolicy,
    MarketSnapshot,
    OpenOrdersSnapshot,
    SessionMode,
    SessionSnapshot,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

NOW = datetime.now(tz=timezone.utc)

DEFAULT_RULES = MarketRules(
    min_amount=Decimal("0.001"),
    max_amount=Decimal("1000"),
    min_price=Decimal("0.01"),
    max_price=Decimal("100000"),
    min_notional=Decimal("5"),
    amount_step=Decimal("0.001"),
    price_tick=Decimal("0.01"),
    precision_mode=PrecisionMode.DECIMAL_PLACES,
    supported_order_types=frozenset(
        {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
    ),
    supported_tif=frozenset({TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}),
)

DEFAULT_SNAPSHOT = MarketSnapshot(
    rules=DEFAULT_RULES,
    fetched_at=NOW,
    metadata_version="v1",
)

DEFAULT_POLICY = FreshnessPolicy(max_age_seconds=300)

DEFAULT_MAX_NOTIONAL = Decimal("10000")


def _make_request(**overrides: object) -> OrderRequest:
    defaults = dict(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        time_in_force=TimeInForce.GTC,
        client_order_id="test-001",
        price=Decimal("50000"),
    )
    defaults.update(overrides)  # type: ignore[arg-type]
    return OrderRequest(**defaults)  # type: ignore[call-overload]


# ── Happy path ────────────────────────────────────────────────────────────


class TestHappyPath:
    def test_admit_valid_limit(self) -> None:
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.ADMIT
        assert len(rec.reason_codes) == 0
        assert len(rec.invariant_results) == 12

    def test_admit_valid_market(self) -> None:
        req = _make_request(order_type=OrderType.MARKET, price=None)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),  # cap выключен → MARKET допустим
            now=NOW,
        )
        assert rec.decision == Decision.ADMIT

    def test_market_cap_active_denies(self) -> None:
        """MARKET + cap>0 → DENY [NOTIONAL_UNCOMPUTABLE] (fail-closed, S-LIVE-2 mirror)."""
        req = _make_request(order_type=OrderType.MARKET, price=None)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.NOTIONAL_UNCOMPUTABLE in rec.reason_codes

    def test_market_cap_disabled_admits(self) -> None:
        """price=None + cap<=0 → ADMIT (no notional reason)."""
        req = _make_request(order_type=OrderType.MARKET, price=None)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
        )
        assert rec.decision == Decision.ADMIT
        assert ReasonCode.NOTIONAL_UNCOMPUTABLE not in rec.reason_codes
        assert ReasonCode.NOTIONAL_ABOVE_CAP not in rec.reason_codes

    def test_limit_cap_within_admits(self) -> None:
        """LIMIT + cap>0, notional ≤ cap → ADMIT."""
        req = _make_request(quantity=Decimal("0.1"), price=Decimal("50000"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("100000"),
            now=NOW,
        )
        assert rec.decision == Decision.ADMIT

    def test_limit_cap_exceeded_denies(self) -> None:
        """LIMIT + cap>0, notional > cap → DENY [NOTIONAL_ABOVE_CAP]."""
        req = _make_request(quantity=Decimal("1"), price=Decimal("50000"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("10000"),
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.NOTIONAL_ABOVE_CAP in rec.reason_codes


# ── Off-by-default cap ────────────────────────────────────────────────────


class TestOffByDefaultCap:
    def test_cap_zero_passes(self) -> None:
        req = _make_request(quantity=Decimal("100"), price=Decimal("50000"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
        )
        assert rec.decision == Decision.ADMIT
        cap_result = [
            r for r in rec.invariant_results if r.code == ReasonCode.NOTIONAL_ABOVE_CAP
        ]
        assert cap_result[0].passed is True


# ── Each reason-code triggers ─────────────────────────────────────────────


class TestReasonCodes:
    def test_unsupported_order_type(self) -> None:
        req = _make_request(order_type=OrderType.STOP_LIMIT)
        # Модифицируем правила чтобы STOP_LIMIT не поддерживался
        rules_no_stop = MarketRules(
            min_amount=Decimal("0.001"),
            max_amount=Decimal("1000"),
            min_price=Decimal("0.01"),
            max_price=Decimal("100000"),
            min_notional=Decimal("5"),
            amount_step=Decimal("0.001"),
            price_tick=Decimal("0.01"),
            precision_mode=PrecisionMode.DECIMAL_PLACES,
            supported_order_types=frozenset({OrderType.MARKET, OrderType.LIMIT}),
            supported_tif=frozenset(
                {TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}
            ),
        )
        snap = MarketSnapshot(
            rules=rules_no_stop, fetched_at=NOW, metadata_version="v1"
        )
        rec = admit(
            intent=req,
            snapshot=snap,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.UNSUPPORTED_ORDER_TYPE in rec.reason_codes

    def test_unsupported_tif(self) -> None:
        req = _make_request(time_in_force=TimeInForce.FOK)
        # Модифицируем правила чтобы FOK не поддерживался
        rules_no_fok = MarketRules(
            min_amount=Decimal("0.001"),
            max_amount=Decimal("1000"),
            min_price=Decimal("0.01"),
            max_price=Decimal("100000"),
            min_notional=Decimal("5"),
            amount_step=Decimal("0.001"),
            price_tick=Decimal("0.01"),
            precision_mode=PrecisionMode.DECIMAL_PLACES,
            supported_order_types=frozenset(
                {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
            ),
            supported_tif=frozenset({TimeInForce.GTC, TimeInForce.IOC}),
        )
        snap = MarketSnapshot(rules=rules_no_fok, fetched_at=NOW, metadata_version="v1")
        rec = admit(
            intent=req,
            snapshot=snap,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.UNSUPPORTED_TIF in rec.reason_codes

    def test_price_required_limit_no_price(self) -> None:
        req = _make_request(price=None)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.PRICE_REQUIRED in rec.reason_codes

    def test_non_positive_field_zero_qty(self) -> None:
        req = _make_request(quantity=Decimal("0"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.NON_POSITIVE_FIELD in rec.reason_codes

    def test_non_positive_field_negative_price(self) -> None:
        req = _make_request(price=Decimal("-1"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.NON_POSITIVE_FIELD in rec.reason_codes

    def test_qty_below_min(self) -> None:
        req = _make_request(quantity=Decimal("0.0001"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.QTY_BELOW_MIN in rec.reason_codes

    def test_qty_above_max(self) -> None:
        req = _make_request(quantity=Decimal("2000"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.QTY_ABOVE_MAX in rec.reason_codes

    def test_price_below_min(self) -> None:
        req = _make_request(price=Decimal("0.001"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.PRICE_BELOW_MIN in rec.reason_codes

    def test_price_above_max(self) -> None:
        req = _make_request(price=Decimal("200000"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.PRICE_ABOVE_MAX in rec.reason_codes

    def test_notional_below_min(self) -> None:
        req = _make_request(quantity=Decimal("0.001"), price=Decimal("1"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.NOTIONAL_BELOW_MIN in rec.reason_codes

    def test_notional_above_cap(self) -> None:
        req = _make_request(quantity=Decimal("1"), price=Decimal("50000"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("10000"),
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.NOTIONAL_ABOVE_CAP in rec.reason_codes

    def test_snapshot_stale(self) -> None:
        stale_snapshot = MarketSnapshot(
            rules=DEFAULT_RULES,
            fetched_at=NOW - timedelta(seconds=600),
            metadata_version="v1",
        )
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=stale_snapshot,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SNAPSHOT_STALE in rec.reason_codes

    def test_snapshot_version_mismatch(self) -> None:
        policy = FreshnessPolicy(max_age_seconds=300, expected_metadata_version="v2")
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=policy,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SNAPSHOT_VERSION_MISMATCH in rec.reason_codes


# ── Fail-closed (EVAL_ERROR) ──────────────────────────────────────────────


class TestFailClosed:
    def test_eval_error_on_bad_snapshot(self) -> None:
        """Инъекция битого snapshot → EVAL_ERROR."""
        req = _make_request()
        bad_snapshot = "not-a-snapshot"  # type: ignore[arg-type]
        rec = admit(
            intent=req,
            snapshot=bad_snapshot,  # type: ignore[arg-type]
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.EVAL_ERROR in rec.reason_codes


# ── Collect-all ───────────────────────────────────────────────────────────


class TestCollectAll:
    def test_multiple_violations(self) -> None:
        """Несколько нарушений → все в reason_codes."""
        rules_minimal = MarketRules(
            min_amount=Decimal("1"),
            max_amount=Decimal("10"),
            min_price=Decimal("10"),
            max_price=Decimal("100"),
            min_notional=Decimal("50"),
            amount_step=Decimal("0.001"),
            price_tick=Decimal("0.01"),
            precision_mode=PrecisionMode.DECIMAL_PLACES,
            supported_order_types=frozenset({OrderType.LIMIT}),
            supported_tif=frozenset({TimeInForce.GTC}),
        )
        snap = MarketSnapshot(
            rules=rules_minimal, fetched_at=NOW, metadata_version="v1"
        )
        req = _make_request(
            order_type=OrderType.STOP_LIMIT,
            quantity=Decimal("0"),
            price=Decimal("-1"),
        )
        rec = admit(
            intent=req,
            snapshot=snap,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert len(rec.reason_codes) >= 3
        assert ReasonCode.UNSUPPORTED_ORDER_TYPE in rec.reason_codes
        assert ReasonCode.NON_POSITIVE_FIELD in rec.reason_codes


# ── Determinism ───────────────────────────────────────────────────────────


class TestDeterminism:
    def test_intent_hash_stable(self) -> None:
        req = _make_request()
        r1 = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        r2 = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert r1.intent_hash == r2.intent_hash

    def test_snapshot_hash_stable(self) -> None:
        r1 = admit(
            intent=_make_request(),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        r2 = admit(
            intent=_make_request(),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert r1.snapshot_hash == r2.snapshot_hash

    def test_hash_differs_on_different_data(self) -> None:
        r1 = admit(
            intent=_make_request(quantity=Decimal("0.1")),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        r2 = admit(
            intent=_make_request(quantity=Decimal("0.2")),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert r1.intent_hash != r2.intent_hash

    def test_semantic_hash_stable(self) -> None:
        req = _make_request()
        r1 = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        r2 = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert r1.semantic_hash == r2.semantic_hash

    def test_semantic_hash_cid_invariant(self) -> None:
        """Два запроса, отличающиеся ТОЛЬКО client_order_id, дают одинаковый semantic_hash."""
        r1 = admit(
            intent=_make_request(client_order_id="cid-001"),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        r2 = admit(
            intent=_make_request(client_order_id="cid-002"),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert r1.semantic_hash == r2.semantic_hash
        # intent_hash при этом РАЗНЫЙ
        assert r1.intent_hash != r2.intent_hash

    def test_semantic_hash_differs_on_qty(self) -> None:
        r1 = admit(
            intent=_make_request(quantity=Decimal("0.1")),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        r2 = admit(
            intent=_make_request(quantity=Decimal("0.2")),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert r1.semantic_hash != r2.semantic_hash

    def test_semantic_hash_differs_on_side(self) -> None:
        r1 = admit(
            intent=_make_request(side=OrderSide.BUY),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        r2 = admit(
            intent=_make_request(side=OrderSide.SELL),
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert r1.semantic_hash != r2.semantic_hash

    def test_fail_closed_semantic_hash_empty(self) -> None:
        """EVAL_ERROR → semantic_hash='' (fail-closed)."""
        req = _make_request()
        bad_snapshot = "not-a-snapshot"  # type: ignore[arg-type]
        rec = admit(
            intent=req,
            snapshot=bad_snapshot,  # type: ignore[arg-type]
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY
        assert rec.semantic_hash == ""


def _make_account(**overrides: object) -> AccountSnapshot:
    defaults: dict[str, object] = dict(
        balances=(
            BalanceSnapshot(
                asset="BTC", free=Decimal("1"), locked=Decimal(0), total=Decimal("1")
            ),
            BalanceSnapshot(
                asset="USDT",
                free=Decimal("50000"),
                locked=Decimal(0),
                total=Decimal("50000"),
            ),
        ),
        fetched_at=NOW,
    )
    defaults.update(overrides)  # type: ignore[arg-type]
    return AccountSnapshot(**defaults)  # type: ignore[call-overload]


class TestAccountPortfolio:
    def test_account_none_skips_portfolio(self) -> None:
        """account=None ⇒ ни одного портфельного кода, 12 invariants."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=None,
        )
        assert rec.decision == Decision.ADMIT
        assert len(rec.invariant_results) == 12
        portfolio_codes = {
            ReasonCode.ACCOUNT_SNAPSHOT_STALE,
            ReasonCode.INSUFFICIENT_FREE_BALANCE,
            ReasonCode.BALANCE_UNCOMPUTABLE,
        }
        assert portfolio_codes.isdisjoint(set(rec.reason_codes))

    def test_buy_within_free_admits(self) -> None:
        """BUY 0.1 BTC @ 50000 = 5000 USDT; free=50000 → ADMIT."""
        account = _make_account()
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("0.1"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=account,
        )
        assert rec.decision == Decision.ADMIT
        assert len(rec.invariant_results) == 14

    def test_buy_over_free_denies(self) -> None:
        """BUY 1 BTC @ 50000 = 50000 USDT; free=50000 → DENY (cost includes fee)."""
        account = _make_account()
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("1"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
            fee_rate=Decimal("0.001"),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.INSUFFICIENT_FREE_BALANCE in rec.reason_codes

    def test_buy_market_with_account_denies(self) -> None:
        """BUY MARKET + account → DENY[BALANCE_UNCOMPUTABLE] (price=None)."""
        account = _make_account()
        req = _make_request(order_type=OrderType.MARKET, price=None)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.BALANCE_UNCOMPUTABLE in rec.reason_codes

    def test_sell_within_base_admits(self) -> None:
        """SELL 0.5 BTC; free BTC=1 → ADMIT (cap disabled)."""
        account = _make_account()
        req = _make_request(
            side=OrderSide.SELL, quantity=Decimal("0.5"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
        )
        assert rec.decision == Decision.ADMIT

    def test_sell_over_base_denies(self) -> None:
        """SELL 2 BTC; free BTC=1 → DENY[INSUFFICIENT_FREE_BALANCE]."""
        account = _make_account()
        req = _make_request(
            side=OrderSide.SELL, quantity=Decimal("2"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=account,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.INSUFFICIENT_FREE_BALANCE in rec.reason_codes

    def test_fee_rate_pushes_over_free(self) -> None:
        """fee_rate=0.01: cost = 0.1 * 50000 * 1.01 = 5050; free=5000 → DENY."""
        account = _make_account(
            balances=(
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("1"),
                    locked=Decimal(0),
                    total=Decimal("1"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("5000"),
                    locked=Decimal(0),
                    total=Decimal("5000"),
                ),
            ),
        )
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("0.1"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
            fee_rate=Decimal("0.01"),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.INSUFFICIENT_FREE_BALANCE in rec.reason_codes

    def test_stale_account_denies(self) -> None:
        """Account fetched_at > max_age → DENY[ACCOUNT_SNAPSHOT_STALE]."""
        stale_account = _make_account(fetched_at=NOW - timedelta(seconds=600))
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=stale_account,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.ACCOUNT_SNAPSHOT_STALE in rec.reason_codes

    def test_collect_all_mixed_codes(self) -> None:
        """Портфельный + per-order коды вместе в reason_codes."""
        account = _make_account()
        req = _make_request(
            side=OrderSide.SELL,
            quantity=Decimal("2"),
            price=Decimal("50000"),
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=account,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.INSUFFICIENT_FREE_BALANCE in rec.reason_codes
        assert len(rec.invariant_results) == 14

    def test_symbol_no_slash_denies(self) -> None:
        """Symbol без '/' → DENY[BALANCE_UNCOMPUTABLE]."""
        account = _make_account()
        req = _make_request(symbol="BTCUSDT")
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=account,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.BALANCE_UNCOMPUTABLE in rec.reason_codes


# ── Position cap (off-by-default) ────────────────────────────────────────


class TestPositionCap:
    def test_buy_within_cap_admits(self) -> None:
        """BUY 0.1 BTC @ 50000; total=1 → projected=(1+0.1)*50000=55000; cap=100000 → ADMIT."""
        account = _make_account()
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("0.1"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=account,
            max_position=Decimal("100000"),
        )
        assert rec.decision == Decision.ADMIT

    def test_buy_over_cap_denies(self) -> None:
        """BUY 1 BTC @ 50000; total=1 → projected=(1+1)*50000=100000; cap=80000 → DENY."""
        account = _make_account()
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("1"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
            max_position=Decimal("80000"),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.POSITION_ABOVE_CAP in rec.reason_codes

    def test_projected_uses_total_of_base(self) -> None:
        """projected = (total_of(base) + qty) * price — existing position counted."""
        account = _make_account(
            balances=(
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("0.5"),
                    locked=Decimal("0.5"),
                    total=Decimal("1"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("50000"),
                    locked=Decimal(0),
                    total=Decimal("50000"),
                ),
            ),
        )
        # projected = (1 + 0.1) * 50000 = 55000; cap=54000 → DENY
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("0.1"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
            max_position=Decimal("54000"),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.POSITION_ABOVE_CAP in rec.reason_codes

    def test_buy_market_no_price_denies(self) -> None:
        """BUY MARKET (price=None) + cap → DENY[POSITION_UNCOMPUTABLE]."""
        account = _make_account()
        req = _make_request(order_type=OrderType.MARKET, price=None)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
            max_position=Decimal("100000"),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.POSITION_UNCOMPUTABLE in rec.reason_codes

    def test_sell_over_cap_admits(self) -> None:
        """SELL (reduce) bypasses position cap — ADR-033 §4."""
        account = _make_account(
            balances=(
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("100"),
                    locked=Decimal(0),
                    total=Decimal("100"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("50000"),
                    locked=Decimal(0),
                    total=Decimal("50000"),
                ),
            ),
        )
        req = _make_request(
            side=OrderSide.SELL, quantity=Decimal("10"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
            max_position=Decimal("1000"),
        )
        assert rec.decision == Decision.ADMIT

    def test_no_slash_symbol_denies(self) -> None:
        """Symbol без '/' + cap → DENY[POSITION_UNCOMPUTABLE]."""
        account = _make_account()
        req = _make_request(symbol="BTCUSDT")
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            account=account,
            max_position=Decimal("100000"),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.POSITION_UNCOMPUTABLE in rec.reason_codes

    def test_cap_zero_off(self) -> None:
        """max_position=0 → no portfolio result added."""
        account = _make_account(
            balances=(
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("1"),
                    locked=Decimal(0),
                    total=Decimal("1"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("5000000"),
                    locked=Decimal(0),
                    total=Decimal("5000000"),
                ),
            ),
        )
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=account,
            max_position=Decimal("0"),
        )
        assert rec.decision == Decision.ADMIT
        pos_codes = {ReasonCode.POSITION_ABOVE_CAP, ReasonCode.POSITION_UNCOMPUTABLE}
        assert pos_codes.isdisjoint(set(rec.reason_codes))

    def test_account_none_off(self) -> None:
        """account=None → no portfolio results, 12 invariants."""
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("50000")
        )
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            account=None,
            max_position=Decimal("100000"),
        )
        assert rec.decision == Decision.ADMIT
        assert len(rec.invariant_results) == 12


# ── Open orders count cap (off-by-default) ────────────────────────────────


def _make_order_snapshot(**overrides: object) -> OrderSnapshot:
    defaults: dict[str, object] = dict(
        client_order_id="ord-001",
        venue_order_id="v-001",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        state=OrderState.NEW,
        quantity=Decimal("0.1"),
        executed_qty=Decimal(0),
        price=Decimal("50000"),
        transact_time=int(NOW.timestamp() * 1000),
    )
    defaults.update(overrides)  # type: ignore[arg-type]
    return OrderSnapshot(**defaults)  # type: ignore[call-overload]


def _make_open_orders(
    orders: tuple[OrderSnapshot, ...] | None = None,
    fetched_at: datetime | None = None,
) -> OpenOrdersSnapshot:
    return OpenOrdersSnapshot(
        orders=orders or (),
        fetched_at=fetched_at or NOW,
    )


class TestOpenOrdersPortfolio:
    def test_within_cap_admits(self) -> None:
        """2 open orders + cap=3 → projected=3 ≤ 3 → ADMIT."""
        oo = _make_open_orders(
            orders=(
                _make_order_snapshot(client_order_id="o1", venue_order_id="v1"),
                _make_order_snapshot(client_order_id="o2", venue_order_id="v2"),
            ),
        )
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
            open_orders=oo,
            max_open_orders=3,
        )
        assert rec.decision == Decision.ADMIT

    def test_over_cap_denies(self) -> None:
        """3 open orders + cap=3 → projected=4 > 3 → DENY."""
        oo = _make_open_orders(
            orders=(
                _make_order_snapshot(client_order_id="o1", venue_order_id="v1"),
                _make_order_snapshot(client_order_id="o2", venue_order_id="v2"),
                _make_order_snapshot(client_order_id="o3", venue_order_id="v3"),
            ),
        )
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=oo,
            max_open_orders=3,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.OPEN_ORDERS_ABOVE_CAP in rec.reason_codes

    def test_at_cap_admits(self) -> None:
        """1 open order + cap=1 → projected=2 > 1 → DENY; but 0 existing + cap=1 → ADMIT."""
        # Zero existing orders, cap=1 → projected=1 ≤ 1 → ADMIT
        oo = _make_open_orders(orders=())
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=oo,
            max_open_orders=1,
        )
        assert rec.decision == Decision.ADMIT

    def test_cap_zero_off(self) -> None:
        """max_open_orders=0 → no open orders result added."""
        oo = _make_open_orders(
            orders=(_make_order_snapshot(client_order_id="o1", venue_order_id="v1"),),
        )
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=oo,
            max_open_orders=0,
        )
        assert rec.decision == Decision.ADMIT
        oo_codes = {
            ReasonCode.OPEN_ORDERS_SNAPSHOT_STALE,
            ReasonCode.OPEN_ORDERS_ABOVE_CAP,
        }
        assert oo_codes.isdisjoint(set(rec.reason_codes))

    def test_open_orders_none_off(self) -> None:
        """open_orders=None → no open orders results, 12 invariants."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=None,
            max_open_orders=3,
        )
        assert rec.decision == Decision.ADMIT
        assert len(rec.invariant_results) == 12

    def test_stale_open_orders_denies(self) -> None:
        """open_orders fetched_at > max_age → DENY[OPEN_ORDERS_SNAPSHOT_STALE]."""
        oo = _make_open_orders(fetched_at=NOW - timedelta(seconds=600))
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=oo,
            max_open_orders=3,
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.OPEN_ORDERS_SNAPSHOT_STALE in rec.reason_codes

    def test_market_bypass_over_cap_admits(self) -> None:
        """MARKET order over cap → ADMIT (MARKET bypass, only _LIMIT_TYPES checked)."""
        oo = _make_open_orders(
            orders=(
                _make_order_snapshot(client_order_id="o1", venue_order_id="v1"),
                _make_order_snapshot(client_order_id="o2", venue_order_id="v2"),
                _make_order_snapshot(client_order_id="o3", venue_order_id="v3"),
            ),
        )
        req = _make_request(order_type=OrderType.MARKET, price=None)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=oo,
            max_open_orders=3,
        )
        assert rec.decision == Decision.ADMIT

    def test_per_symbol_isolation(self) -> None:
        """Orders for ETH/USDT don't count toward BTC/USDT cap."""
        oo = _make_open_orders(
            orders=(
                _make_order_snapshot(
                    client_order_id="o1",
                    venue_order_id="v1",
                    symbol="ETH/USDT",
                ),
                _make_order_snapshot(
                    client_order_id="o2",
                    venue_order_id="v2",
                    symbol="ETH/USDT",
                ),
            ),
        )
        req = _make_request(symbol="BTC/USDT")
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=oo,
            max_open_orders=1,
        )
        assert rec.decision == Decision.ADMIT

    def test_sell_orders_count(self) -> None:
        """SELL orders also count toward cap (both sides, no reduce-bypass)."""
        oo = _make_open_orders(
            orders=(
                _make_order_snapshot(
                    client_order_id="o1",
                    venue_order_id="v1",
                    side=OrderSide.SELL,
                ),
                _make_order_snapshot(client_order_id="o2", venue_order_id="v2"),
            ),
        )
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            open_orders=oo,
            max_open_orders=2,
        )
        # 2 existing + 1 projected = 3 > 2 → DENY
        assert rec.decision == Decision.DENY
        assert ReasonCode.OPEN_ORDERS_ABOVE_CAP in rec.reason_codes


# ── Kill-switch invariant (off-by-default) ──────────────────────────────────


def _make_session(
    kill_switch_engaged: bool = False,
    mode: SessionMode = SessionMode.NORMAL,
    drawdown_tripped: bool = False,
    cooldown_tripped: bool = False,
    submit_rate_exceeded: bool = False,
    duplicate_intent: bool = False,
) -> SessionSnapshot:
    return SessionSnapshot(
        kill_switch_engaged=kill_switch_engaged,
        fetched_at=NOW,
        mode=mode,
        drawdown_tripped=drawdown_tripped,
        cooldown_tripped=cooldown_tripped,
        submit_rate_exceeded=submit_rate_exceeded,
        duplicate_intent=duplicate_intent,
    )


class TestKillSwitch:
    def test_engaged_denies(self) -> None:
        """kill_switch_engaged=True → DENY[KILL_SWITCH_ENGAGED]."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(kill_switch_engaged=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.KILL_SWITCH_ENGAGED in rec.reason_codes

    def test_not_engaged_admits(self) -> None:
        """kill_switch_engaged=False → ADMIT (no session violation)."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(kill_switch_engaged=False),
        )
        assert rec.decision == Decision.ADMIT

    def test_session_none_skips(self) -> None:
        """session=None → kill-switch invariant absent (17 invariant_results)."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=None,
        )
        assert rec.decision == Decision.ADMIT
        codes = {r.code for r in rec.invariant_results}
        assert ReasonCode.KILL_SWITCH_ENGAGED not in codes

    def test_collect_all_engaged_plus_violation(self) -> None:
        """engaged + snapshot stale → both KILL_SWITCH_ENGAGED + SNAPSHOT_STALE."""
        stale_snapshot = MarketSnapshot(
            rules=DEFAULT_RULES,
            fetched_at=NOW - timedelta(seconds=600),
            metadata_version="v1",
        )
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=stale_snapshot,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(kill_switch_engaged=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.KILL_SWITCH_ENGAGED in rec.reason_codes
        assert ReasonCode.SNAPSHOT_STALE in rec.reason_codes

    def test_session_snapshot_naive_guard(self) -> None:
        """SessionSnapshot with naive fetched_at → ValueError."""
        with pytest.raises(ValueError, match="fetched_at"):
            SessionSnapshot(kill_switch_engaged=False, fetched_at=datetime(2026, 1, 1))


# ── Hypothesis anti-drift (kill-switch) ─────────────────────────────────────


@given(engaged=st.just(True))
@settings(max_examples=200)
def test_kill_switch_engaged_never_admit(engaged: bool) -> None:
    """kill_switch_engaged=True ⇒ never ADMIT (Hypothesis anti-drift)."""
    req = _make_request()
    rec = admit(
        intent=req,
        snapshot=DEFAULT_SNAPSHOT,
        policy=DEFAULT_POLICY,
        max_order_notional=Decimal("0"),
        now=NOW,
        session=_make_session(kill_switch_engaged=engaged),
    )
    assert rec.decision == Decision.DENY
    assert ReasonCode.KILL_SWITCH_ENGAGED in rec.reason_codes


@given(
    num_orders=st.integers(min_value=0, max_value=50),
    cap=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200)
def test_open_orders_over_cap_never_admit(num_orders: int, cap: int) -> None:
    """projected > cap ⇒ never ADMIT (Hypothesis anti-drift)."""
    orders = tuple(
        _make_order_snapshot(
            client_order_id=f"o{i}",
            venue_order_id=f"v{i}",
        )
        for i in range(num_orders)
    )
    oo = _make_open_orders(orders=orders)
    req = _make_request()
    rec = admit(
        intent=req,
        snapshot=DEFAULT_SNAPSHOT,
        policy=DEFAULT_POLICY,
        max_order_notional=Decimal("0"),
        now=NOW,
        open_orders=oo,
        max_open_orders=cap,
    )
    if num_orders + 1 > cap:
        assert rec.decision == Decision.DENY
        assert ReasonCode.OPEN_ORDERS_ABOVE_CAP in rec.reason_codes


# ── Session mode (NORMAL / REDUCING / HALTED) ────────────────────────────────


class TestSessionMode:
    def test_halted_denies_all(self) -> None:
        """HALTED → DENY[SESSION_HALTED] for any place intent."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(mode=SessionMode.HALTED),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_HALTED in rec.reason_codes

    def test_halted_sell_denies(self) -> None:
        """HALTED + SELL → still DENY[SESSION_HALTED] (cancel goes mimo gate)."""
        req = _make_request(side=OrderSide.SELL)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(mode=SessionMode.HALTED),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_HALTED in rec.reason_codes

    def test_reducing_buy_denies(self) -> None:
        """REDUCING + BUY → DENY[SESSION_REDUCE_ONLY]."""
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(mode=SessionMode.REDUCING),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_REDUCE_ONLY in rec.reason_codes

    def test_reducing_sell_admits(self) -> None:
        """REDUCING + SELL → ADMIT (spot-reduce allowed)."""
        req = _make_request(side=OrderSide.SELL)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(mode=SessionMode.REDUCING),
        )
        assert rec.decision == Decision.ADMIT
        assert ReasonCode.SESSION_REDUCE_ONLY not in rec.reason_codes

    def test_normal_admits(self) -> None:
        """NORMAL → ADMIT, no session violations."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(mode=SessionMode.NORMAL),
        )
        assert rec.decision == Decision.ADMIT
        session_codes = {ReasonCode.SESSION_HALTED, ReasonCode.SESSION_REDUCE_ONLY}
        assert session_codes.isdisjoint(set(rec.reason_codes))

    def test_default_mode_is_normal(self) -> None:
        """SessionSnapshot without explicit mode → NORMAL."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=SessionSnapshot(kill_switch_engaged=False, fetched_at=NOW),
        )
        assert rec.decision == Decision.ADMIT

    def test_session_none_skips_mode(self) -> None:
        """session=None → no session mode results."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=None,
        )
        codes = {r.code for r in rec.invariant_results}
        assert ReasonCode.SESSION_HALTED not in codes
        assert ReasonCode.SESSION_REDUCE_ONLY not in codes

    def test_collect_all_halted_plus_killswitch(self) -> None:
        """engaged + HALTED → both KILL_SWITCH_ENGAGED + SESSION_HALTED."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(kill_switch_engaged=True, mode=SessionMode.HALTED),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.KILL_SWITCH_ENGAGED in rec.reason_codes
        assert ReasonCode.SESSION_HALTED in rec.reason_codes

    def test_invariant_count_with_session(self) -> None:
        """session present → 19 invariants (12 base + #18..#24)."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(),
        )
        assert len(rec.invariant_results) == 19


@given(mode=st.sampled_from([SessionMode.HALTED]))
@settings(max_examples=200)
def test_halted_never_admit(mode: SessionMode) -> None:
    """HALTED ⇒ never ADMIT (Hypothesis anti-drift)."""
    req = _make_request()
    rec = admit(
        intent=req,
        snapshot=DEFAULT_SNAPSHOT,
        policy=DEFAULT_POLICY,
        max_order_notional=Decimal("0"),
        now=NOW,
        session=_make_session(mode=mode),
    )
    assert rec.decision == Decision.DENY
    assert ReasonCode.SESSION_HALTED in rec.reason_codes


# ── Session risk-tripped (drawdown + cooldown) ────────────────────────────────


class TestSessionRiskTripped:
    def test_drawdown_buy_denies(self) -> None:
        """drawdown_tripped + BUY → DENY[SESSION_DRAWDOWN_TRIPPED]."""
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(drawdown_tripped=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED in rec.reason_codes

    def test_drawdown_sell_admits(self) -> None:
        """drawdown_tripped + SELL → ADMIT (reduce bypass)."""
        req = _make_request(side=OrderSide.SELL)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(drawdown_tripped=True),
        )
        assert rec.decision == Decision.ADMIT
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED not in rec.reason_codes

    def test_cooldown_buy_denies(self) -> None:
        """cooldown_tripped + BUY → DENY[SESSION_COOLDOWN_TRIPPED]."""
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(cooldown_tripped=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_COOLDOWN_TRIPPED in rec.reason_codes

    def test_cooldown_sell_admits(self) -> None:
        """cooldown_tripped + SELL → ADMIT (reduce bypass)."""
        req = _make_request(side=OrderSide.SELL)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(cooldown_tripped=True),
        )
        assert rec.decision == Decision.ADMIT
        assert ReasonCode.SESSION_COOLDOWN_TRIPPED not in rec.reason_codes

    def test_both_tripped_buy_denies_both_codes(self) -> None:
        """both tripped + BUY → both DRAWDOWN + COOLDOWN in reason_codes."""
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(drawdown_tripped=True, cooldown_tripped=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED in rec.reason_codes
        assert ReasonCode.SESSION_COOLDOWN_TRIPPED in rec.reason_codes

    def test_not_tripped_no_codes(self) -> None:
        """neither tripped → no risk codes."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(),
        )
        risk_codes = {
            ReasonCode.SESSION_DRAWDOWN_TRIPPED,
            ReasonCode.SESSION_COOLDOWN_TRIPPED,
        }
        assert risk_codes.isdisjoint(set(rec.reason_codes))

    def test_session_none_skips_risk(self) -> None:
        """session=None → no risk results."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=None,
        )
        codes = {r.code for r in rec.invariant_results}
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED not in codes
        assert ReasonCode.SESSION_COOLDOWN_TRIPPED not in codes

    def test_collect_all_drawdown_plus_stale(self) -> None:
        """drawdown+stale+BUY → SNAPSHOT_STALE + SESSION_DRAWDOWN_TRIPPED."""
        stale = MarketSnapshot(
            rules=DEFAULT_RULES,
            fetched_at=NOW - timedelta(seconds=600),
            metadata_version="v1",
        )
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=stale,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(drawdown_tripped=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SNAPSHOT_STALE in rec.reason_codes
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED in rec.reason_codes

    def test_snapshot_defaults_false(self) -> None:
        """SessionSnapshot defaults: drawdown=False, cooldown=False."""
        snap = SessionSnapshot(kill_switch_engaged=False, fetched_at=NOW)
        assert snap.drawdown_tripped is False
        assert snap.cooldown_tripped is False

    def test_snapshot_fields_settable(self) -> None:
        """SessionSnapshot accepts drawdown/cooldown explicitly."""
        snap = SessionSnapshot(
            kill_switch_engaged=False,
            fetched_at=NOW,
            drawdown_tripped=True,
            cooldown_tripped=True,
        )
        assert snap.drawdown_tripped is True
        assert snap.cooldown_tripped is True

    def test_snapshot_frozen(self) -> None:
        """SessionSnapshot remains frozen after adding new fields."""
        snap = SessionSnapshot(kill_switch_engaged=False, fetched_at=NOW)
        with pytest.raises(AttributeError):
            snap.drawdown_tripped = True  # type: ignore[misc]


# ── Session submit-rate exceeded ─────────────────────────────────────────────


class TestSessionSubmitRate:
    def test_exceeded_buy_denies(self) -> None:
        """submit_rate_exceeded + BUY → DENY[SESSION_SUBMIT_RATE_EXCEEDED]."""
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(submit_rate_exceeded=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_SUBMIT_RATE_EXCEEDED in rec.reason_codes

    def test_exceeded_sell_admits(self) -> None:
        """submit_rate_exceeded + SELL → ADMIT (reduce bypass)."""
        req = _make_request(side=OrderSide.SELL)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(submit_rate_exceeded=True),
        )
        assert rec.decision == Decision.ADMIT
        assert ReasonCode.SESSION_SUBMIT_RATE_EXCEEDED not in rec.reason_codes

    def test_not_exceeded_no_code(self) -> None:
        """submit_rate_exceeded=False → no code."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(submit_rate_exceeded=False),
        )
        assert ReasonCode.SESSION_SUBMIT_RATE_EXCEEDED not in rec.reason_codes

    def test_session_none_skips_submit_rate(self) -> None:
        """session=None → no submit-rate result."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=None,
        )
        codes = {r.code for r in rec.invariant_results}
        assert ReasonCode.SESSION_SUBMIT_RATE_EXCEEDED not in codes

    def test_snapshot_submit_rate_default_false(self) -> None:
        """SessionSnapshot submit_rate_exceeded defaults to False."""
        snap = SessionSnapshot(kill_switch_engaged=False, fetched_at=NOW)
        assert snap.submit_rate_exceeded is False

    def test_snapshot_submit_rate_settable(self) -> None:
        """SessionSnapshot accepts submit_rate_exceeded explicitly."""
        snap = SessionSnapshot(
            kill_switch_engaged=False, fetched_at=NOW, submit_rate_exceeded=True
        )
        assert snap.submit_rate_exceeded is True


# ── Session duplicate-intent (off-by-default, both-sides deny) ───────────────


class TestSessionDuplicateIntent:
    def test_duplicate_buy_denies(self) -> None:
        """duplicate_intent + BUY → DENY[SESSION_DUPLICATE_INTENT]."""
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(duplicate_intent=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_DUPLICATE_INTENT in rec.reason_codes

    def test_duplicate_sell_also_denies(self) -> None:
        """duplicate_intent + SELL → DENY (no reduce-bypass, unique to #24)."""
        req = _make_request(side=OrderSide.SELL)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(duplicate_intent=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_DUPLICATE_INTENT in rec.reason_codes

    def test_not_duplicate_no_code(self) -> None:
        """duplicate_intent=False → no code."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(duplicate_intent=False),
        )
        assert ReasonCode.SESSION_DUPLICATE_INTENT not in rec.reason_codes

    def test_session_none_skips_duplicate_intent(self) -> None:
        """session=None → no duplicate-intent result."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=None,
        )
        codes = {r.code for r in rec.invariant_results}
        assert ReasonCode.SESSION_DUPLICATE_INTENT not in codes

    def test_collect_all_duplicate_plus_stale(self) -> None:
        """duplicate+stale+BUY → SNAPSHOT_STALE + SESSION_DUPLICATE_INTENT."""
        stale = MarketSnapshot(
            rules=DEFAULT_RULES,
            fetched_at=NOW - timedelta(seconds=600),
            metadata_version="v1",
        )
        req = _make_request(side=OrderSide.BUY)
        rec = admit(
            intent=req,
            snapshot=stale,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(duplicate_intent=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SNAPSHOT_STALE in rec.reason_codes
        assert ReasonCode.SESSION_DUPLICATE_INTENT in rec.reason_codes

    def test_snapshot_duplicate_intent_default_false(self) -> None:
        """SessionSnapshot duplicate_intent defaults to False."""
        snap = SessionSnapshot(kill_switch_engaged=False, fetched_at=NOW)
        assert snap.duplicate_intent is False

    def test_snapshot_duplicate_intent_settable(self) -> None:
        """SessionSnapshot accepts duplicate_intent explicitly."""
        snap = SessionSnapshot(
            kill_switch_engaged=False, fetched_at=NOW, duplicate_intent=True
        )
        assert snap.duplicate_intent is True


@given(duplicate=st.just(True))
@settings(max_examples=200)
def test_duplicate_intent_never_admit(duplicate: bool) -> None:
    """duplicate_intent=True ⇒ never ADMIT (Hypothesis anti-drift, both sides)."""
    for side in (OrderSide.BUY, OrderSide.SELL):
        req = _make_request(side=side)
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(duplicate_intent=duplicate),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_DUPLICATE_INTENT in rec.reason_codes


# ── Consolidated session invariants (#18–#24) ───────────────────────────


class TestCheckerSessionInvariants:
    """Прямые pure-function тесты session-инвариантов #18–#24.

    Все тесты: account=None, open_orders=None, max_position=0,
    max_order_notional=Decimal("0") (cap off), валидный LIMIT с ценой —
    чтобы решение диктовал ТОЛЬКО целевой инвариант.
    """

    def test_session_none_no_session_codes(self) -> None:
        """1. session=None → нет session-кодов; 12 invariants."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=None,
        )
        assert rec.decision == Decision.ADMIT
        assert len(rec.invariant_results) == 12
        session_codes = {
            ReasonCode.KILL_SWITCH_ENGAGED,
            ReasonCode.SESSION_HALTED,
            ReasonCode.SESSION_REDUCE_ONLY,
            ReasonCode.SESSION_DRAWDOWN_TRIPPED,
            ReasonCode.SESSION_COOLDOWN_TRIPPED,
            ReasonCode.SESSION_SUBMIT_RATE_EXCEEDED,
            ReasonCode.SESSION_DUPLICATE_INTENT,
        }
        assert session_codes.isdisjoint(set(rec.reason_codes))

    def test_clean_session_buy_admits(self) -> None:
        """2. Чистая session (все флаги False, mode=NORMAL) → BUY ADMIT; 19 invariants."""
        req = _make_request()
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(),
        )
        assert rec.decision == Decision.ADMIT
        assert len(rec.invariant_results) == 19

    def test_kill_switch_engaged_denies_both_sides(self) -> None:
        """3. #18 kill_switch_engaged=True: BUY → DENY; SELL → DENY."""
        for side in (OrderSide.BUY, OrderSide.SELL):
            req = _make_request(side=side)
            rec = admit(
                intent=req,
                snapshot=DEFAULT_SNAPSHOT,
                policy=DEFAULT_POLICY,
                max_order_notional=Decimal("0"),
                now=NOW,
                session=_make_session(kill_switch_engaged=True),
            )
            assert rec.decision == Decision.DENY
            assert ReasonCode.KILL_SWITCH_ENGAGED in rec.reason_codes

    def test_halted_denies_both_sides(self) -> None:
        """4. #19 mode=HALTED: BUY → DENY; SELL → DENY."""
        for side in (OrderSide.BUY, OrderSide.SELL):
            req = _make_request(side=side)
            rec = admit(
                intent=req,
                snapshot=DEFAULT_SNAPSHOT,
                policy=DEFAULT_POLICY,
                max_order_notional=Decimal("0"),
                now=NOW,
                session=_make_session(mode=SessionMode.HALTED),
            )
            assert rec.decision == Decision.DENY
            assert ReasonCode.SESSION_HALTED in rec.reason_codes

    def test_reducing_buy_denies_sell_admits(self) -> None:
        """5. #20 mode=REDUCING: BUY → DENY[SESSION_REDUCE_ONLY]; SELL → ADMIT."""
        req_buy = _make_request(side=OrderSide.BUY)
        rec_buy = admit(
            intent=req_buy,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(mode=SessionMode.REDUCING),
        )
        assert rec_buy.decision == Decision.DENY
        assert ReasonCode.SESSION_REDUCE_ONLY in rec_buy.reason_codes

        req_sell = _make_request(side=OrderSide.SELL)
        rec_sell = admit(
            intent=req_sell,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(mode=SessionMode.REDUCING),
        )
        assert rec_sell.decision == Decision.ADMIT
        assert ReasonCode.SESSION_REDUCE_ONLY not in rec_sell.reason_codes

    def test_drawdown_tripped_buy_denies_sell_admits(self) -> None:
        """6. #21 drawdown_tripped=True: BUY → DENY[SESSION_DRAWDOWN_TRIPPED]; SELL → ADMIT."""
        req_buy = _make_request(side=OrderSide.BUY)
        rec_buy = admit(
            intent=req_buy,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(drawdown_tripped=True),
        )
        assert rec_buy.decision == Decision.DENY
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED in rec_buy.reason_codes

        req_sell = _make_request(side=OrderSide.SELL)
        rec_sell = admit(
            intent=req_sell,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(drawdown_tripped=True),
        )
        assert rec_sell.decision == Decision.ADMIT
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED not in rec_sell.reason_codes

    def test_cooldown_tripped_buy_denies_sell_admits(self) -> None:
        """7. #22 cooldown_tripped=True: BUY → DENY[SESSION_COOLDOWN_TRIPPED]; SELL → ADMIT."""
        req_buy = _make_request(side=OrderSide.BUY)
        rec_buy = admit(
            intent=req_buy,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(cooldown_tripped=True),
        )
        assert rec_buy.decision == Decision.DENY
        assert ReasonCode.SESSION_COOLDOWN_TRIPPED in rec_buy.reason_codes

        req_sell = _make_request(side=OrderSide.SELL)
        rec_sell = admit(
            intent=req_sell,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(cooldown_tripped=True),
        )
        assert rec_sell.decision == Decision.ADMIT
        assert ReasonCode.SESSION_COOLDOWN_TRIPPED not in rec_sell.reason_codes

    def test_submit_rate_exceeded_buy_denies_sell_admits(self) -> None:
        """8. #23 submit_rate_exceeded=True: BUY → DENY[SESSION_SUBMIT_RATE_EXCEEDED]; SELL → ADMIT."""
        req_buy = _make_request(side=OrderSide.BUY)
        rec_buy = admit(
            intent=req_buy,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(submit_rate_exceeded=True),
        )
        assert rec_buy.decision == Decision.DENY
        assert ReasonCode.SESSION_SUBMIT_RATE_EXCEEDED in rec_buy.reason_codes

        req_sell = _make_request(side=OrderSide.SELL)
        rec_sell = admit(
            intent=req_sell,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(submit_rate_exceeded=True),
        )
        assert rec_sell.decision == Decision.ADMIT
        assert ReasonCode.SESSION_SUBMIT_RATE_EXCEEDED not in rec_sell.reason_codes

    def test_duplicate_intent_denies_both_sides(self) -> None:
        """9. #24 duplicate_intent=True: BUY → DENY; SELL → DENY (нет reduce-bypass)."""
        for side in (OrderSide.BUY, OrderSide.SELL):
            req = _make_request(side=side)
            rec = admit(
                intent=req,
                snapshot=DEFAULT_SNAPSHOT,
                policy=DEFAULT_POLICY,
                max_order_notional=Decimal("0"),
                now=NOW,
                session=_make_session(duplicate_intent=True),
            )
            assert rec.decision == Decision.DENY
            assert ReasonCode.SESSION_DUPLICATE_INTENT in rec.reason_codes

    def test_collect_all_session_plus_qty_below_min(self) -> None:
        """10. Collect-all: drawdown + duplicate_intent + QTY_BELOW_MIN → все три в reason_codes."""
        req = _make_request(side=OrderSide.BUY, quantity=Decimal("0.0001"))
        rec = admit(
            intent=req,
            snapshot=DEFAULT_SNAPSHOT,
            policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            now=NOW,
            session=_make_session(drawdown_tripped=True, duplicate_intent=True),
        )
        assert rec.decision == Decision.DENY
        assert ReasonCode.SESSION_DRAWDOWN_TRIPPED in rec.reason_codes
        assert ReasonCode.SESSION_DUPLICATE_INTENT in rec.reason_codes
        assert ReasonCode.QTY_BELOW_MIN in rec.reason_codes
