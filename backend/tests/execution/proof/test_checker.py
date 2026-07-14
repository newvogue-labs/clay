"""Unit-тесты для execution/proof — checker, reason-codes, decision-record.

Покрытие: каждый reason-code, happy ADMIT, off-by-default cap, fail-closed,
collect-all, детерминизм хешей.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal


from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    OrderSide,
    OrderType,
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.rules import MarketRules
from clay.execution.proof.checker import admit
from clay.execution.proof.decision import Decision
from clay.execution.proof.reason_codes import ReasonCode
from clay.execution.proof.snapshot import FreshnessPolicy, MarketSnapshot

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
            max_order_notional=DEFAULT_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.ADMIT


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
