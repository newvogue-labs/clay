"""S-EXEC-4: Testnet execution smoke (manual/gated).

Place a non-marketable limit order on testnet, query, cancel, verify gone.
Do NOT write to demo_trade_records. Adapter-level only.

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
from typing import Any

from clay.execution.binance_testnet import BinanceTestnetExecutionClient
from clay.execution.models import OrderResult


@dataclass
class SmokeEvidence:
    symbol: str = "BTCUSDT"
    side: str = "buy"
    quantity: float = 0.001
    limit_price: float = 50000.0  # non-marketable: below BTC market, above minNotional
    order_type: str = "limit"
    place_result: OrderResult | None = None
    open_orders_before_cancel: list[dict[str, Any]] = field(default_factory=list)
    cancel_result: dict[str, Any] | None = None
    open_orders_after_cancel: list[dict[str, Any]] = field(default_factory=list)
    place_latency_ms: float = 0.0
    query_latency_ms: float = 0.0
    cancel_latency_ms: float = 0.0
    rate_limit_weight: str | None = None
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


async def _run() -> SmokeEvidence:
    evidence = SmokeEvidence()
    key, secret = _env()
    if key is None:
        return evidence

    client = BinanceTestnetExecutionClient(api_key=key, api_secret=secret)
    ccxt_client = client._client
    client_order_id = f"smoke-{int(time.time() * 1000)}"

    try:
        await ccxt_client.load_markets()
        t0 = time.perf_counter()
        evidence.place_result = await client.place_order(
            symbol=evidence.symbol,
            side=evidence.side,
            quantity=evidence.quantity,
            order_type=evidence.order_type,
            price=evidence.limit_price,
            time_in_force="GTC",
            client_order_id=client_order_id,
        )
        evidence.place_latency_ms = (time.perf_counter() - t0) * 1000
        evidence.rate_limit_weight = getattr(
            ccxt_client, "last_response_headers", {}
        ).get("x-mbx-used-weight-1m")

        t0 = time.perf_counter()
        open_orders = await client.get_open_orders(symbol=evidence.symbol)
        evidence.query_latency_ms = (time.perf_counter() - t0) * 1000
        evidence.open_orders_before_cancel = [
            {
                "exchange_order_id": o.exchange_order_id,
                "client_order_id": o.client_order_id,
                "status": o.status,
                "side": o.side,
                "quantity": o.quantity,
                "price": o.price,
            }
            for o in open_orders
        ]

        order_id = evidence.place_result.exchange_order_id
        t0 = time.perf_counter()
        cancel = await client.cancel_order(symbol=evidence.symbol, order_id=order_id)
        evidence.cancel_latency_ms = (time.perf_counter() - t0) * 1000
        evidence.cancel_result = cancel

        t0 = time.perf_counter()
        open_after = await client.get_open_orders(symbol=evidence.symbol)
        evidence.query_latency_ms = max(
            evidence.query_latency_ms, (time.perf_counter() - t0) * 1000
        )
        evidence.open_orders_after_cancel = [
            {
                "exchange_order_id": o.exchange_order_id,
                "status": o.status,
            }
            for o in open_after
        ]
    except Exception as exc:  # noqa: BLE001
        evidence.error = f"{type(exc).__name__}: {exc}"
    finally:
        await client.close()

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
                    "exchange_order_id": evidence.place_result.exchange_order_id
                    if evidence.place_result
                    else None,
                    "status": evidence.place_result.status
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
                "rate_limit_weight": evidence.rate_limit_weight,
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
                    "exchange_order_id": evidence.place_result.exchange_order_id
                    if evidence.place_result
                    else None,
                    "status": evidence.place_result.status
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
                "rate_limit_weight": evidence.rate_limit_weight,
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
