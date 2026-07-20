"""ExecutionProofGate — внешний wrapper над ExchangeAdapter.

Делегирует все методы inner, переопределяет только place_order:
rules → quantize → snapshot → admit → persist-fail-closed → delegate.

Дормантность снята: гейт активен только для testnet (bootstrap оборачивает).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import CancelResult, Environment
from clay.execution.adapter.rules import MarketRules
from clay.execution.proof.checker import admit
from clay.execution.proof.decision import Decision, DecisionRecord
from clay.execution.proof.errors import ProofGateDeniedError, ProofGatePersistError
from clay.execution.proof.snapshot import (
    AccountSnapshot,
    FreshnessPolicy,
    MarketSnapshot,
    OpenOrdersSnapshot,
    SessionMode,
    SessionSnapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class ExecutionProofGate:
    """Внешний wrapper: place_order через admit() → persist → delegate.

    Остальные методы — прямая делегация inner.
    """

    def __init__(
        self,
        inner,  # : ExchangeAdapter — runtime_checkable Protocol
        *,
        session_factory: sessionmaker | None,
        freshness_policy: FreshnessPolicy,
        max_order_notional,  # : Decimal
        max_position: Decimal | None = None,
        max_open_orders: int = 0,
        metadata_version: str = "v1",
        enforce_portfolio: bool = False,
        enforce_session: bool = False,
        kill_switch_probe: Callable[[], bool] | None = None,
        session_mode_probe: Callable[[], SessionMode] | None = None,
        session_risk_probe: Callable[[], tuple[bool, bool]] | None = None,
        session_submit_rate_probe: Callable[[], bool] | None = None,
        session_duplicate_intent_probe: Callable[[OrderRequest], bool] | None = None,
    ) -> None:
        self._inner = inner
        self._session_factory = session_factory
        self._freshness_policy = freshness_policy
        self._max_order_notional = max_order_notional
        self._max_position = max_position or Decimal(0)
        self._max_open_orders = max_open_orders
        self._metadata_version = metadata_version
        self._enforce_portfolio = enforce_portfolio
        self._enforce_session = enforce_session
        self._kill_switch_probe = kill_switch_probe
        self._session_mode_probe = session_mode_probe
        self._session_risk_probe = session_risk_probe
        self._session_submit_rate_probe = session_submit_rate_probe
        self._session_duplicate_intent_probe = session_duplicate_intent_probe

    def set_kill_switch_probe(self, probe: Callable[[], bool]) -> None:
        """Late-bind the kill-switch probe (bootstrap wiring, after override_service)."""
        self._kill_switch_probe = probe

    def set_session_mode_probe(self, probe: Callable[[], SessionMode]) -> None:
        """Late-bind the session mode probe (bootstrap wiring, after override_service)."""
        self._session_mode_probe = probe

    def set_session_risk_probe(self, probe: Callable[[], tuple[bool, bool]]) -> None:
        """Late-bind the session risk probe (drawdown, cooldown)."""
        self._session_risk_probe = probe

    def set_session_submit_rate_probe(self, probe: Callable[[], bool]) -> None:
        """Late-bind the session submit-rate probe."""
        self._session_submit_rate_probe = probe

    def set_session_duplicate_intent_probe(
        self, probe: Callable[[OrderRequest], bool]
    ) -> None:
        """Late-bind the session duplicate-intent probe."""
        self._session_duplicate_intent_probe = probe

    @property
    def environment(self) -> Environment:
        return self._inner.environment

    async def get_market_rules(self, symbol: str) -> MarketRules:
        return await self._inner.get_market_rules(symbol)

    def validate_order(self, req: OrderRequest, rules: MarketRules) -> None:
        self._inner.validate_order(req, rules)

    def quantize_order(self, req: OrderRequest, rules: MarketRules) -> OrderRequest:
        return self._inner.quantize_order(req, rules)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        rules = await self._inner.get_market_rules(req.symbol)
        quantized = self._inner.quantize_order(req, rules)
        snapshot = MarketSnapshot(
            rules=rules,
            fetched_at=_now_utc(),
            metadata_version=self._metadata_version,
        )
        account: AccountSnapshot | None = None
        open_orders: OpenOrdersSnapshot | None = None
        if self._enforce_portfolio:
            account = AccountSnapshot(
                balances=tuple(await self._inner.get_balances()),
                fetched_at=_now_utc(),
            )
            if self._max_open_orders > 0:
                open_orders = OpenOrdersSnapshot(
                    orders=tuple(await self._inner.get_open_orders(quantized.symbol)),
                    fetched_at=_now_utc(),
                )
        session: SessionSnapshot | None = None
        if self._enforce_session:
            if self._kill_switch_probe is not None:
                try:
                    engaged = self._kill_switch_probe()
                except Exception:
                    logger.exception("kill_switch_probe failed (fail-closed → engaged)")
                    engaged = True
            else:
                # Fail-closed: armed without probe = engaged
                engaged = True
            # Resolve session mode (off-by-default: no probe → NORMAL)
            if self._session_mode_probe is not None:
                try:
                    mode = self._session_mode_probe()
                except Exception:
                    logger.exception("session_mode_probe failed (fail-closed → HALTED)")
                    mode = SessionMode.HALTED
            else:
                mode = SessionMode.NORMAL
            # Resolve risk-tripped flags (off-by-default: no probe → not tripped)
            if self._session_risk_probe is not None:
                try:
                    drawdown_tripped, cooldown_tripped = self._session_risk_probe()
                except Exception:
                    logger.exception(
                        "session_risk_probe failed (fail-closed → tripped)"
                    )
                    drawdown_tripped, cooldown_tripped = True, True
            else:
                drawdown_tripped, cooldown_tripped = False, False
            # Resolve submit-rate exceeded (off-by-default: no probe → not exceeded)
            if self._session_submit_rate_probe is not None:
                try:
                    submit_rate_exceeded = self._session_submit_rate_probe()
                except Exception:
                    logger.exception(
                        "session_submit_rate_probe failed (fail-closed → exceeded)"
                    )
                    submit_rate_exceeded = True
            else:
                submit_rate_exceeded = False
            # Resolve duplicate-intent (off-by-default: no probe → not duplicate)
            if self._session_duplicate_intent_probe is not None:
                try:
                    duplicate_intent = self._session_duplicate_intent_probe(quantized)
                except Exception:
                    logger.exception(
                        "session_duplicate_intent_probe failed (fail-closed → duplicate)"
                    )
                    duplicate_intent = True
            else:
                duplicate_intent = False
            session = SessionSnapshot(
                kill_switch_engaged=engaged,
                fetched_at=_now_utc(),
                mode=mode,
                drawdown_tripped=drawdown_tripped,
                cooldown_tripped=cooldown_tripped,
                submit_rate_exceeded=submit_rate_exceeded,
                duplicate_intent=duplicate_intent,
            )
        record = admit(
            intent=quantized,
            snapshot=snapshot,
            policy=self._freshness_policy,
            max_order_notional=self._max_order_notional,
            now=_now_utc(),
            account=account,
            max_position=self._max_position,
            open_orders=open_orders,
            max_open_orders=self._max_open_orders,
            session=session,
        )
        # persist fail-closed
        try:
            self._persist(
                record,
                symbol=quantized.symbol,
                client_order_id=quantized.client_order_id,
            )
        except Exception as exc:
            raise ProofGatePersistError() from exc
        if record.decision is Decision.DENY:
            raise ProofGateDeniedError(record.reason_codes)
        return await self._inner.place_order(quantized)

    async def cancel_order(self, symbol: str, venue_order_id: str) -> CancelResult:
        return await self._inner.cancel_order(symbol, venue_order_id)

    async def get_order(self, symbol: str, venue_order_id: str) -> OrderSnapshot:
        return await self._inner.get_order(symbol, venue_order_id)

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderSnapshot]:
        return await self._inner.get_open_orders(symbol)

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]:
        return await self._inner.reconcile_orders(symbol, since)

    async def get_balances(self) -> list[BalanceSnapshot]:
        return await self._inner.get_balances()

    async def get_by_client_order_id(
        self, symbol: str, client_order_id: str
    ) -> OrderSnapshot | None:
        return await self._inner.get_by_client_order_id(symbol, client_order_id)

    def _persist(
        self,
        record: DecisionRecord,
        *,
        symbol: str,
        client_order_id: str,
    ) -> None:
        if self._session_factory is None:
            return
        from clay.db.models_ops import ExecutionProofDecision
        from clay.db.repositories_ops import ProofDecisionRepository

        with self._session_factory() as session:
            repo = ProofDecisionRepository(session)
            orm = ExecutionProofDecision.from_record(
                record, symbol=symbol, client_order_id=client_order_id
            )
            repo.append(orm)
            session.commit()
