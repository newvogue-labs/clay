"""Hypothesis anti-drift тесты для proof-gate.

Гарант: если normalization.validate_order raise ⇒ admit()==DENY.
Если validate_order проходит ∧ notional-ok ∧ fresh ⇒ ADMIT.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import hypothesis
from hypothesis import given
from hypothesis import strategies as st

from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    OrderSide,
    OrderType,
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.normalization import validate_order
from clay.execution.adapter.rules import MarketRules
from clay.execution.proof.checker import admit
from clay.execution.proof.decision import Decision
from clay.execution.proof.snapshot import FreshnessPolicy, MarketSnapshot

NOW = datetime.now(tz=timezone.utc)

STABLE_RULES = MarketRules(
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

STABLE_POLICY = FreshnessPolicy(max_age_seconds=300)
STABLE_MAX_NOTIONAL = Decimal("100000")


def _rules_strategy():
    return st.fixed_dictionaries(
        {
            "min_amount": st.decimals(
                min_value=Decimal("0.001"), max_value=Decimal("10")
            ),
            "max_amount": st.decimals(
                min_value=Decimal("10"), max_value=Decimal("10000")
            ),
            "min_price": st.decimals(
                min_value=Decimal("0.01"), max_value=Decimal("10")
            ),
            "max_price": st.decimals(
                min_value=Decimal("100"), max_value=Decimal("200000")
            ),
            "min_notional": st.decimals(
                min_value=Decimal("1"), max_value=Decimal("50")
            ),
        }
    )


def _order_request_from_dict(d: dict) -> OrderRequest:
    return OrderRequest(**d)


def _order_request_strategy() -> st.SearchStrategy[OrderRequest]:
    return st.fixed_dictionaries(
        {
            "symbol": st.just("BTC/USDT"),
            "side": st.sampled_from(list(OrderSide)),
            "order_type": st.sampled_from(list(OrderType)),
            "quantity": st.decimals(
                min_value=Decimal("0.0001"), max_value=Decimal("500")
            ),
            "time_in_force": st.sampled_from(list(TimeInForce)),
            "client_order_id": st.just("hypo-001"),
            "price": st.none()
            | st.decimals(min_value=Decimal("0.001"), max_value=Decimal("200000")),
        }
    ).map(_order_request_from_dict)


@hypothesis.settings(max_examples=200)
@given(req=_order_request_strategy())
def test_validate_order_raise_implies_deny(req: OrderRequest) -> None:
    """Если normalization.validate_order raise ⇒ admit()==DENY."""
    try:
        validate_order(req, STABLE_RULES)
    except Exception:
        rec = admit(
            intent=req,
            snapshot=MarketSnapshot(
                rules=STABLE_RULES, fetched_at=NOW, metadata_version="v1"
            ),
            policy=STABLE_POLICY,
            max_order_notional=STABLE_MAX_NOTIONAL,
            now=NOW,
        )
        assert rec.decision == Decision.DENY


@hypothesis.settings(max_examples=200)
@given(
    req=_order_request_strategy(),
    overrides=_rules_strategy(),
)
def test_valid_order_with_fresh_snapshot_admits(
    req: OrderRequest, overrides: dict
) -> None:
    """Валидный ордер + свежий снимок ⇒ ADMIT."""
    rules = MarketRules(
        min_amount=overrides["min_amount"],
        max_amount=max(overrides["max_amount"], overrides["min_amount"] + Decimal("1")),
        min_price=overrides["min_price"],
        max_price=max(overrides["max_price"], overrides["min_price"] + Decimal("1")),
        min_notional=overrides["min_notional"],
        amount_step=Decimal("0.001"),
        price_tick=Decimal("0.01"),
        precision_mode=PrecisionMode.DECIMAL_PLACES,
        supported_order_types=frozenset(
            {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
        ),
        supported_tif=frozenset({TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK}),
    )
    # Построить валидный ордер
    qty = max(overrides["min_amount"], Decimal("0.001"))
    price = Decimal("100") if req.price is not None else None
    valid_req = OrderRequest(
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type
        if req.order_type in rules.supported_order_types
        else OrderType.LIMIT,
        quantity=qty,
        time_in_force=req.time_in_force
        if req.time_in_force in rules.supported_tif
        else TimeInForce.GTC,
        client_order_id=req.client_order_id,
        price=price,
    )
    # Если validate_order не падает — admit должен ADMIT
    try:
        validate_order(valid_req, rules)
    except Exception:
        return  # validate_order отверг — admit тоже отвергнет (тест выше покрывает)
    # Дополнительно: notional >= min_notional
    if price is not None:
        notional = qty * price
        if notional < rules.min_notional:
            return  # notional < min — admit отвергнет (покрыто unit-тестами)

    snapshot = MarketSnapshot(rules=rules, fetched_at=NOW, metadata_version="v1")
    rec = admit(
        intent=valid_req,
        snapshot=snapshot,
        policy=STABLE_POLICY,
        max_order_notional=STABLE_MAX_NOTIONAL,
        now=NOW,
    )
    assert rec.decision == Decision.ADMIT
