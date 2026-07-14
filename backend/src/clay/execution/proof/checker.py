"""Pure checker: admit() — O(1) collect-all оценка ордера.

Fail-closed: любое исключение внутри eval → DENY + [EVAL_ERROR].
Никогда не делает network I/O.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal

import icontract

from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import OrderType
from clay.execution.proof.decision import Decision, DecisionRecord, InvariantResult
from clay.execution.proof.reason_codes import ReasonCode
from clay.execution.proof.snapshot import FreshnessPolicy, MarketSnapshot

logger = logging.getLogger(__name__)

_LIMIT_TYPES = frozenset({OrderType.LIMIT, OrderType.STOP_LIMIT})


def _intent_hash(req: OrderRequest) -> str:
    """Детерминированный хеш OrderRequest (Decimal→str)."""
    canon = json.dumps(
        {
            "symbol": req.symbol,
            "side": str(req.side),
            "order_type": str(req.order_type),
            "quantity": str(req.quantity),
            "time_in_force": str(req.time_in_force),
            "client_order_id": req.client_order_id,
            "price": str(req.price) if req.price is not None else None,
            "stop_price": str(req.stop_price) if req.stop_price is not None else None,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def _check_invariants(
    *,
    req: OrderRequest,
    snapshot: MarketSnapshot,
    policy: FreshnessPolicy,
    max_order_notional: Decimal,
    now: datetime,
) -> list[InvariantResult]:
    """Collect-all проверка инвариантов. Порядок фиксирован."""
    rules = snapshot.rules
    results: list[InvariantResult] = []

    def _add(code: ReasonCode, passed: bool) -> None:
        results.append(InvariantResult(code=code, passed=passed))

    # 1. order_type ∈ supported_order_types
    _add(
        ReasonCode.UNSUPPORTED_ORDER_TYPE,
        req.order_type in rules.supported_order_types,
    )
    # 2. time_in_force ∈ supported_tif
    _add(ReasonCode.UNSUPPORTED_TIF, req.time_in_force in rules.supported_tif)
    # 3. LIMIT/STOP_LIMIT ⇒ price is not None
    _add(
        ReasonCode.PRICE_REQUIRED,
        not (req.order_type in _LIMIT_TYPES and req.price is None),
    )
    # 4. quantity > 0; price is None or price > 0
    qty_positive = req.quantity > 0
    price_positive = req.price is None or req.price > 0
    _add(ReasonCode.NON_POSITIVE_FIELD, qty_positive and price_positive)
    # 5. quantity >= min_amount
    _add(ReasonCode.QTY_BELOW_MIN, req.quantity >= rules.min_amount)
    # 6. quantity <= max_amount
    _add(ReasonCode.QTY_ABOVE_MAX, req.quantity <= rules.max_amount)
    # 7. price >= min_price (если price задан)
    _add(
        ReasonCode.PRICE_BELOW_MIN,
        req.price is None or req.price >= rules.min_price,
    )
    # 8. price <= max_price (если price задан)
    _add(
        ReasonCode.PRICE_ABOVE_MAX,
        req.price is None or req.price <= rules.max_price,
    )
    # 9. notional >= min_notional (если price задан)
    if req.price is not None:
        notional = req.quantity * req.price
        _add(ReasonCode.NOTIONAL_BELOW_MIN, notional >= rules.min_notional)
    else:
        _add(ReasonCode.NOTIONAL_BELOW_MIN, True)
    # 10. notional <= max_order_notional (off-by-default при <=0)
    if max_order_notional > 0 and req.price is not None:
        notional_cap = req.quantity * req.price
        _add(ReasonCode.NOTIONAL_ABOVE_CAP, notional_cap <= max_order_notional)
    elif max_order_notional > 0 and req.price is None:
        # cap активен, но notional невычислим (MARKET) → DENY (fail-closed, зеркалит S-LIVE-2)
        _add(ReasonCode.NOTIONAL_UNCOMPUTABLE, False)
    else:
        # cap выключен (<=0) → неприменимо, проходит
        _add(ReasonCode.NOTIONAL_ABOVE_CAP, True)
    # 11. snapshot freshness: age
    age_seconds = (now - snapshot.fetched_at).total_seconds()
    _add(ReasonCode.SNAPSHOT_STALE, age_seconds <= policy.max_age_seconds)
    # 12. snapshot version
    if policy.expected_metadata_version is not None:
        _add(
            ReasonCode.SNAPSHOT_VERSION_MISMATCH,
            policy.expected_metadata_version == snapshot.metadata_version,
        )
    else:
        _add(ReasonCode.SNAPSHOT_VERSION_MISMATCH, True)
    return results


@icontract.require(lambda snapshot: snapshot is not None)
@icontract.ensure(
    lambda result: (
        (result.decision == Decision.ADMIT) == (len(result.reason_codes) == 0)
    )
)
def admit(
    *,
    intent: OrderRequest,
    snapshot: MarketSnapshot,
    policy: FreshnessPolicy,
    max_order_notional: Decimal,
    now: datetime,
) -> DecisionRecord:
    """Оценка ордера: ADMIT или DENY(reason-codes). Collect-all, fail-closed."""
    try:
        results = _check_invariants(
            req=intent,
            snapshot=snapshot,
            policy=policy,
            max_order_notional=max_order_notional,
            now=now,
        )
        failed = tuple(r.code for r in results if not r.passed)
        decision = Decision.ADMIT if not failed else Decision.DENY
        return DecisionRecord(
            decision=decision,
            intent_hash=_intent_hash(intent),
            snapshot_hash=snapshot.snapshot_hash,
            snapshot_ts=snapshot.fetched_at,
            metadata_version=snapshot.metadata_version,
            invariant_results=tuple(results),
            reason_codes=failed,
            created_at=now,
        )
    except Exception:
        logger.exception("EVAL_ERROR: checker exception (fail-closed)")
        now_utc = (
            now if now.tzinfo else datetime.now(tz=__import__("datetime").timezone.utc)
        )
        return DecisionRecord(
            decision=Decision.DENY,
            intent_hash="",
            snapshot_hash="",
            snapshot_ts=now_utc,
            metadata_version="",
            invariant_results=(),
            reason_codes=(ReasonCode.EVAL_ERROR,),
            created_at=now_utc,
        )
