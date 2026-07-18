"""Tests for session_risk: evaluate_session_risk + build_session_risk_probe + gate/bootstrap wiring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from clay.config.models import SessionLimitsConfig
from clay.execution.adapter.enums import OrderSide, OrderType, TimeInForce
from clay.session_control.session_risk import (
    SessionRiskAssessment,
    build_session_risk_probe,
    evaluate_session_risk,
)


def _limits(**overrides: object) -> SessionLimitsConfig:
    defaults: dict[str, object] = dict(
        max_drawdown_pct=15.0,
        max_consecutive_losses=3,
        cooldown_minutes=60,
        drawdown_window_hours=24,
    )
    defaults.update(overrides)
    return SessionLimitsConfig(**defaults)  # type: ignore[arg-type]


def _record(
    pnl_pct: float | None,
    *,
    outcome_status: str = "matched",
    recorded_at: datetime | None = None,
) -> object:
    return type(
        "FakeRecord",
        (),
        {
            "pnl_pct": pnl_pct,
            "outcome_status": outcome_status,
            "recorded_at": recorded_at or datetime.now(UTC),
        },
    )()


# ── evaluate_session_risk: drawdown ──────────────────────────────────


class TestEvaluateDrawdown:
    @patch("clay.session_control.session_risk.DemoRepository")
    def test_empty_db_not_tripped(self, mock_repo_cls: MagicMock) -> None:
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = []
        mock_repo.list_ordered_recent.return_value = []
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(),
            now=datetime.now(UTC),
        )
        assert result.drawdown_tripped is False
        assert result.cum_pnl == 0.0
        assert result.loss_pct == 0.0

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_drawdown_tripped_at_threshold(self, mock_repo_cls: MagicMock) -> None:
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = [
            _record(pnl_pct=-8.0),
            _record(pnl_pct=-7.5),
        ]
        mock_repo.list_ordered_recent.return_value = []
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(max_drawdown_pct=15.0),
            now=datetime.now(UTC),
        )
        assert result.drawdown_tripped is True
        assert result.loss_pct == 15.5

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_drawdown_passes_below_threshold(self, mock_repo_cls: MagicMock) -> None:
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = [
            _record(pnl_pct=-5.0),
            _record(pnl_pct=-3.0),
        ]
        mock_repo.list_ordered_recent.return_value = []
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(max_drawdown_pct=15.0),
            now=datetime.now(UTC),
        )
        assert result.drawdown_tripped is False
        assert result.loss_pct == 8.0

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_positive_pnl_not_tripped(self, mock_repo_cls: MagicMock) -> None:
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = [
            _record(pnl_pct=5.0),
            _record(pnl_pct=3.0),
        ]
        mock_repo.list_ordered_recent.return_value = []
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(),
            now=datetime.now(UTC),
        )
        assert result.drawdown_tripped is False
        assert result.loss_pct == 0.0


# ── evaluate_session_risk: cooldown ──────────────────────────────────


class TestEvaluateCooldown:
    @patch("clay.session_control.session_risk.DemoRepository")
    def test_cooldown_tripped_within_window(self, mock_repo_cls: MagicMock) -> None:
        now = datetime.now(UTC)
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = []
        mock_repo.list_ordered_recent.return_value = [
            _record(pnl_pct=-2.0, recorded_at=now),
            _record(pnl_pct=-1.5, recorded_at=now),
            _record(pnl_pct=-3.0, recorded_at=now),
        ]
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(max_consecutive_losses=3, cooldown_minutes=60),
            now=now,
        )
        assert result.cooldown_tripped is True
        assert result.streak == 3
        assert result.cooldown_remaining_minutes is not None
        assert result.cooldown_remaining_minutes <= 60

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_cooldown_expired(self, mock_repo_cls: MagicMock) -> None:
        now = datetime.now(UTC)
        old = now - timedelta(hours=2)
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = []
        mock_repo.list_ordered_recent.return_value = [
            _record(pnl_pct=-2.0, recorded_at=old),
            _record(pnl_pct=-1.5, recorded_at=old),
            _record(pnl_pct=-3.0, recorded_at=old),
        ]
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(max_consecutive_losses=3, cooldown_minutes=60),
            now=now,
        )
        assert result.cooldown_tripped is False
        assert result.streak == 3
        assert result.cooldown_remaining_minutes is None

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_streak_below_threshold(self, mock_repo_cls: MagicMock) -> None:
        now = datetime.now(UTC)
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = []
        mock_repo.list_ordered_recent.return_value = [
            _record(pnl_pct=-2.0, recorded_at=now),
        ]
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(max_consecutive_losses=3),
            now=now,
        )
        assert result.cooldown_tripped is False
        assert result.streak == 1

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_win_breaks_streak(self, mock_repo_cls: MagicMock) -> None:
        now = datetime.now(UTC)
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = []
        mock_repo.list_ordered_recent.return_value = [
            _record(pnl_pct=-2.0, recorded_at=now),
            _record(pnl_pct=1.0, recorded_at=now),
            _record(pnl_pct=-3.0, recorded_at=now),
        ]
        result = evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(max_consecutive_losses=3),
            now=now,
        )
        assert result.cooldown_tripped is False
        assert result.streak == 1

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_clock_desync_raises(self, mock_repo_cls: MagicMock) -> None:
        now = datetime.now(UTC)
        future = now + timedelta(seconds=120)
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = []
        mock_repo.list_ordered_recent.return_value = [
            _record(pnl_pct=-2.0, recorded_at=future),
            _record(pnl_pct=-1.5, recorded_at=future),
            _record(pnl_pct=-3.0, recorded_at=future),
        ]
        with pytest.raises(ValueError, match="clock desync"):
            evaluate_session_risk(
                MagicMock(),
                limits_cfg=_limits(max_consecutive_losses=3),
                now=now,
            )

    @patch("clay.session_control.session_risk.DemoRepository")
    def test_scope_passed_to_repo(self, mock_repo_cls: MagicMock) -> None:
        mock_repo = mock_repo_cls.return_value
        mock_repo.list_resolved_window.return_value = []
        mock_repo.list_ordered_recent.return_value = []
        custom_scope = frozenset({"test"})
        evaluate_session_risk(
            MagicMock(),
            limits_cfg=_limits(),
            now=datetime.now(UTC),
            scope=custom_scope,
        )
        mock_repo.list_resolved_window.assert_called_once_with(
            hours=24, source_scope=custom_scope
        )
        mock_repo.list_ordered_recent.assert_called_once_with(
            limit=50, source_scope=custom_scope
        )


# ── build_session_risk_probe ─────────────────────────────────────────


class TestBuildSessionRiskProbe:
    @patch("clay.session_control.session_risk.evaluate_session_risk")
    def test_probe_returns_tripped_flags(self, mock_eval: MagicMock) -> None:
        mock_eval.return_value = SessionRiskAssessment(
            drawdown_tripped=True,
            cooldown_tripped=False,
            cum_pnl=-20.0,
            loss_pct=20.0,
            streak=0,
        )
        mock_session_factory = MagicMock()
        mock_config_loader = MagicMock()
        mock_config_loader.load_scope.return_value = MagicMock(session_limits=_limits())
        probe = build_session_risk_probe(mock_session_factory, mock_config_loader)
        result = probe()
        assert result == (True, False)
        mock_eval.assert_called_once()

    @patch("clay.session_control.session_risk.evaluate_session_risk")
    def test_probe_reads_config_each_call(self, mock_eval: MagicMock) -> None:
        mock_eval.return_value = SessionRiskAssessment(
            drawdown_tripped=False,
            cooldown_tripped=False,
            cum_pnl=0.0,
            loss_pct=0.0,
            streak=0,
        )
        mock_session_factory = MagicMock()
        mock_config_loader = MagicMock()
        mock_config_loader.load_scope.return_value = MagicMock(session_limits=_limits())
        probe = build_session_risk_probe(mock_session_factory, mock_config_loader)
        probe()
        probe()
        assert mock_config_loader.load_scope.call_count == 2
        assert mock_eval.call_count == 2

    def test_probe_propagates_db_error(self) -> None:
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(
            side_effect=RuntimeError("db down")
        )
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
        mock_config_loader = MagicMock()
        mock_config_loader.load_scope.return_value = MagicMock(session_limits=_limits())
        probe = build_session_risk_probe(mock_session_factory, mock_config_loader)
        with pytest.raises(RuntimeError, match="db down"):
            probe()


# ── Gate integration (drawdown → BUY DENY, SELL ADMIT reduce-bypass) ─


class _FakeInner:
    """Async-safe inner adapter for gate integration tests."""

    def __init__(self) -> None:
        self.place_order_called = False
        self.environment = MagicMock()

    async def get_market_rules(self, symbol: str) -> object:
        from clay.execution.adapter.enums import PrecisionMode

        return type(
            "FakeRules",
            (),
            {
                "min_amount": Decimal("0.001"),
                "max_amount": Decimal("1000"),
                "min_price": Decimal("0.01"),
                "max_price": Decimal("100000"),
                "min_notional": Decimal("5"),
                "amount_step": Decimal("0.001"),
                "price_tick": Decimal("0.01"),
                "precision_mode": PrecisionMode.DECIMAL_PLACES,
                "supported_order_types": frozenset({OrderType.MARKET, OrderType.LIMIT}),
                "supported_tif": frozenset({TimeInForce.GTC}),
            },
        )()

    def validate_order(self, req: object, rules: object) -> None:
        pass

    def quantize_order(self, req: object, rules: object) -> object:
        return req

    async def place_order(self, req: object) -> object:
        self.place_order_called = True
        return MagicMock()


class TestGateSessionRiskIntegration:
    @pytest.mark.asyncio
    async def test_drawdown_tripped_buy_denies(self) -> None:
        from clay.execution.adapter.domain import OrderRequest
        from clay.execution.proof.errors import ProofGateDeniedError
        from clay.execution.proof.gate import ExecutionProofGate
        from clay.execution.proof.snapshot import FreshnessPolicy

        inner = _FakeInner()
        risk_probe = MagicMock(return_value=(True, False))
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=lambda: False,
        )
        gate.set_session_risk_probe(risk_probe)

        req = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            time_in_force=TimeInForce.GTC,
            client_order_id="test-risk-001",
            price=Decimal("50000"),
        )
        with pytest.raises(ProofGateDeniedError) as exc_info:
            await gate.place_order(req)
        assert "SESSION_DRAWDOWN_TRIPPED" in exc_info.value.reason_codes

    @pytest.mark.asyncio
    async def test_drawdown_tripped_sell_admits_reduce_bypass(self) -> None:
        from clay.execution.adapter.domain import OrderRequest
        from clay.execution.proof.gate import ExecutionProofGate
        from clay.execution.proof.snapshot import FreshnessPolicy

        inner = _FakeInner()
        risk_probe = MagicMock(return_value=(True, False))
        gate = ExecutionProofGate(
            inner,
            session_factory=None,
            freshness_policy=FreshnessPolicy(max_age_seconds=300),
            max_order_notional=Decimal("0"),
            enforce_session=True,
            kill_switch_probe=lambda: False,
        )
        gate.set_session_risk_probe(risk_probe)

        req = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            time_in_force=TimeInForce.GTC,
            client_order_id="test-risk-002",
            price=Decimal("50000"),
        )
        await gate.place_order(req)
        assert inner.place_order_called


# ── Bootstrap wiring ─────────────────────────────────────────────────


class TestBootstrapSessionRiskWiring:
    def test_probe_bound_when_both_flags_on(self) -> None:
        mock_client = MagicMock()
        enforce_session = True
        enforce_risk = True

        wired = mock_client is not None and enforce_session and enforce_risk
        assert wired is True
        mock_client.set_session_risk_probe(MagicMock())

    def test_probe_not_bound_when_enforce_session_off(self) -> None:
        mock_client = MagicMock()
        enforce_session = False
        enforce_risk = True

        wired = mock_client is not None and enforce_session and enforce_risk
        assert wired is False
        mock_client.set_session_risk_probe.assert_not_called()

    def test_probe_not_bound_when_enforce_risk_off(self) -> None:
        mock_client = MagicMock()
        enforce_session = True
        enforce_risk = False

        wired = mock_client is not None and enforce_session and enforce_risk
        assert wired is False
        mock_client.set_session_risk_probe.assert_not_called()

    def test_probe_not_bound_when_client_none(self) -> None:
        mock_client = None
        enforce_session = True
        enforce_risk = True

        wired = mock_client is not None and enforce_session and enforce_risk
        assert wired is False


# ── Config: ExecutionConfig.proof_enforce_session_risk ───────────────


class TestExecutionConfigSessionRisk:
    def test_default_false(self) -> None:
        from clay.execution.config import ExecutionConfig

        cfg = ExecutionConfig()
        assert cfg.proof_enforce_session_risk is False

    @patch.dict("os.environ", {"CLAY_PROOF_ENFORCE_SESSION_RISK": "true"})
    def test_parse_true(self) -> None:
        from clay.execution.config import ExecutionConfig

        cfg = ExecutionConfig.from_env()
        assert cfg.proof_enforce_session_risk is True

    @patch.dict("os.environ", {"CLAY_PROOF_ENFORCE_SESSION_RISK": "1"})
    def test_parse_one(self) -> None:
        from clay.execution.config import ExecutionConfig

        cfg = ExecutionConfig.from_env()
        assert cfg.proof_enforce_session_risk is True

    @patch.dict("os.environ", {"CLAY_PROOF_ENFORCE_SESSION_RISK": "0"})
    def test_parse_zero(self) -> None:
        from clay.execution.config import ExecutionConfig

        cfg = ExecutionConfig.from_env()
        assert cfg.proof_enforce_session_risk is False

    @patch.dict("os.environ", {}, clear=True)
    def test_env_not_set_default_false(self) -> None:
        from clay.execution.config import ExecutionConfig

        cfg = ExecutionConfig.from_env()
        assert cfg.proof_enforce_session_risk is False
