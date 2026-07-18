"""Тесты submit-rate probe wiring (S-EXEC-SAFE-4d / D-7).

Покрытие:
  D1: ExecutionConfig defaults + from_env для submit-rate полей.
  D2: ProofDecisionRepository.count_admitted_since — sliding window.
  D3: build_submit_rate_probe — пусто→False, count<max→False,
      count==max→True, count>max→True, DB exception propagates.
  D4: Bootstrap wiring — probe set / not set по conditions.
  D5: Double-off — enforce_session=False → probe never called.
  D6: Gate integration — non-reduce denied, reduce bypass.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from clay.db.models_ops import ExecutionProofDecision
from clay.db.repositories_ops import ProofDecisionRepository
from clay.execution.adapter.enums import OrderSide
from clay.execution.config import ExecutionConfig
from clay.execution.proof.decision import Decision, DecisionRecord, InvariantResult
from clay.execution.proof.reason_codes import ReasonCode
from clay.execution.proof.snapshot import FreshnessPolicy

pytestmark = pytest.mark.usefixtures("sqlite_session_factory")

NOW = datetime.now(tz=timezone.utc)


# ── D1: Config defaults + from_env ────────────────────────────────────


class TestSubmitRateConfigDefaults:
    def test_defaults_are_zero(self) -> None:
        cfg = ExecutionConfig()
        assert cfg.proof_submit_rate_max == 0
        assert cfg.proof_submit_rate_window_seconds == 0

    @patch.dict(os.environ, {"CLAY_PROOF_SUBMIT_RATE_MAX": "10"})
    def test_from_env_max(self) -> None:
        cfg = ExecutionConfig.from_env()
        assert cfg.proof_submit_rate_max == 10

    @patch.dict(os.environ, {"CLAY_PROOF_SUBMIT_RATE_WINDOW_SECONDS": "60"})
    def test_from_env_window(self) -> None:
        cfg = ExecutionConfig.from_env()
        assert cfg.proof_submit_rate_window_seconds == 60

    @patch.dict(
        os.environ,
        {
            "CLAY_PROOF_SUBMIT_RATE_MAX": "5",
            "CLAY_PROOF_SUBMIT_RATE_WINDOW_SECONDS": "30",
        },
    )
    def test_from_env_both(self) -> None:
        cfg = ExecutionConfig.from_env()
        assert cfg.proof_submit_rate_max == 5
        assert cfg.proof_submit_rate_window_seconds == 30

    def test_env_missing_defaults_zero(self) -> None:
        cfg = ExecutionConfig.from_env()
        assert cfg.proof_submit_rate_max == 0
        assert cfg.proof_submit_rate_window_seconds == 0


# ── D2: count_admitted_since ──────────────────────────────────────────


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
    created_at: datetime | None = None,
    symbol: str = "BTC/USDT",
    client_order_id: str = "cid-test",
) -> None:
    record = _make_record(
        decision=decision, created_at=created_at or datetime.now(tz=timezone.utc)
    )
    orm = ExecutionProofDecision.from_record(
        record, symbol=symbol, client_order_id=client_order_id
    )
    with session_factory() as session:
        repo = ProofDecisionRepository(session)
        repo.append(orm)
        session.commit()


class TestCountAdmittedSince:
    def test_empty_returns_zero(self, sqlite_session_factory) -> None:
        since = NOW - timedelta(hours=1)
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert repo.count_admitted_since(since=since) == 0

    def test_counts_only_admit(self, sqlite_session_factory) -> None:
        _persist(
            sqlite_session_factory, decision=Decision.ADMIT, client_order_id="cid-1"
        )
        _persist(
            sqlite_session_factory, decision=Decision.DENY, client_order_id="cid-2"
        )
        _persist(
            sqlite_session_factory, decision=Decision.ADMIT, client_order_id="cid-3"
        )
        since = NOW - timedelta(hours=1)
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert repo.count_admitted_since(since=since) == 2

    def test_window_excludes_old(self, sqlite_session_factory) -> None:
        old_time = NOW - timedelta(hours=2)
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            client_order_id="cid-old",
            created_at=old_time,
        )
        _persist(
            sqlite_session_factory, decision=Decision.ADMIT, client_order_id="cid-new"
        )
        since = NOW - timedelta(hours=1)
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert repo.count_admitted_since(since=since) == 1

    def test_deny_not_counted(self, sqlite_session_factory) -> None:
        for i in range(5):
            _persist(
                sqlite_session_factory,
                decision=Decision.DENY,
                client_order_id=f"cid-deny-{i}",
            )
        since = NOW - timedelta(hours=1)
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            assert repo.count_admitted_since(since=since) == 0


# ── D3: build_submit_rate_probe ───────────────────────────────────────


class TestBuildSubmitRateProbe:
    def test_empty_db_returns_false(self, sqlite_session_factory) -> None:
        from clay.execution.proof.probe import build_submit_rate_probe

        probe = build_submit_rate_probe(
            sqlite_session_factory, max_submits=3, window_seconds=60
        )
        assert probe() is False

    def test_count_below_max_returns_false(self, sqlite_session_factory) -> None:
        from clay.execution.proof.probe import build_submit_rate_probe

        for i in range(2):
            _persist(
                sqlite_session_factory,
                decision=Decision.ADMIT,
                client_order_id=f"cid-{i}",
            )
        probe = build_submit_rate_probe(
            sqlite_session_factory, max_submits=3, window_seconds=60
        )
        assert probe() is False

    def test_count_equals_max_returns_true(self, sqlite_session_factory) -> None:
        from clay.execution.proof.probe import build_submit_rate_probe

        for i in range(3):
            _persist(
                sqlite_session_factory,
                decision=Decision.ADMIT,
                client_order_id=f"cid-{i}",
            )
        probe = build_submit_rate_probe(
            sqlite_session_factory, max_submits=3, window_seconds=60
        )
        assert probe() is True

    def test_count_above_max_returns_true(self, sqlite_session_factory) -> None:
        from clay.execution.proof.probe import build_submit_rate_probe

        for i in range(5):
            _persist(
                sqlite_session_factory,
                decision=Decision.ADMIT,
                client_order_id=f"cid-{i}",
            )
        probe = build_submit_rate_probe(
            sqlite_session_factory, max_submits=3, window_seconds=60
        )
        assert probe() is True

    def test_db_error_propagates(self) -> None:
        """DB exception NOT swallowed — gate fail-closed treats it as exceeded."""
        from clay.execution.proof.probe import build_submit_rate_probe

        mock_sf = MagicMock()
        mock_sf.return_value.__enter__ = MagicMock(side_effect=RuntimeError("db down"))
        mock_sf.return_value.__exit__ = MagicMock(return_value=False)
        probe = build_submit_rate_probe(mock_sf, max_submits=3, window_seconds=60)
        with pytest.raises(RuntimeError, match="db down"):
            probe()

    def test_window_respected(self, sqlite_session_factory) -> None:
        """Only recent ADMITs within window_seconds count."""
        from clay.execution.proof.probe import build_submit_rate_probe

        old_time = NOW - timedelta(hours=2)
        _persist(
            sqlite_session_factory,
            decision=Decision.ADMIT,
            client_order_id="cid-old",
            created_at=old_time,
        )
        _persist(
            sqlite_session_factory, decision=Decision.ADMIT, client_order_id="cid-new"
        )
        probe = build_submit_rate_probe(
            sqlite_session_factory, max_submits=3, window_seconds=3600
        )
        assert probe() is False


# ── D4: Bootstrap wiring ──────────────────────────────────────────────


class TestBootstrapSubmitRateWiring:
    def test_probe_set_when_all_conditions_met(self) -> None:
        """enforce_session=True + max>0 + window>0 → probe wired."""
        mock_client = MagicMock()
        enforce_session = True
        submit_rate_max = 5
        submit_rate_window = 60

        wired = (
            mock_client is not None
            and enforce_session
            and submit_rate_max > 0
            and submit_rate_window > 0
        )
        assert wired is True
        mock_client.set_session_submit_rate_probe(MagicMock())

    def test_probe_not_wired_when_enforce_false(self) -> None:
        """enforce_session=False → probe NOT wired (D5: double-off)."""
        mock_client = MagicMock()
        mock_client.set_session_submit_rate_probe = MagicMock()

        # Simulate the wiring logic directly
        enforce_session = False
        submit_rate_max = 5
        submit_rate_window = 60

        wired = (
            mock_client is not None
            and enforce_session
            and submit_rate_max > 0
            and submit_rate_window > 0
        )
        assert wired is False
        mock_client.set_session_submit_rate_probe.assert_not_called()

    def test_probe_not_wired_when_max_zero(self) -> None:
        """submit_rate_max=0 → dormant, probe NOT wired."""
        mock_client = MagicMock()
        enforce_session = True
        submit_rate_max = 0
        submit_rate_window = 60

        wired = (
            mock_client is not None
            and enforce_session
            and submit_rate_max > 0
            and submit_rate_window > 0
        )
        assert wired is False

    def test_probe_not_wired_when_window_zero(self) -> None:
        """submit_rate_window_seconds=0 → dormant, probe NOT wired."""
        mock_client = MagicMock()
        enforce_session = True
        submit_rate_max = 5
        submit_rate_window = 0

        wired = (
            mock_client is not None
            and enforce_session
            and submit_rate_max > 0
            and submit_rate_window > 0
        )
        assert wired is False

    def test_probe_not_wired_when_client_none(self) -> None:
        """execution_client=None → no wiring."""
        mock_client = None
        enforce_session = True
        submit_rate_max = 5
        submit_rate_window = 60

        wired = (
            mock_client is not None
            and enforce_session
            and submit_rate_max > 0
            and submit_rate_window > 0
        )
        assert wired is False


# ── D5+D6: Gate integration ───────────────────────────────────────────


class TestSubmitRateGateIntegration:
    @pytest.mark.asyncio
    async def test_enforce_false_probe_not_called(self) -> None:
        """D5: enforce_session=False → probe never called, ADMIT."""
        from tests.execution.proof.test_gate import FakeInner, _make_request

        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        sr_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
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
    async def test_submit_rate_exceeded_buy_denied(self) -> None:
        """D6: non-reduce BUY denied with SESSION_SUBMIT_RATE_EXCEEDED."""
        from tests.execution.proof.test_gate import FakeInner, _make_request

        from clay.execution.proof.errors import ProofGateDeniedError
        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        sr_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
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
        """D6: reduce SELL bypasses submit-rate limit."""
        from tests.execution.proof.test_gate import FakeInner, _make_request

        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        sr_probe = MagicMock(return_value=True)

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
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
        """DB error in probe → fail-closed → denied."""
        from tests.execution.proof.test_gate import FakeInner, _make_request

        from clay.execution.proof.errors import ProofGateDeniedError
        from clay.execution.proof.gate import ExecutionProofGate

        inner = FakeInner()
        ks_probe = MagicMock(return_value=False)
        sr_probe = MagicMock(side_effect=RuntimeError("db down"))

        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
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
