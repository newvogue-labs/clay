"""Submit-rate probe: sliding-window counter over ADMIT decisions.

The probe is a zero-arg callable wired into ExecutionProofGate via
``set_session_submit_rate_probe``.  DB errors propagate — the gate
treats any probe exception as ``submit_rate_exceeded=True`` (fail-closed).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

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
