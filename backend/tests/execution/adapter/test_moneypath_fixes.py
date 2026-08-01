"""Golden-эталонные регресс-тесты D-42/D-43/D-44 (S-MONEYPATH-2).

Источник эталонов: DRILL S-MONEYPATH-1b, 2026-08-01, testnet.binance.vision.
Фикстуры — verbatim unified-ответы ccxt (unified dict + raw info).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from clay.execution.adapter.binance import BinanceExecutionAdapter
from clay.execution.adapter.ccxt_base import CcxtExchangeAdapter
from clay.execution.adapter.ccxt_client import CcxtSpotClient
from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    Environment,
    OrderSide,
    OrderState,
    OrderType,
    TimeInForce,
)
from clay.execution.adapter.errors import InvalidOrderError
from clay.execution.adapter.rules import MarketRules
from tests.execution.adapter.test_binance import FakeBinanceClient, _make_binance_market

# ---------------------------------------------------------------------------
# Golden-эталоны (DRILL S-MONEYPATH-1b, testnet.binance.vision, 2026-08-01)
# ---------------------------------------------------------------------------


GOLDEN_C_UNIFIED: dict[str, Any] = {
    "info": {
        "symbol": "BTCUSDT",
        "orderId": "22668468",
        "orderListId": "-1",
        "clientOrderId": "sm-c-1785595871214",
        "transactTime": "1785595871461",
        "price": "66496.13000000",
        "origQty": "0.00009000",
        "executedQty": "0.00000000",
        "cummulativeQuoteQty": "0.00000000",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "STOP_LOSS_LIMIT",
        "side": "BUY",
        "stopPrice": "66629.39000000",
        "workingTime": "-1",
        "fills": [],
        "selfTradePreventionMode": "EXPIRE_MAKER",
    },
    "id": "22668468",
    "clientOrderId": "sm-c-1785595871214",
    "timestamp": -1,
    "lastUpdateTimestamp": 1785595871461,
    "symbol": "BTC/USDT",
    "type": "limit",
    "side": "buy",
    "price": 66496.13,
    "triggerPrice": 66629.39,
    "stopPrice": 66629.39,
    "amount": 9e-05,
    "filled": 0.0,
    "status": "open",
}


GOLDEN_A_UNIFIED: dict[str, Any] = {
    "info": {
        "symbol": "BTCUSDT",
        "orderId": "22668465",
        "orderListId": "-1",
        "clientOrderId": "sm-a-1785595869820",
        "transactTime": "1785595870756",
        "price": "0.00000000",
        "origQty": "0.00009000",
        "executedQty": "0.00009000",
        "cummulativeQuoteQty": "5.67864090",
        "status": "FILLED",
        "timeInForce": "GTC",
        "type": "MARKET",
        "side": "BUY",
        "workingTime": "1785595870756",
        "fills": [
            {
                "price": "63096.01000000",
                "qty": "0.00009000",
                "commission": "0.00000000",
                "commissionAsset": "BTC",
                "tradeId": "5958692",
            }
        ],
        "selfTradePreventionMode": "EXPIRE_MAKER",
    },
    "id": "22668465",
    "clientOrderId": "sm-a-1785595869820",
    "timestamp": 1785595870756,
    "lastUpdateTimestamp": 1785595870756,
    "symbol": "BTC/USDT",
    "type": "market",
    "side": "buy",
    "price": 63096.01,
    "triggerPrice": None,
    "stopPrice": None,
    "amount": 9e-05,
    "filled": 9e-05,
    "status": "closed",
}


GOLDEN_B_UNIFIED: dict[str, Any] = {
    "info": {
        "symbol": "BTCUSDT",
        "orderId": "22668467",
        "orderListId": "-1",
        "clientOrderId": "sm-b-1785595870896",
        "transactTime": "1785595871072",
        "price": "56786.41000000",
        "origQty": "0.00009000",
        "executedQty": "0.00000000",
        "cummulativeQuoteQty": "0.00000000",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "BUY",
        "workingTime": "1785595871072",
        "fills": [],
        "selfTradePreventionMode": "EXPIRE_MAKER",
    },
    "id": "22668467",
    "clientOrderId": "sm-b-1785595870896",
    "timestamp": 1785595871072,
    "lastUpdateTimestamp": 1785595871072,
    "symbol": "BTC/USDT",
    "type": "limit",
    "side": "buy",
    "price": 56786.41,
    "triggerPrice": None,
    "stopPrice": None,
    "amount": 9e-05,
    "filled": 0.0,
    "status": "open",
}


# ---------------------------------------------------------------------------
# Стаб: доступ к read-mapping базового адаптера
# ---------------------------------------------------------------------------


class _StubAdapter(CcxtExchangeAdapter):
    supported_order_types = frozenset(
        {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}
    )
    supported_tif = frozenset({TimeInForce.GTC})

    def _build_client(self, api_key: str, api_secret: str) -> CcxtSpotClient:
        return MagicMock()

    def _is_duplicate_cid(self, exc: Exception) -> bool:
        return False

    def _build_order_params(self, req: OrderRequest) -> dict[str, Any]:
        return {}

    async def get_market_rules(self, symbol: str) -> MarketRules:
        raise NotImplementedError


def _stop_request() -> OrderRequest:
    return OrderRequest(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.STOP_LIMIT,
        quantity=Decimal("0.00009"),
        time_in_force=TimeInForce.GTC,
        client_order_id="sm-c-1785595871214",
        price=Decimal("66496.13"),
        stop_price=Decimal("66629.39"),
    )


def _adapter() -> _StubAdapter:
    return _StubAdapter(Environment.TESTNET)


# ---------------------------------------------------------------------------
# D-43 — стоп-характер не теряется в read-mapping
# ---------------------------------------------------------------------------


class TestD43StopLimit:
    def test_d43_ack_preserves_stop_limit(self) -> None:
        ack = _adapter()._ack_from_response(
            "sm-c-1785595871214", GOLDEN_C_UNIFIED, requested=_stop_request()
        )
        assert ack.order_type == OrderType.STOP_LIMIT
        assert ack.state == OrderState.NEW

    def test_d43_snapshot_preserves_stop_limit(self) -> None:
        snap = _adapter()._snapshot_from_response(GOLDEN_C_UNIFIED)
        assert snap.order_type == OrderType.STOP_LIMIT

    def test_d43_market_and_limit_unchanged(self) -> None:
        ack_a = _adapter()._ack_from_response("cid-a", GOLDEN_A_UNIFIED, requested=None)
        ack_b = _adapter()._ack_from_response("cid-b", GOLDEN_B_UNIFIED, requested=None)
        assert ack_a.order_type == OrderType.MARKET
        assert ack_a.state == OrderState.FILLED
        assert ack_b.order_type == OrderType.LIMIT
        assert ack_b.state == OrderState.NEW


# ---------------------------------------------------------------------------
# D-44 — transact_time не уезжает в -1
# ---------------------------------------------------------------------------


class TestD44TransactTime:
    def test_d44_ack_recovers_transact_time(self) -> None:
        ack = _adapter()._ack_from_response(
            "sm-c-1785595871214", GOLDEN_C_UNIFIED, requested=_stop_request()
        )
        assert ack.transact_time == 1785595871461

    def test_d44_snapshot_recovers_transact_time(self) -> None:
        snap = _adapter()._snapshot_from_response(GOLDEN_C_UNIFIED)
        assert snap.transact_time == 1785595871461

    def test_d44_fills_reject_negative_sentinel(self) -> None:
        resp: dict[str, Any] = {
            "symbol": "BTC/USDT",
            "id": "o1",
            "trades": [
                {"id": "t1", "amount": "0.00009", "price": "63096.01", "timestamp": -1}
            ],
        }
        fills = _adapter()._fills_from_trades(resp)
        assert len(fills) == 1
        assert fills[0].transact_time == 0


# ---------------------------------------------------------------------------
# D-42 — get_market_rules принимает и unified, и market-id
# ---------------------------------------------------------------------------


class TestD42MarketId:
    @pytest.mark.anyio
    async def test_d42_get_market_rules_accepts_market_id(self) -> None:
        client = FakeBinanceClient()
        client._markets = {"BTCUSDT": _make_binance_market()}
        adapter = BinanceExecutionAdapter(Environment.PRODUCTION, client=client)

        rules_by_id = await adapter.get_market_rules("BTCUSDT")
        rules_unified = await adapter.get_market_rules("BTC/USDT")

        assert rules_by_id.min_amount == Decimal("0.001")
        assert rules_unified.min_amount == Decimal("0.001")
        assert rules_by_id.amount_step == Decimal("0.001")

        with pytest.raises(InvalidOrderError):
            await adapter.get_market_rules("NOPE/USDT")
