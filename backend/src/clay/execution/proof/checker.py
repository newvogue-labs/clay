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
from clay.execution.adapter.enums import OrderSide, OrderType
from clay.execution.proof.decision import Decision, DecisionRecord, InvariantResult
from clay.execution.proof.reason_codes import ReasonCode
from clay.execution.proof.snapshot import (
    AccountSnapshot,
    FreshnessPolicy,
    MarketSnapshot,
    OpenOrdersSnapshot,
    SessionMode,
    SessionSnapshot,
)

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
    account: AccountSnapshot | None = None,
    fee_rate: Decimal = Decimal(0),
    max_position: Decimal = Decimal(0),
    open_orders: OpenOrdersSnapshot | None = None,
    max_open_orders: int = 0,
    session: SessionSnapshot | None = None,
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
    # ── Portfolio invariants (off-by-default: account=None ⇒ skip) ──────
    if account is not None:
        # 13. account freshness
        account_age = (now - account.fetched_at).total_seconds()
        _add(ReasonCode.ACCOUNT_SNAPSHOT_STALE, account_age <= policy.max_age_seconds)
        # 14. no-oversell (side-dependent)
        if "/" not in req.symbol:
            _add(ReasonCode.BALANCE_UNCOMPUTABLE, False)
        elif req.side == OrderSide.BUY and req.price is None:
            _add(ReasonCode.BALANCE_UNCOMPUTABLE, False)
        elif req.side == OrderSide.BUY and req.price is not None:
            cost = req.quantity * req.price * (Decimal(1) + fee_rate)
            _add(
                ReasonCode.INSUFFICIENT_FREE_BALANCE,
                account.free_of(req.symbol.split("/")[1]) >= cost,
            )
        else:
            # SELL
            _add(
                ReasonCode.INSUFFICIENT_FREE_BALANCE,
                account.free_of(req.symbol.split("/")[0]) >= req.quantity,
            )
        # 15. position cap (entry/increase-only; reduce bypass per ADR-033 §4)
        if max_position > 0:
            if "/" not in req.symbol:
                _add(ReasonCode.POSITION_UNCOMPUTABLE, False)
            elif req.side == OrderSide.BUY and req.price is None:
                _add(ReasonCode.POSITION_UNCOMPUTABLE, False)
            elif req.side == OrderSide.BUY and req.price is not None:
                base = req.symbol.split("/")[0]
                projected = (account.total_of(base) + req.quantity) * req.price
                _add(ReasonCode.POSITION_ABOVE_CAP, projected <= max_position)
            else:
                # SELL (reduce) → bypass
                _add(ReasonCode.POSITION_ABOVE_CAP, True)
    # ── Open orders invariants (off-by-default: open_orders=None ⇒ skip) ─
    if open_orders is not None:
        # 16. open orders freshness
        oo_age = (now - open_orders.fetched_at).total_seconds()
        _add(ReasonCode.OPEN_ORDERS_SNAPSHOT_STALE, oo_age <= policy.max_age_seconds)
        # 17. open order count cap (per-symbol, both sides count, MARKET bypass)
        if max_open_orders > 0 and req.order_type in _LIMIT_TYPES:
            projected = open_orders.count_for(req.symbol) + 1
            _add(ReasonCode.OPEN_ORDERS_ABOVE_CAP, projected <= max_open_orders)
        else:
            _add(ReasonCode.OPEN_ORDERS_ABOVE_CAP, True)
    # ── Session invariants (off-by-default: session=None ⇒ skip) ─────────
    if session is not None:
        # 18. kill-switch engaged
        _add(ReasonCode.KILL_SWITCH_ENGAGED, not session.kill_switch_engaged)
        # 19. session halted
        _add(ReasonCode.SESSION_HALTED, session.mode != SessionMode.HALTED)
        # 20. reducing: only SELL allowed
        _add(
            ReasonCode.SESSION_REDUCE_ONLY,
            session.mode != SessionMode.REDUCING or req.side == OrderSide.SELL,
        )
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
    account: AccountSnapshot | None = None,
    fee_rate: Decimal = Decimal(0),
    max_position: Decimal = Decimal(0),
    open_orders: OpenOrdersSnapshot | None = None,
    max_open_orders: int = 0,
    session: SessionSnapshot | None = None,
) -> DecisionRecord:
    """Оценка ордера: ADMIT или DENY(reason-codes). Collect-all, fail-closed."""
    try:
        results = _check_invariants(
            req=intent,
            snapshot=snapshot,
            policy=policy,
            max_order_notional=max_order_notional,
            now=now,
            account=account,
            fee_rate=fee_rate,
            max_position=max_position,
            open_orders=open_orders,
            max_open_orders=max_open_orders,
            session=session,
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
