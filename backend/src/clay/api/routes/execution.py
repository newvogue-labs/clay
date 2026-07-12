"""POST /workspace/trading/execution/testnet-probe — live testnet order probe.

Operator-initiated endpoint that places a REAL order on Binance Spot
testnet, validating the signal→execution chain on a live testnet API.

Safety gates:
  - mode guard: only ``testnet`` allowed (dry_run / live → 409)
  - notional guard: delegated to ``BinanceTestnetExecutionClient.place_order``
    (per-order cap from ``CLAY_EXECUTION_MAX_ORDER_NOTIONAL``)

Audit: durable write via ``AuditWriter.write`` (sync, from bootstrap).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from clay.api.dependencies import get_execution_client, get_execution_config
from clay.bootstrap import audit_writer
from clay.execution.config import ExecutionConfig
from clay.execution.exceptions import (
    OrderRejectedError,
    OrderTimeoutError,
    PartialFillError,
)
from clay.execution.models import OrderResult
from clay.execution.protocol import ExecutionClient

router = APIRouter(prefix="/workspace/trading/execution", tags=["execution"])


# ── Response models (V1) ──────────────────────────────────────────


class TestnetProbeFill(BaseModel):
    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float
    commission_asset: str
    transact_time: int


class TestnetProbeResponse(BaseModel):
    client_order_id: str
    exchange_order_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    status: str
    transact_time: int
    price: float | None = None
    stop_price: float | None = None
    fills: list[TestnetProbeFill] = []


# ── Request model ─────────────────────────────────────────────────


class TestnetProbeRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    order_type: str
    price: float | None = None
    client_order_id: str | None = None


# ── Endpoint ──────────────────────────────────────────────────────


@router.post("/testnet-probe", response_model=TestnetProbeResponse)
async def testnet_probe(
    payload: TestnetProbeRequest,
    exec_config: Annotated[ExecutionConfig, Depends(get_execution_config)],
    client: Annotated[ExecutionClient, Depends(get_execution_client)],
) -> TestnetProbeResponse:
    # V3: mode guard — only testnet allowed
    if exec_config.mode != "testnet":
        raise HTTPException(
            status_code=409,
            detail=f"testnet-probe requires mode=testnet, current={exec_config.mode!r}",
        )

    # V4: notional guard lives inside place_order (single source of truth)
    try:
        result: OrderResult = await client.place_order(
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
            order_type=payload.order_type,
            price=payload.price,
            client_order_id=payload.client_order_id,
        )
    except (OrderRejectedError, OrderTimeoutError, PartialFillError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # V2: durable audit write (sync, from bootstrap)
    audit_writer.write(
        "execution.testnet_probe",
        {
            "actor": "operator",
            "request": {
                "symbol": payload.symbol,
                "side": payload.side,
                "quantity": payload.quantity,
                "order_type": payload.order_type,
                "price": payload.price,
                "client_order_id": payload.client_order_id,
            },
            "result": asdict(result),
        },
    )

    # V1: map dataclass → pydantic via asdict
    result_dict = asdict(result)
    return TestnetProbeResponse(**result_dict)
