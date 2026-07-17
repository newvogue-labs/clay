"""Тесты ExecutionProofGate — admit→delegate, DENY→error, persist-fail→503."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import (
    Environment,
    OrderSide,
    OrderState,
    OrderType,
    PrecisionMode,
    TimeInForce,
)
from clay.execution.adapter.rules import MarketRules
from clay.execution.proof.errors import ProofGateDeniedError, ProofGatePersistError
from clay.execution.proof.gate import ExecutionProofGate
from clay.execution.proof.snapshot import FreshnessPolicy, SessionMode

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
    supported_order_types=frozenset({OrderType.MARKET, OrderType.LIMIT}),
    supported_tif=frozenset({TimeInForce.GTC}),
)

DEFAULT_POLICY = FreshnessPolicy(max_age_seconds=300)


def _make_request(**overrides: object) -> OrderRequest:
    defaults: dict[str, object] = dict(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        time_in_force=TimeInForce.GTC,
        client_order_id="test-gate-001",
        price=Decimal("50000"),
    )
    defaults.update(overrides)  # type: ignore[arg-type]
    return OrderRequest(**defaults)  # type: ignore[call-overload]


class FakeInner:
    """Минимальный inner adapter для тестов гейта."""

    def __init__(self) -> None:
        self.place_order_called = False
        self.get_balances_called = False
        self.get_open_orders_called = False
        self.environment = Environment.TESTNET

    async def get_market_rules(self, symbol: str) -> MarketRules:
        return DEFAULT_RULES

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        pass

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        return req

    async def place_order(self, req: OrderRequest) -> OrderAck:
        self.place_order_called = True
        return OrderAck(
            client_order_id=req.client_order_id,
            venue_order_id="exch_001",
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            order_type=req.order_type,
            state=OrderState.FILLED,
            transact_time=int(NOW.timestamp() * 1000),
            price=req.price,
            fills=(),
        )

    async def cancel_order(self, symbol: str, venue_order_id: str) -> None:
        pass

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        raise NotImplementedError

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return []

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return []

    async def get_balances(self) -> list[BalanceSnapshot]:
        self.get_balances_called = True
        return []


class TestGateAdmit:
    @pytest.mark.asyncio
    async def test_admit_delegates_to_inner(self) -> None:
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_admit_persists_record(self) -> None:
        inner = FakeInner()
        mock_sf = MagicMock()
        mock_session = MagicMock()
        mock_sf.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.__exit__ = MagicMock(return_value=False)
        gate = ExecutionProofGate(
            inner,
            session_factory=mock_sf,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
        )
        req = _make_request()
        await gate.place_order(req)
        mock_session.commit.assert_called_once()


class TestGateDeny:
    @pytest.mark.asyncio
    async def test_deny_raises_error(self) -> None:
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("100"),  # cap active
        )
        # MARKET + cap>0 → DENY
        req = _make_request(order_type=OrderType.MARKET, price=None)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "NOTIONAL_UNCOMPUTABLE" in exc_info.value.reason_codes

    @pytest.mark.asyncio
    async def test_deny_does_not_call_inner(self) -> None:
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("100"),
        )
        req = _make_request(order_type=OrderType.MARKET, price=None)
        with pytest.raises(ProofGateDeniedError):
            await gate.place_order(req)
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_deny_persists_record(self) -> None:
        inner = FakeInner()
        mock_sf = MagicMock()
        mock_session = MagicMock()
        mock_sf.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.__exit__ = MagicMock(return_value=False)
        gate = ExecutionProofGate(
            inner,
            session_factory=mock_sf,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("100"),
        )
        req = _make_request(order_type=OrderType.MARKET, price=None)
        with pytest.raises(ProofGateDeniedError):
            await gate.place_order(req)
        mock_session.commit.assert_called_once()


class TestGatePersistFail:
    @pytest.mark.asyncio
    async def test_persist_fail_raises_503(self) -> None:
        inner = FakeInner()
        mock_sf = MagicMock()
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("db down")
        mock_sf.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.__exit__ = MagicMock(return_value=False)
        gate = ExecutionProofGate(
            inner,
            session_factory=mock_sf,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
        )
        req = _make_request()
        with pytest.raises(ProofGatePersistError):
            await gate.place_order(req)

    @pytest.mark.asyncio
    async def test_persist_fail_does_not_call_inner(self) -> None:
        inner = FakeInner()
        mock_sf = MagicMock()
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("db down")
        mock_sf.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.__exit__ = MagicMock(return_value=False)
        gate = ExecutionProofGate(
            inner,
            session_factory=mock_sf,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
        )
        req = _make_request()
        with pytest.raises(ProofGatePersistError):
            await gate.place_order(req)
        assert not inner.place_order_called


class TestGateDelegation:
    def test_environment_delegates(self) -> None:
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
        )
        assert gate.environment == Environment.TESTNET

    @pytest.mark.asyncio
    async def test_get_market_rules_delegates(self) -> None:
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
        )
        rules = await gate.get_market_rules("BTC/USDT")
        assert rules == DEFAULT_RULES

    def test_quantize_order_delegates(self) -> None:
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
        )
        req = _make_request()
        result = gate.quantize_order(req, DEFAULT_RULES)
        assert result == req


class TestGateEnforcePortfolio:
    @pytest.mark.asyncio
    async def test_enforce_false_no_get_balances(self) -> None:
        """enforce_portfolio=False → get_balances() не вызывается."""
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_portfolio=False,
        )
        req = _make_request()
        await gate.place_order(req)
        assert not inner.get_balances_called

    @pytest.mark.asyncio
    async def test_enforce_true_oversell_denies(self) -> None:
        """enforce_portfolio=True + insufficient free → ProofGateDeniedError."""
        inner = FakeInner()

        async def rich_balances() -> list:
            return [
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("0"),
                    locked=Decimal("0"),
                    total=Decimal("0"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("100"),
                    locked=Decimal("0"),
                    total=Decimal("100"),
                ),
            ]

        inner.get_balances = rich_balances  # type: ignore[assignment]
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_portfolio=True,
        )
        # BUY 0.1 BTC @ 50000 = 5000 USDT; free=100 → DENY
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("0.1"), price=Decimal("50000")
        )
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "INSUFFICIENT_FREE_BALANCE" in exc_info.value.reason_codes

    @pytest.mark.asyncio
    async def test_enforce_true_within_free_admits(self) -> None:
        """enforce_portfolio=True + enough free → ADMIT + delegate."""
        inner = FakeInner()

        async def rich_balances() -> list:
            return [
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("1"),
                    locked=Decimal("0"),
                    total=Decimal("1"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("100000"),
                    locked=Decimal("0"),
                    total=Decimal("100000"),
                ),
            ]

        inner.get_balances = rich_balances  # type: ignore[assignment]
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_portfolio=True,
        )
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("0.1"), price=Decimal("50000")
        )
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"


class TestGatePositionCap:
    @pytest.mark.asyncio
    async def test_enforce_true_cap_over_denies(self) -> None:
        """enforce_portfolio=True + max_position over → ProofGateDeniedError."""
        inner = FakeInner()

        async def balances_with_btc() -> list:
            return [
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("1"),
                    locked=Decimal("0"),
                    total=Decimal("1"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("100000"),
                    locked=Decimal("0"),
                    total=Decimal("100000"),
                ),
            ]

        inner.get_balances = balances_with_btc  # type: ignore[assignment]
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            max_position=Decimal("80000"),
            enforce_portfolio=True,
        )
        # projected = (1 + 1) * 50000 = 100000; cap=80000 → DENY
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("1"), price=Decimal("50000")
        )
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "POSITION_ABOVE_CAP" in exc_info.value.reason_codes

    @pytest.mark.asyncio
    async def test_enforce_false_cap_ignored(self) -> None:
        """enforce_portfolio=False → cap ignored, no get_balances call."""
        inner = FakeInner()
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            max_position=Decimal("1"),
            enforce_portfolio=False,
        )
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("50000")
        )
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not inner.get_balances_called
        assert ack.client_order_id == "test-gate-001"


class TestGateEnforceOpenOrders:
    @pytest.mark.asyncio
    async def test_enforce_true_over_cap_denies(self) -> None:
        """enforce=True + cap=2 + 3 open orders → ProofGateDeniedError[OPEN_ORDERS_ABOVE_CAP]."""
        inner = FakeInner()
        inner.get_open_orders_called = False

        async def balances_rich() -> list:
            return [
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("1"),
                    locked=Decimal("0"),
                    total=Decimal("1"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("100000"),
                    locked=Decimal("0"),
                    total=Decimal("100000"),
                ),
            ]

        async def three_open_orders(symbol: str | None = None) -> list:
            return [
                OrderSnapshot(
                    client_order_id=f"o{i}",
                    venue_order_id=f"v{i}",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    state=OrderState.NEW,
                    quantity=Decimal("0.1"),
                    executed_qty=Decimal(0),
                    price=Decimal("50000"),
                    transact_time=int(NOW.timestamp() * 1000),
                )
                for i in range(3)
            ]

        inner.get_balances = balances_rich  # type: ignore[assignment]

        async def tracking_get_open(symbol: str | None = None) -> list:
            inner.get_open_orders_called = True
            return await three_open_orders(symbol)

        inner.get_open_orders = tracking_get_open  # type: ignore[assignment]

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            max_open_orders=2,
            enforce_portfolio=True,
        )
        req = _make_request(
            side=OrderSide.BUY, quantity=Decimal("0.1"), price=Decimal("50000")
        )
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "OPEN_ORDERS_ABOVE_CAP" in exc_info.value.reason_codes
        assert inner.get_open_orders_called

    @pytest.mark.asyncio
    async def test_enforce_false_no_get_open_orders(self) -> None:
        """enforce=False → get_open_orders not called."""
        inner = FakeInner()
        inner.get_open_orders_called = False

        async def tracking_get_open(symbol: str | None = None) -> list:
            inner.get_open_orders_called = True
            return []

        inner.get_open_orders = tracking_get_open  # type: ignore[assignment]

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            max_open_orders=5,
            enforce_portfolio=False,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not inner.get_open_orders_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_enforce_true_cap_zero_no_get_open_orders(self) -> None:
        """enforce=True + cap=0 → get_open_orders not called (cap off)."""
        inner = FakeInner()
        inner.get_open_orders_called = False

        async def balances_rich() -> list:
            return [
                BalanceSnapshot(
                    asset="BTC",
                    free=Decimal("1"),
                    locked=Decimal("0"),
                    total=Decimal("1"),
                ),
                BalanceSnapshot(
                    asset="USDT",
                    free=Decimal("100000"),
                    locked=Decimal("0"),
                    total=Decimal("100000"),
                ),
            ]

        async def tracking_get_open(symbol: str | None = None) -> list:
            inner.get_open_orders_called = True
            return []

        inner.get_balances = balances_rich  # type: ignore[assignment]
        inner.get_open_orders = tracking_get_open  # type: ignore[assignment]

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            max_open_orders=0,
            enforce_portfolio=True,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not inner.get_open_orders_called
        assert ack.client_order_id == "test-gate-001"


class TestGateEnforceSession:
    @pytest.mark.asyncio
    async def test_enforce_true_probe_engaged_denies(self) -> None:
        """enforce_session=True + probe→True (engaged) → ProofGateDeniedError[KILL_SWITCH_ENGAGED]."""
        inner = FakeInner()
        probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=probe,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "KILL_SWITCH_ENGAGED" in exc_info.value.reason_codes
        assert not inner.place_order_called
        probe.assert_called_once()

    @pytest.mark.asyncio
    async def test_enforce_false_no_probe_call(self) -> None:
        """enforce_session=False → probe never called, delegate succeeds."""
        inner = FakeInner()
        probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=False,
            kill_switch_probe=probe,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not probe.called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_enforce_true_probe_false_admits(self) -> None:
        """enforce_session=True + probe→False → ADMIT + delegate."""
        inner = FakeInner()
        probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=probe,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_enforce_true_probe_none_fail_closed(self) -> None:
        """enforce_session=True + probe=None → fail-closed → DENY[KILL_SWITCH_ENGAGED]."""
        inner = FakeInner()

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=None,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "KILL_SWITCH_ENGAGED" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_enforce_true_probe_raises_fail_closed(self) -> None:
        """enforce_session=True + probe raises → fail-closed → DENY[KILL_SWITCH_ENGAGED]."""
        inner = FakeInner()
        probe = MagicMock(side_effect=RuntimeError("db down"))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=probe,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "KILL_SWITCH_ENGAGED" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_set_kill_switch_probe_late_bind(self) -> None:
        """set_kill_switch_probe wires probe after construction."""
        inner = FakeInner()
        probe_engaged = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
        )
        gate.set_kill_switch_probe(probe_engaged)
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "KILL_SWITCH_ENGAGED" in exc_info.value.reason_codes
        assert not inner.place_order_called
        probe_engaged.assert_called_once()


class TestGateSessionMode:
    @pytest.mark.asyncio
    async def test_halted_mode_denies(self) -> None:
        """enforce_session=True + mode_probe→HALTED → DENY[SESSION_HALTED]."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        mode_probe = MagicMock(return_value=SessionMode.HALTED)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_mode_probe=mode_probe,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_HALTED" in exc_info.value.reason_codes
        assert not inner.place_order_called
        mode_probe.assert_called_once()

    @pytest.mark.asyncio
    async def test_reducing_buy_denies(self) -> None:
        """enforce_session=True + mode_probe→REDUCING + BUY → DENY[SESSION_REDUCE_ONLY]."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        mode_probe = MagicMock(return_value=SessionMode.REDUCING)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_mode_probe=mode_probe,
        )
        req = _make_request(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_REDUCE_ONLY" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_reducing_sell_admits(self) -> None:
        """enforce_session=True + mode_probe→REDUCING + SELL → ADMIT + delegate."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        mode_probe = MagicMock(return_value=SessionMode.REDUCING)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_mode_probe=mode_probe,
        )
        req = _make_request(side=OrderSide.SELL)
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_no_mode_probe_defaults_normal(self) -> None:
        """enforce_session=True + no session_mode_probe → NORMAL → ADMIT."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_mode_probe=None,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_mode_probe_raises_fail_closed_halted(self) -> None:
        """enforce_session=True + mode_probe raises → fail-closed → HALTED → DENY."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        mode_probe = MagicMock(side_effect=RuntimeError("db down"))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_mode_probe=mode_probe,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_HALTED" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_set_session_mode_probe_late_bind(self) -> None:
        """set_session_mode_probe wires probe after construction."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        mode_probe = MagicMock(return_value=SessionMode.HALTED)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
        )
        gate.set_session_mode_probe(mode_probe)
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_HALTED" in exc_info.value.reason_codes
        assert not inner.place_order_called
        mode_probe.assert_called_once()

    @pytest.mark.asyncio
    async def test_enforce_false_no_mode_probe_call(self) -> None:
        """enforce_session=False → mode_probe never called, delegate succeeds."""
        inner = FakeInner()
        mode_probe = MagicMock(return_value=SessionMode.HALTED)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=False,
            session_mode_probe=mode_probe,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not mode_probe.called
        assert ack.client_order_id == "test-gate-001"


class TestGateSessionRisk:
    @pytest.mark.asyncio
    async def test_risk_probe_drawdown_buy_denies(self) -> None:
        """risk_probe=(True,False) + BUY → DENY[SESSION_DRAWDOWN_TRIPPED]."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        risk_probe = MagicMock(return_value=(True, False))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_risk_probe=risk_probe,
        )
        req = _make_request(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DRAWDOWN_TRIPPED" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_risk_probe_drawdown_sell_admits(self) -> None:
        """risk_probe=(True,False) + SELL → ADMIT (reduce bypass)."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        risk_probe = MagicMock(return_value=(True, False))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_risk_probe=risk_probe,
        )
        req = _make_request(side=OrderSide.SELL)
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_risk_probe_raises_fail_closed(self) -> None:
        """risk_probe raises → fail-closed → both tripped → DENY."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        risk_probe = MagicMock(side_effect=RuntimeError("db down"))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_risk_probe=risk_probe,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DRAWDOWN_TRIPPED" in exc_info.value.reason_codes
        assert "SESSION_COOLDOWN_TRIPPED" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_no_risk_probe_no_codes(self) -> None:
        """risk_probe=None → no risk tripped, ADMIT."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_risk_probe=None,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_enforce_false_no_risk_probe_call(self) -> None:
        """enforce_session=False → risk_probe never called."""
        inner = FakeInner()
        risk_probe = MagicMock(return_value=(True, True))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=False,
            session_risk_probe=risk_probe,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not risk_probe.called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_set_session_risk_probe_late_bind(self) -> None:
        """set_session_risk_probe wires probe after construction."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        risk_probe = MagicMock(return_value=(True, False))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
        )
        gate.set_session_risk_probe(risk_probe)
        req = _make_request(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DRAWDOWN_TRIPPED" in exc_info.value.reason_codes
        assert not inner.place_order_called
        risk_probe.assert_called_once()


class TestGateSessionSubmitRate:
    @pytest.mark.asyncio
    async def test_submit_rate_exceeded_buy_denies(self) -> None:
        """submit_rate_probe=True + BUY → DENY[SESSION_SUBMIT_RATE_EXCEEDED]."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        sr_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_submit_rate_probe=sr_probe,
        )
        req = _make_request(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_SUBMIT_RATE_EXCEEDED" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_submit_rate_exceeded_sell_admits(self) -> None:
        """submit_rate_probe=True + SELL → ADMIT (reduce bypass)."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        sr_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_submit_rate_probe=sr_probe,
        )
        req = _make_request(side=OrderSide.SELL)
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_submit_rate_probe_raises_fail_closed(self) -> None:
        """submit_rate_probe raises → fail-closed → exceeded → DENY."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        sr_probe = MagicMock(side_effect=RuntimeError("db down"))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_submit_rate_probe=sr_probe,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_SUBMIT_RATE_EXCEEDED" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_no_submit_rate_probe_no_codes(self) -> None:
        """submit_rate_probe=None → no exceeded, ADMIT."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_submit_rate_probe=None,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_enforce_false_no_submit_rate_probe_call(self) -> None:
        """enforce_session=False → submit_rate_probe never called."""
        inner = FakeInner()
        sr_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=False,
            session_submit_rate_probe=sr_probe,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not sr_probe.called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_set_session_submit_rate_probe_late_bind(self) -> None:
        """set_session_submit_rate_probe wires probe after construction."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        sr_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
        )
        gate.set_session_submit_rate_probe(sr_probe)
        req = _make_request(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_SUBMIT_RATE_EXCEEDED" in exc_info.value.reason_codes
        assert not inner.place_order_called
        sr_probe.assert_called_once()


class TestGateSessionDuplicateIntent:
    @pytest.mark.asyncio
    async def test_duplicate_intent_buy_denies(self) -> None:
        """duplicate_intent_probe=True + BUY → DENY[SESSION_DUPLICATE_INTENT]."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = _make_request(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DUPLICATE_INTENT" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_duplicate_intent_sell_also_denies(self) -> None:
        """duplicate_intent_probe=True + SELL → DENY (no reduce-bypass)."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = _make_request(side=OrderSide.SELL)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DUPLICATE_INTENT" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_duplicate_intent_probe_raises_fail_closed(self) -> None:
        """duplicate_intent_probe raises → fail-closed → duplicate → DENY."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(side_effect=RuntimeError("db down"))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = _make_request()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DUPLICATE_INTENT" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_no_duplicate_intent_probe_no_codes(self) -> None:
        """duplicate_intent_probe=None → no duplicate, ADMIT."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=None,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_enforce_false_no_duplicate_probe_call(self) -> None:
        """enforce_session=False → duplicate_intent_probe never called."""
        inner = FakeInner()
        di_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=False,
            session_duplicate_intent_probe=di_probe,
        )
        req = _make_request()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not di_probe.called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_set_session_duplicate_intent_probe_late_bind(self) -> None:
        """set_session_duplicate_intent_probe wires probe after construction."""
        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=DEFAULT_POLICY,
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
        )
        gate.set_session_duplicate_intent_probe(di_probe)
        req = _make_request(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DUPLICATE_INTENT" in exc_info.value.reason_codes
        assert not inner.place_order_called
        di_probe.assert_called_once()
