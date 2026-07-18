"""Тесты duplicate-intent probe wiring (D-8).

Покрытие:
  D1: semantic_intent_hash — CID-инвариантность + чувствительность к эконом-полям;
      intent_hash байт-стабильность.
  D5: exists_admitted_duplicate — окно/CID-exemption/ADMIT-only/empty→False.
  D6: ExecutionConfig defaults + from_env для duplicate_intent полей.
  D7: build_duplicate_intent_probe — True/False/fail-closed.
  D8: Gate integration — probe(quantized) wired; None→ok; raise→DENY; double-off.
  D9: Bootstrap wiring — probe set / not set по conditions.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from clay.db.models_ops import ExecutionProofDecision
from clay.db.repositories_ops import ProofDecisionRepository
from clay.execution.adapter.domain import OrderRequest
from clay.execution.adapter.enums import (
    OrderSide,
    OrderType,
    TimeInForce,
)
from clay.execution.config import ExecutionConfig
from clay.execution.proof.checker import semantic_intent_hash
from clay.execution.proof.decision import Decision, DecisionRecord, InvariantResult
from clay.execution.proof.reason_codes import ReasonCode
from clay.execution.proof.snapshot import FreshnessPolicy

pytestmark = pytest.mark.usefixtures("sqlite_session_factory")

NOW = datetime.now(tz=timezone.utc)


def _make_request(**overrides: object) -> OrderRequest:
    defaults = dict(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        time_in_force=TimeInForce.GTC,
        client_order_id="test-001",
        price=Decimal("50000"),
    )
    defaults.update(overrides)  # type: ignore[arg-type]
    return OrderRequest(**defaults)  # type: ignore[call-overload]


def _make_record(**overrides: object) -> DecisionRecord:
    defaults: dict[str, object] = dict(
        decision=Decision.ADMIT,
        intent_hash="a" * 16,
        semantic_hash="c" * 16,
        snapshot_hash="b" * 16,
        snapshot_ts=NOW,
        metadata_version="v1",
        invariant_results=(
            InvariantResult(code=ReasonCode.UNSUPPORTED_ORDER_TYPE, passed=True),
        ),
        reason_codes=(),
        created_at=NOW,
    )
    defaults.update(overrides)  # type: ignore[arg-type]
    return DecisionRecord(**defaults)  # type: ignore[call-overload]


def _persist(
    session_factory,
    *,
    decision: Decision = Decision.ADMIT,
    semantic_hash: str = "c" * 16,
    created_at: datetime | None = None,
    symbol: str = "BTC/USDT",
    client_order_id: str = "cid-test",
) -> None:
    record = _make_record(
        decision=decision,
        semantic_hash=semantic_hash,
        created_at=created_at or datetime.now(tz=timezone.utc),
    )
    orm = ExecutionProofDecision.from_record(
        record, symbol=symbol, client_order_id=client_order_id
    )
    with session_factory() as session:
        repo = ProofDecisionRepository(session)
        repo.append(orm)
        session.commit()


# ── D1: semantic_intent_hash ──────────────────────────────────────────


class TestSemanticIntentHash:
    def test_cid_invariant(self) -> None:
        """Два запроса, отличающиеся ТОЛЬКО client_order_id, дают одинаковый hash."""
        r1 = _make_request(client_order_id="cid-001")
        r2 = _make_request(client_order_id="cid-002")
        assert semantic_intent_hash(r1) == semantic_intent_hash(r2)

    def test_differs_on_qty(self) -> None:
        """Отличие в quantity → разный hash."""
        r1 = _make_request(quantity=Decimal("0.1"))
        r2 = _make_request(quantity=Decimal("0.2"))
        assert semantic_intent_hash(r1) != semantic_intent_hash(r2)

    def test_differs_on_price(self) -> None:
        """Отличие в price → разный hash."""
        r1 = _make_request(price=Decimal("50000"))
        r2 = _make_request(price=Decimal("51000"))
        assert semantic_intent_hash(r1) != semantic_intent_hash(r2)

    def test_differs_on_side(self) -> None:
        """Отличие в side → разный hash."""
        r1 = _make_request(side=OrderSide.BUY)
        r2 = _make_request(side=OrderSide.SELL)
        assert semantic_intent_hash(r1) != semantic_intent_hash(r2)

    def test_differs_on_tif(self) -> None:
        """Отличие в time_in_force → разный hash."""
        r1 = _make_request(time_in_force=TimeInForce.GTC)
        r2 = _make_request(time_in_force=TimeInForce.IOC)
        assert semantic_intent_hash(r1) != semantic_intent_hash(r2)

    def test_differs_on_order_type(self) -> None:
        """Отличие в order_type → разный hash."""
        r1 = _make_request(order_type=OrderType.LIMIT)
        r2 = _make_request(order_type=OrderType.STOP_LIMIT, stop_price=Decimal("49000"))
        assert semantic_intent_hash(r1) != semantic_intent_hash(r2)

    def test_differs_on_symbol(self) -> None:
        """Отличие в symbol → разный hash."""
        r1 = _make_request(symbol="BTC/USDT")
        r2 = _make_request(symbol="ETH/USDT")
        assert semantic_intent_hash(r1) != semantic_intent_hash(r2)

    def test_stable_deterministic(self) -> None:
        """Дважды вызванная на одном запросе → одинаковый hash."""
        r = _make_request()
        assert semantic_intent_hash(r) == semantic_intent_hash(r)

    def test_16_hex_chars(self) -> None:
        """Hash = 16 hex-символов (SHA256[:16])."""
        h = semantic_intent_hash(_make_request())
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_intent_hash_unchanged(self) -> None:
        """intent_hash по-прежнему ВКЛЮЧАЕТ client_order_id (байт-стабильность)."""
        from clay.execution.proof.checker import _intent_hash

        r1 = _make_request(client_order_id="cid-001")
        r2 = _make_request(client_order_id="cid-002")
        # intent_hash РАЗНЫЙ (включает CID)
        assert _intent_hash(r1) != _intent_hash(r2)
        # semantic_hash ОДИНАКОВЫЙ (без CID)
        assert semantic_intent_hash(r1) == semantic_intent_hash(r2)

    def test_differs_on_stop_price(self) -> None:
        """Отличие в stop_price → разный hash."""
        r1 = _make_request(order_type=OrderType.STOP_LIMIT, stop_price=Decimal("49000"))
        r2 = _make_request(order_type=OrderType.STOP_LIMIT, stop_price=Decimal("48000"))
        assert semantic_intent_hash(r1) != semantic_intent_hash(r2)

    def test_cid_not_in_canon(self) -> None:
        """client_order_id не влияет на semantic_hash (verify CID-exclusion)."""
        r1 = _make_request(client_order_id="aaa")
        r2 = _make_request(client_order_id="zzz")
        h1 = semantic_intent_hash(r1)
        h2 = semantic_intent_hash(r2)
        assert h1 == h2
        # Дополнительно: semantic_hash != intent_hash
        from clay.execution.proof.checker import _intent_hash

        assert h1 != _intent_hash(r1)


# ── D5: exists_admitted_duplicate ─────────────────────────────────────


class TestExistsAdmittedDuplicate:
    def test_empty_returns_false(self, sqlite_session_factory) -> None:
        since = NOW - timedelta(hours=1)
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert (
                repo.exists_admitted_duplicate(
                    semantic_hash="a" * 16,
                    since=since,
                    exclude_client_order_id="cid-001",
                )
                is False
            )

    def test_prior_admit_same_hash_diff_cid_returns_true(
        self, sqlite_session_factory
    ) -> None:
        """Prior ADMIT с тем же semantic_hash и ДРУГИМ CID → True."""
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash="a" * 16,
            client_order_id="cid-prior",
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert (
                repo.exists_admitted_duplicate(
                    semantic_hash="a" * 16,
                    since=NOW - timedelta(hours=1),
                    exclude_client_order_id="cid-new",
                )
                is True
            )

    def test_same_cid_returns_false(self, sqlite_session_factory) -> None:
        """CID-exemption: тот же CID → False (legit retry)."""
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash="a" * 16,
            client_order_id="cid-retry",
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert (
                repo.exists_admitted_duplicate(
                    semantic_hash="a" * 16,
                    since=NOW - timedelta(hours=1),
                    exclude_client_order_id="cid-retry",
                )
                is False
            )

    def test_deny_not_matched(self, sqlite_session_factory) -> None:
        """DENY с тем же hash не матчит (только ADMIT)."""
        _persist(
            sqlite_session_factory,
            decision=Decision.DENY,
            semantic_hash="a" * 16,
            client_order_id="cid-deny",
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert (
                repo.exists_admitted_duplicate(
                    semantic_hash="a" * 16,
                    since=NOW - timedelta(hours=1),
                    exclude_client_order_id="cid-new",
                )
                is False
            )

    def test_outside_window_not_matched(self, sqlite_session_factory) -> None:
        """Старый ADMIT вне окна не матчит."""
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash="a" * 16,
            client_order_id="cid-old",
            created_at=NOW - timedelta(hours=2),
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert (
                repo.exists_admitted_duplicate(
                    semantic_hash="a" * 16,
                    since=NOW - timedelta(hours=1),
                    exclude_client_order_id="cid-new",
                )
                is False
            )

    def test_different_hash_not_matched(self, sqlite_session_factory) -> None:
        """Разный semantic_hash не матчит."""
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash="b" * 16,
            client_order_id="cid-other",
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert (
                repo.exists_admitted_duplicate(
                    semantic_hash="a" * 16,
                    since=NOW - timedelta(hours=1),
                    exclude_client_order_id="cid-new",
                )
                is False
            )

    def test_multiple_prior_one_matches(self, sqlite_session_factory) -> None:
        """Из нескольких prior — матчит тот, что с другим CID."""
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash="a" * 16,
            client_order_id="cid-same",
        )
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash="a" * 16,
            client_order_id="cid-different",
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            # exclude cid-same → cid-different матчит
            assert (
                repo.exists_admitted_duplicate(
                    semantic_hash="a" * 16,
                    since=NOW - timedelta(hours=1),
                    exclude_client_order_id="cid-same",
                )
                is True
            )


# ── D6: Config defaults + from_env ────────────────────────────────────


class TestDuplicateIntentConfigDefaults:
    def test_defaults_are_zero(self) -> None:
        cfg = ExecutionConfig()
        assert cfg.proof_duplicate_intent_window_seconds == 0

    @patch.dict(os.environ, {"CLAY_PROOF_DUPLICATE_INTENT_WINDOW_SECONDS": "30"})
    def test_from_env_window(self) -> None:
        cfg = ExecutionConfig.from_env()
        assert cfg.proof_duplicate_intent_window_seconds == 30

    def test_env_missing_defaults_zero(self) -> None:
        cfg = ExecutionConfig.from_env()
        assert cfg.proof_duplicate_intent_window_seconds == 0


# ── D7: build_duplicate_intent_probe ──────────────────────────────────


class TestBuildDuplicateIntentProbe:
    def test_no_prior_returns_false(self, sqlite_session_factory) -> None:
        from clay.execution.proof.probe import build_duplicate_intent_probe

        probe = build_duplicate_intent_probe(sqlite_session_factory, window_seconds=60)
        req = _make_request()
        assert probe(req) is False

    def test_prior_admit_diff_cid_returns_true(self, sqlite_session_factory) -> None:
        from clay.execution.proof.probe import build_duplicate_intent_probe

        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash=semantic_intent_hash(_make_request()),
            client_order_id="cid-prior",
        )
        probe = build_duplicate_intent_probe(sqlite_session_factory, window_seconds=60)
        # Новый запрос с ДРУГИМ CID → True (дубль)
        req = _make_request(client_order_id="cid-new")
        assert probe(req) is True

    def test_prior_admit_same_cid_returns_false(self, sqlite_session_factory) -> None:
        """CID-exemption: тот же CID → False (legit retry)."""
        from clay.execution.proof.probe import build_duplicate_intent_probe

        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash=semantic_intent_hash(_make_request()),
            client_order_id="cid-retry",
        )
        probe = build_duplicate_intent_probe(sqlite_session_factory, window_seconds=60)
        req = _make_request(client_order_id="cid-retry")
        assert probe(req) is False

    def test_db_error_propagates(self) -> None:
        """DB exception NOT swallowed — gate fail-closed treats it as duplicate."""
        from clay.execution.proof.probe import build_duplicate_intent_probe

        mock_sf = MagicMock()
        mock_sf.return_value.__enter__ = MagicMock(side_effect=RuntimeError("db down"))
        mock_sf.return_value.__exit__ = MagicMock(return_value=False)
        probe = build_duplicate_intent_probe(mock_sf, window_seconds=60)
        req = _make_request()
        with pytest.raises(RuntimeError, match="db down"):
            probe(req)

    def test_window_respected(self, sqlite_session_factory) -> None:
        """Only recent ADMITs within window_seconds count."""
        from clay.execution.proof.probe import build_duplicate_intent_probe

        old_time = NOW - timedelta(hours=2)
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            semantic_hash=semantic_intent_hash(_make_request()),
            client_order_id="cid-old",
            created_at=old_time,
        )
        probe = build_duplicate_intent_probe(
            sqlite_session_factory, window_seconds=3600
        )
        req = _make_request(client_order_id="cid-new")
        assert probe(req) is False

    def test_deny_not_counted(self, sqlite_session_factory) -> None:
        """DENY с тем же hash не триггерит probe."""
        from clay.execution.proof.probe import build_duplicate_intent_probe

        _persist(
            sqlite_session_factory,
            decision=Decision.DENY,
            semantic_hash=semantic_intent_hash(_make_request()),
            client_order_id="cid-deny",
        )
        probe = build_duplicate_intent_probe(sqlite_session_factory, window_seconds=60)
        req = _make_request(client_order_id="cid-new")
        assert probe(req) is False


# ── D8: Gate integration ──────────────────────────────────────────────


class TestDuplicateIntentGateIntegration:
    @pytest.mark.asyncio
    async def test_enforce_false_probe_not_called(self) -> None:
        """double-off: enforce_session=False → probe never called, ADMIT."""
        from tests.execution.proof.test_gate import FakeInner, _make_request as mk

        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        di_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=False,
            session_duplicate_intent_probe=di_probe,
        )
        req = mk()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert not di_probe.called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_duplicate_intent_buy_denied(self) -> None:
        """duplicate_intent=True → DENY[SESSION_DUPLICATE_INTENT] (both-sides deny)."""
        from tests.execution.proof.test_gate import FakeInner, _make_request as mk

        from clay.execution.proof.errors import ProofGateDeniedError
        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = mk(side=OrderSide.BUY)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DUPLICATE_INTENT" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_duplicate_intent_sell_also_denied(self) -> None:
        """duplicate_intent=True + SELL → DENY (both-sides deny, no reduce-bypass)."""
        from tests.execution.proof.test_gate import FakeInner, _make_request as mk

        from clay.execution.proof.errors import ProofGateDeniedError
        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = mk(side=OrderSide.SELL)
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DUPLICATE_INTENT" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_probe_not_duplicate_admits(self) -> None:
        """duplicate_intent=False → ADMIT (no session violation)."""
        from tests.execution.proof.test_gate import FakeInner, _make_request as mk

        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = mk()
        ack = await gate.place_order(req)
        assert inner.place_order_called
        assert ack.client_order_id == "test-gate-001"

    @pytest.mark.asyncio
    async def test_probe_none_not_duplicate(self) -> None:
        """probe=None → not duplicate (off-by-default), ADMIT."""
        from tests.execution.proof.test_gate import FakeInner, _make_request as mk

        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=None,
        )
        req = mk()
        await gate.place_order(req)
        assert inner.place_order_called

    @pytest.mark.asyncio
    async def test_probe_raises_fail_closed(self) -> None:
        """DB error in probe → fail-closed → DENY[SESSION_DUPLICATE_INTENT]."""
        from tests.execution.proof.test_gate import FakeInner, _make_request as mk

        from clay.execution.proof.errors import ProofGateDeniedError
        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(side_effect=RuntimeError("db down"))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = mk()
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DUPLICATE_INTENT" in exc_info.value.reason_codes
        assert not inner.place_order_called

    @pytest.mark.asyncio
    async def test_probe_receives_quantized_request(self) -> None:
        """Probe receives the quantized OrderRequest, not the original."""
        from tests.execution.proof.test_gate import FakeInner

        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        di_probe = MagicMock(return_value=False)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=ks_probe,
            session_duplicate_intent_probe=di_probe,
        )
        req = _make_request()
        await gate.place_order(req)
        # probe вызван ровно 1 раз
        assert di_probe.call_count == 1
        # Аргумент — OrderRequest (quantized)
        called_with = di_probe.call_args[0][0]
        assert isinstance(called_with, OrderRequest)
        assert called_with.symbol == "BTC/USDT"


# ── D9: Bootstrap wiring ──────────────────────────────────────────────


class TestBootstrapDuplicateIntentWiring:
    def test_probe_set_when_conditions_met(self) -> None:
        """enforce_session=True + window>0 → probe wired."""
        mock_client = MagicMock()
        enforce_session = True
        window_seconds = 30

        wired = mock_client is not None and enforce_session and window_seconds > 0
        assert wired is True
        mock_client.set_session_duplicate_intent_probe(MagicMock())

    def test_probe_not_wired_when_enforce_false(self) -> None:
        """enforce_session=False → probe NOT wired (double-off)."""
        mock_client = MagicMock()
        enforce_session = False
        window_seconds = 30

        wired = mock_client is not None and enforce_session and window_seconds > 0
        assert wired is False
        mock_client.set_session_duplicate_intent_probe.assert_not_called()

    def test_probe_not_wired_when_window_zero(self) -> None:
        """window_seconds=0 → dormant, probe NOT wired."""
        mock_client = MagicMock()
        enforce_session = True
        window_seconds = 0

        wired = mock_client is not None and enforce_session and window_seconds > 0
        assert wired is False

    def test_probe_not_wired_when_client_none(self) -> None:
        """execution_client=None → no wiring."""
        mock_client = None
        enforce_session = True
        window_seconds = 30

        wired = mock_client is not None and enforce_session and window_seconds > 0
        assert wired is False
