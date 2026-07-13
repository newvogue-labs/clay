"""POST /workspace/trading/execution/testnet-probe — live testnet order probe.

Operator-initiated endpoint that places a REAL order on Binance Spot
testnet, validating the signal->execution chain on a live testnet API.

Safety gates:
  - default-deny: only ``testnet`` mode allowed (dry_run -> 409)
  - notional guard: per-order cap (S-LIVE-2) with fail-closed semantics
    (cap>0 + unknown price -> reject)
  - adapter validate+quantize before any cex call

BREAKING-CHANGE (v2): monetary fields now serialise as **str** not float
(Decimal -> JSON string). Frontend consumers: none — operator/curl only.

Audit: durable write via ``AuditWriter.write`` (sync, from bootstrap).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from clay.api.dependencies import get_execution_client, get_execution_config
from clay.bootstrap import audit_writer
from clay.execution.adapter.domain import OrderAck, OrderRequest
from clay.execution.adapter.enums import OrderSide, OrderType, TimeInForce
from clay.execution.adapter.errors import (
    AdapterError,
    AmbiguousExecutionError,
    InvalidOrderError,
    OperationNotAllowedError,
    OrderRejectedError,
)
from clay.execution.adapter.notional import check_order_notional
from clay.execution.adapter.port import ExchangeAdapter
from clay.execution.config import ExecutionConfig

router = APIRouter(prefix="/workspace/trading/execution", tags=["execution"])


# -- Response models (v2 -- Decimal as str) -------------------------


class TestnetProbeFill(BaseModel):
    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    commission: str
    commission_asset: str
    transact_time: int


class TestnetProbeResponse(BaseModel):
    client_order_id: str
    exchange_order_id: str
    symbol: str
    side: str
    quantity: str
    order_type: str
    status: str
    transact_time: int
    price: str | None = None
    stop_price: str | None = None
    fills: list[TestnetProbeFill] = []


# -- Request model -------------------------------------------------


class TestnetProbeRequest(BaseModel):
    symbol: str
    side: str
    quantity: str
    order_type: str
    price: str | None = None
    client_order_id: str | None = None


# -- Mapper: adapter domain -> pydantic response ----


def _ack_to_response(ack: OrderAck) -> TestnetProbeResponse:
    return TestnetProbeResponse(
        client_order_id=ack.client_order_id,
        exchange_order_id=ack.venue_order_id,
        symbol=ack.symbol,
        side=ack.side.value,
        quantity=str(ack.quantity),
        order_type=ack.order_type.value,
        status=ack.state.value,
        transact_time=ack.transact_time,
        price=str(ack.price) if ack.price is not None else None,
        fills=[
            TestnetProbeFill(
                trade_id=f.trade_id,
                order_id=f.venue_order_id,
                symbol=f.symbol,
                side=f.side.value,
                quantity=str(f.quantity),
                price=str(f.price),
                commission=str(f.commission),
                commission_asset=f.commission_asset,
                transact_time=f.transact_time,
            )
            for f in ack.fills
        ],
    )


# -- Endpoint -----------------------------------------


@router.post("/testnet-probe", response_model=TestnetProbeResponse)
async def testnet_probe(
    payload: TestnetProbeRequest,
    exec_config: ExecutionConfig = Depends(get_execution_config),
    client: ExchangeAdapter | None = Depends(get_execution_client),
) -> TestnetProbeResponse:
    # V3: mode guard
    if exec_config.mode != "testnet":
        raise HTTPException(
            status_code=409,
            detail=f"testnet-probe requires mode=testnet, current={exec_config.mode!r}",
        )

    # V4: default-deny
    if client is None:
        raise HTTPException(
            status_code=409,
            detail="execution not armed for testnet",
        )

    # V1: resolve or allocate client_order_id
    cid = payload.client_order_id or uuid4().hex

    # V2: build domain request
    req = OrderRequest(
        symbol=payload.symbol,
        side=OrderSide(payload.side),
        order_type=OrderType(payload.order_type),
        quantity=Decimal(payload.quantity),
        time_in_force=TimeInForce.GTC,
        client_order_id=cid,
        price=Decimal(payload.price) if payload.price else None,
    )

    # V5: get market rules + validate
    try:
        rules = await client.get_market_rules(req.symbol)
    except AdapterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    client.validate_order(req, rules)
    quantized = client.quantize_order(req, rules)

    # V6: notional cap (S-LIVE-2) after quantization, before cex call
    try:
        check_order_notional(
            symbol=quantized.symbol,
            quantity=quantized.quantity,
            price=quantized.price,
            max_notional=Decimal(str(exec_config.max_order_notional_usdt)),
        )
    except OperationNotAllowedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # V7: place via adapter
    try:
        ack = await client.place_order(quantized)
    except InvalidOrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OrderRejectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OperationNotAllowedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AmbiguousExecutionError as exc:
        audit_writer.write(
            "execution.testnet_probe_ambiguous",
            {
                "actor": "operator",
                "cid": quantized.client_order_id,
                "symbol": quantized.symbol,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=409, detail=f"reconcile pending: {exc}"
        ) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # V8: durable audit write
    audit_writer.write(
        "execution.testnet_probe",
        {
            "actor": "operator",
            "request": payload.model_dump(),
            "result": {
                "client_order_id": ack.client_order_id,
                "venue_order_id": ack.venue_order_id,
                "symbol": ack.symbol,
                "side": ack.side.value,
                "quantity": str(ack.quantity),
                "order_type": ack.order_type.value,
                "state": ack.state.value,
                "transact_time": ack.transact_time,
                "price": str(ack.price) if ack.price is not None else None,
                "fills_count": len(ack.fills),
            },
        },
    )

    return _ack_to_response(ack)
