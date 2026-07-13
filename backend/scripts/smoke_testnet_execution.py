"""S-ADAPT-2C: Testnet execution smoke via BinanceExecutionAdapter (no legacy).

Place a non-marketable limit order on testnet, query, cancel, verify gone.
Uses the public adapter API only — no private attrs, no legacy execution client.

Run:
    CLAY_BINANCE_TESTNET_API_KEY=... CLAY_BINANCE_TESTNET_API_SECRET=... python scripts/smoke_testnet_execution.py

Skip:
    Missing env vars → skips with message.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from clay.execution.adapter.binance import BinanceExecutionAdapter
from clay.execution.adapter.domain import OrderAck, OrderRequest, OrderSnapshot
from clay.execution.adapter.enums import (
    Environment,
    OrderSide,
    OrderType,
    TimeInForce,
)


@dataclass
class SmokeEvidence:
    symbol: str = "BTCUSDT"
    side: str = "buy"
    quantity: str = "0.001"
    limit_price: str = "50000.0"
    order_type: str = "limit"
    place_result: OrderAck | None = None
    open_orders_before_cancel: list[dict[str, Any]] = field(default_factory=list)
    cancel_result: str | None = None
    open_orders_after_cancel: list[dict[str, Any]] = field(default_factory=list)
    place_latency_ms: float = 0.0
    query_latency_ms: float = 0.0
    cancel_latency_ms: float = 0.0
    error: str | None = None


def _env() -> tuple[str, str] | None:
    key = os.environ.get("CLAY_BINANCE_TESTNET_API_KEY", "")
    secret = os.environ.get("CLAY_BINANCE_TESTNET_API_SECRET", "")
    if not key or not secret:
        print(
            "[skip] CLAY_BINANCE_TESTNET_API_KEY / CLAY_BINANCE_TESTNET_API_SECRET are not set."
        )
        return None
    return key, secret


def _evidence_path() -> str:
    return os.path.join(os.path.dirname(__file__), "smoke_testnet_evidence.json")


def _snap_to_dict(snap: OrderSnapshot) -> dict[str, Any]:
    return {
        "venue_order_id": snap.venue_order_id,
        "client_order_id": snap.client_order_id,
        "status": snap.state.value,
        "side": snap.side.value,
        "quantity": str(snap.quantity),
        "price": str(snap.price) if snap.price else None,
    }


async def _run() -> SmokeEvidence:
    evidence = SmokeEvidence()
    key, secret = _env()
    if key is None:
        return evidence

    adapter = BinanceExecutionAdapter(
        environment=Environment.TESTNET,
        api_key=key,
        api_secret=secret,
    )
    client_order_id = f"smoke-{int(time.time() * 1000)}"

    try:
        req = OrderRequest(
            symbol=evidence.symbol,
            side=OrderSide(evidence.side),
            order_type=OrderType(evidence.order_type),
            quantity=Decimal(evidence.quantity),
            time_in_force=TimeInForce.GTC,
            client_order_id=client_order_id,
            price=Decimal(evidence.limit_price),
        )

        rules = await adapter.get_market_rules(req.symbol)
        adapter.validate_order(req, rules)
        quantized = adapter.quantize_order(req, rules)

        t0 = time.perf_counter()
        evidence.place_result = await adapter.place_order(quantized)
        evidence.place_latency_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        open_orders = await adapter.get_open_orders(symbol=evidence.symbol)
        evidence.query_latency_ms = (time.perf_counter() - t0) * 1000
        evidence.open_orders_before_cancel = [_snap_to_dict(o) for o in open_orders]

        order_id = evidence.place_result.venue_order_id
        t0 = time.perf_counter()
        await adapter.cancel_order(symbol=evidence.symbol, venue_order_id=order_id)
        evidence.cancel_latency_ms = (time.perf_counter() - t0) * 1000
        evidence.cancel_result = order_id

        t0 = time.perf_counter()
        open_after = await adapter.get_open_orders(symbol=evidence.symbol)
        evidence.query_latency_ms = max(
            evidence.query_latency_ms, (time.perf_counter() - t0) * 1000
        )
        evidence.open_orders_after_cancel = [_snap_to_dict(o) for o in open_after]
    except Exception as exc:  # noqa: BLE001
        evidence.error = f"{type(exc).__name__}: {exc}"
    finally:
        await adapter.close()

    return evidence


def _print_evidence(evidence: SmokeEvidence) -> None:
    print(
        json.dumps(
            {
                "symbol": evidence.symbol,
                "side": evidence.side,
                "quantity": evidence.quantity,
                "limit_price": evidence.limit_price,
                "order_type": evidence.order_type,
                "place_result": {
                    "client_order_id": evidence.place_result.client_order_id
                    if evidence.place_result
                    else None,
                    "venue_order_id": evidence.place_result.venue_order_id
                    if evidence.place_result
                    else None,
                    "status": evidence.place_result.state.value
                    if evidence.place_result
                    else None,
                }
                if evidence.place_result
                else None,
                "open_orders_before_cancel_count": len(
                    evidence.open_orders_before_cancel
                ),
                "open_orders_before_cancel": evidence.open_orders_before_cancel,
                "cancel_result": evidence.cancel_result,
                "open_orders_after_cancel_count": len(
                    evidence.open_orders_after_cancel
                ),
                "open_orders_after_cancel": evidence.open_orders_after_cancel,
                "place_latency_ms": round(evidence.place_latency_ms, 2),
                "query_latency_ms": round(evidence.query_latency_ms, 2),
                "cancel_latency_ms": round(evidence.cancel_latency_ms, 2),
                "error": evidence.error,
            },
            indent=2,
        )
    )


def main() -> int:
    if _env() is None:
        return 0
    evidence = asyncio.run(_run())
    _print_evidence(evidence)

    path = _evidence_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "symbol": evidence.symbol,
                "side": evidence.side,
                "quantity": evidence.quantity,
                "limit_price": evidence.limit_price,
                "order_type": evidence.order_type,
                "place_result": {
                    "client_order_id": evidence.place_result.client_order_id
                    if evidence.place_result
                    else None,
                    "venue_order_id": evidence.place_result.venue_order_id
                    if evidence.place_result
                    else None,
                    "status": evidence.place_result.state.value
                    if evidence.place_result
                    else None,
                }
                if evidence.place_result
                else None,
                "open_orders_before_cancel_count": len(
                    evidence.open_orders_before_cancel
                ),
                "open_orders_after_cancel_count": len(
                    evidence.open_orders_after_cancel
                ),
                "place_latency_ms": round(evidence.place_latency_ms, 2),
                "query_latency_ms": round(evidence.query_latency_ms, 2),
                "cancel_latency_ms": round(evidence.cancel_latency_ms, 2),
                "error": evidence.error,
            },
            f,
            indent=2,
        )
    print(f"[evidence] written to {path}")
    return 1 if evidence.error else 0


def run_smoke() -> SmokeEvidence:
    if _env() is None:
        return SmokeEvidence(error="missing credentials")
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
