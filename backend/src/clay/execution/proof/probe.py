"""Proof probes: sliding-window checks over ADMIT decisions.

Submit-rate probe: zero-arg callable wired into ExecutionProofGate via
``set_session_submit_rate_probe``.

Duplicate-intent probe: takes OrderRequest, computes semantic_hash,
checks for prior ADMIT with same semantic_hash and different CID.

DB errors propagate — the gate treats any probe exception as
``submit_rate_exceeded=True`` / ``duplicate_intent=True`` (fail-closed).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from clay.execution.adapter.domain import OrderRequest
from clay.execution.proof.checker import semantic_intent_hash
from clay.db.repositories_ops import ProofDecisionRepository


def build_submit_rate_probe(
    session_factory: sessionmaker,
    *,
    max_submits: int,
    window_seconds: int,
) -> Callable[[], bool]:
    """Фабрика probe: замыкание на session_factory + бюджет.

    Семантика: текущее решение ещё НЕ персистировано (persist ПОСЛЕ admit),
    поэтому бюджет = max_submits допущенных за окно; (max+1)-й → True (deny).
    """

    def _probe() -> bool:
        since = datetime.now(tz=timezone.utc) - timedelta(seconds=window_seconds)
        with session_factory() as session:
            repo = ProofDecisionRepository(session)
            return repo.count_admitted_since(since=since) >= max_submits

    return _probe


def build_duplicate_intent_probe(
    session_factory: sessionmaker,
    *,
    window_seconds: int,
) -> Callable[[OrderRequest], bool]:
    """Фабрика duplicate-intent probe: замыкание на session_factory + окно.

    Семантика: проверяет, был ли prior ADMIT с тем же semantic_hash
    и ДРУГИМ client_order_id в скользящем окне (CID-exemption).
    Текущее решение ещё НЕ персистировано (persist ПОСЛЕ admit).
    """

    def _probe(intent: OrderRequest) -> bool:
        sem = semantic_intent_hash(intent)
        since = datetime.now(tz=timezone.utc) - timedelta(seconds=window_seconds)
        with session_factory() as session:
            repo = ProofDecisionRepository(session)
            return repo.exists_admitted_duplicate(
                semantic_hash=sem,
                since=since,
                exclude_client_order_id=intent.client_order_id,
            )

    return _probe
