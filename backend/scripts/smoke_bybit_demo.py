"""Bybit demo-trading smoke: reachability + optional round-trip order (F-D12-10 smoke).

Tier 0 (READ-ONLY, always):
    reachability (load_markets) + server-time skew + authed get_balances.

Tier 1 (ROUND-TRIP, only if CLAY_BYBIT_SMOKE_PLACE_ORDER=1):
    place tiny LIMIT far from market → get_by_client_order_id →
    record orderLinkId empiric comparison (ccxt #23260) → cancel_order.

Run:
    CLAY_BYBIT_DEMO_API_KEY=... CLAY_BYBIT_DEMO_API_SECRET=... \\
    python scripts/smoke_bybit_demo.py

Tier 1:
    CLAY_BYBIT_SMOKE_PLACE_ORDER=1 CLAY_BYBIT_SMOKE_SYMBOL=BTC/USDT \\
    python scripts/smoke_bybit_demo.py

Skip:
    Missing env vars → prints "[skip] ..." and exits 0.

Evidence:
    Written to scripts/smoke_bybit_demo_evidence.json (gitignored).
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

from clay.execution.adapter.bybit import BybitExecutionAdapter
from clay.execution.adapter.domain import OrderAck, OrderRequest, OrderSnapshot
from clay.execution.adapter.enums import (
    Environment,
    OrderSide,
    OrderType,
    TimeInForce,
)


@dataclass
class SmokeEvidence:
    """Accumulates evidence across Tier 0 and Tier 1 checks."""

    # -- Tier 0 --
    symbol: str = "BTC/USDT"
    reachability_ok: bool = False
    reachability_error: str | None = None
    server_time_ms: int = 0
    local_time_ms: int = 0
    skew_ms: int = 0
    balances_ok: bool = False
    balances_error: str | None = None
    balances: list[dict[str, Any]] = field(default_factory=list)

    # -- Tier 1 --
    tier1_enabled: bool = False
    place_result: OrderAck | None = None
    place_latency_ms: float = 0.0
    client_order_id_sent: str = ""
    venue_order_id_returned: str = ""
    snapshot_client_order_id: str = ""
    raw_orderLinkId: str = ""
    orderLinkId_match: bool | None = None
    cancel_ok: bool = False
    cancel_latency_ms: float = 0.0
    cancel_error: str | None = None
    tier1_error: str | None = None

    error: str | None = None


def _env() -> tuple[str, str] | None:
    key = os.environ.get("CLAY_BYBIT_DEMO_API_KEY", "")
    secret = os.environ.get("CLAY_BYBIT_DEMO_API_SECRET", "")
    if not key or not secret:
        print(
            "[skip] CLAY_BYBIT_DEMO_API_KEY / CLAY_BYBIT_DEMO_API_SECRET are not set."
        )
        return None
    return key, secret


def _evidence_path() -> str:
    return os.path.join(os.path.dirname(__file__), "smoke_bybit_demo_evidence.json")


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
    ev = SmokeEvidence()
    creds = _env()
    if creds is None:
        return ev

    key, secret = creds
    adapter = BybitExecutionAdapter(
        environment=Environment.DEMO,
        api_key=key,
        api_secret=secret,
    )

    try:
        # -- Tier 0: reachability --
        t0 = time.perf_counter()
        try:
            markets = await adapter._client.load_markets()
            ev.reachability_ok = len(markets) > 0
        except Exception as exc:  # noqa: BLE001
            ev.reachability_error = f"{type(exc).__name__}: {exc}"
            ev.error = ev.reachability_error
            return ev

        # -- Tier 0: server-time skew --
        try:
            server_time = await adapter._client.fetch_time()
            ev.server_time_ms = int(server_time)
            ev.local_time_ms = int(time.time() * 1000)
            ev.skew_ms = ev.server_time_ms - ev.local_time_ms
        except Exception as exc:  # noqa: BLE001
            ev.reachability_error = f"fetch_time: {type(exc).__name__}: {exc}"

        # -- Tier 0: authed balances --
        try:
            balances = await adapter.get_balances()
            ev.balances_ok = True
            ev.balances = [
                {"asset": b.asset, "free": str(b.free), "total": str(b.total)}
                for b in balances
            ]
        except Exception as exc:  # noqa: BLE001
            ev.balances_error = f"{type(exc).__name__}: {exc}"

        # -- Tier 1: round-trip order (opt-in) --
        ev.tier1_enabled = os.environ.get("CLAY_BYBIT_SMOKE_PLACE_ORDER", "") == "1"
        if not ev.tier1_enabled:
            return ev

        symbol = os.environ.get("CLAY_BYBIT_SMOKE_SYMBOL", "BTC/USDT")
        ev.symbol = symbol
        client_order_id = f"smoke-demo-{int(time.time() * 1000)}"
        ev.client_order_id_sent = client_order_id

        # Minimal LIMIT order far from market (should not fill).
        req = OrderRequest(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            time_in_force=TimeInForce.GTC,
            client_order_id=client_order_id,
            price=Decimal("1.00"),
        )

        try:
            t0 = time.perf_counter()
            ev.place_result = await adapter.place_order(req)
            ev.place_latency_ms = (time.perf_counter() - t0) * 1000
            ev.venue_order_id_returned = ev.place_result.venue_order_id

            # Fetch order snapshot to compare clientOrderId vs orderLinkId.
            try:
                snap = await adapter.get_order(symbol, ev.venue_order_id_returned)
                ev.snapshot_client_order_id = snap.client_order_id

                # Raw info.orderLinkId from the venue response.
                raw = await adapter._client.fetch_order(
                    id=ev.venue_order_id_returned, symbol=symbol
                )
                info = raw.get("info") or {}
                ev.raw_orderLinkId = str(info.get("orderLinkId", ""))

                ev.orderLinkId_match = ev.client_order_id_sent == ev.raw_orderLinkId
            except Exception as exc:  # noqa: BLE001
                ev.tier1_error = f"snapshot: {type(exc).__name__}: {exc}"

            # Cancel the order.
            t0 = time.perf_counter()
            await adapter.cancel_order(
                symbol=symbol, venue_order_id=ev.venue_order_id_returned
            )
            ev.cancel_latency_ms = (time.perf_counter() - t0) * 1000
            ev.cancel_ok = True
        except Exception as exc:  # noqa: BLE001
            ev.tier1_error = f"{type(exc).__name__}: {exc}"
            # Attempt cancel on best-effort basis.
            if ev.venue_order_id_returned:
                try:
                    await adapter.cancel_order(
                        symbol=symbol, venue_order_id=ev.venue_order_id_returned
                    )
                except Exception:  # noqa: BLE001
                    pass
    finally:
        await adapter.close()

    return ev


def _evidence_to_dict(ev: SmokeEvidence) -> dict[str, Any]:
    d: dict[str, Any] = {
        "symbol": ev.symbol,
        "tier0": {
            "reachability_ok": ev.reachability_ok,
            "reachability_error": ev.reachability_error,
            "server_time_ms": ev.server_time_ms,
            "local_time_ms": ev.local_time_ms,
            "skew_ms": ev.skew_ms,
            "balances_ok": ev.balances_ok,
            "balances_error": ev.balances_error,
            "balances_count": len(ev.balances),
        },
        "tier1": {
            "enabled": ev.tier1_enabled,
        },
        "error": ev.error,
    }
    if ev.tier1_enabled:
        d["tier1"].update(
            {
                "client_order_id_sent": ev.client_order_id_sent,
                "venue_order_id_returned": ev.venue_order_id_returned,
                "snapshot_client_order_id": ev.snapshot_client_order_id,
                "raw_orderLinkId": ev.raw_orderLinkId,
                "orderLinkId_match": ev.orderLinkId_match,
                "cancel_ok": ev.cancel_ok,
                "cancel_error": ev.cancel_error,
                "place_latency_ms": round(ev.place_latency_ms, 2),
                "cancel_latency_ms": round(ev.cancel_latency_ms, 2),
                "tier1_error": ev.tier1_error,
            }
        )
    return d


def main() -> int:
    if _env() is None:
        return 0
    evidence = asyncio.run(_run())
    result = _evidence_to_dict(evidence)
    print(json.dumps(result, indent=2))

    path = _evidence_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[evidence] written to {path}")
    return 1 if evidence.error else 0


def run_smoke() -> SmokeEvidence:
    if _env() is None:
        return SmokeEvidence(error="missing credentials")
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
