"""ExecutionProofGate — внешний wrapper над ExchangeAdapter.

Делегирует все методы inner, переопределяет только place_order:
rules → quantize → snapshot → admit → persist-fail-closed → delegate.

Дормантность снята: гейт активен только для testnet (bootstrap оборачивает).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from clay.execution.adapter.domain import (
    BalanceSnapshot,
    OrderAck,
    OrderRequest,
    OrderSnapshot,
)
from clay.execution.adapter.enums import Environment
from clay.execution.adapter.rules import MarketRules
from clay.execution.proof.checker import admit
from clay.execution.proof.decision import Decision, DecisionRecord
from clay.execution.proof.errors import ProofGateDeniedError, ProofGatePersistError
from clay.execution.proof.snapshot import FreshnessPolicy, MarketSnapshot

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
        metadata_version: str = "v1",
    ) -> None:
        self._inner = inner
        self._session_factory = session_factory
        self._freshness_policy = freshness_policy
        self._max_order_notional = max_order_notional
        self._metadata_version = metadata_version

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
        record = admit(
            intent=quantized,
            snapshot=snapshot,
            policy=self._freshness_policy,
            max_order_notional=self._max_order_notional,
            now=_now_utc(),
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

    async def cancel_order(self, symbol: str, venue_order_id: str) -> None:
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
