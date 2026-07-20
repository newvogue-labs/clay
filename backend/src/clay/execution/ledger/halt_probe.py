"""D-15: Halt-latch mode probe for ExecutionProofGate.

Reads the durable ``HaltLatch`` singleton and returns ``SessionMode.HALTED``
when engaged, ``SessionMode.NORMAL`` otherwise.

Dormant by default (``CLAY_PROOF_ENFORCE_HALT_LATCH=false``). When the flag
is OFF, no probe is bound → gate sees ``SessionMode.NORMAL`` → live path
byte-identical.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from clay.execution.ledger.halt_latch import HaltLatchRepository
from clay.execution.proof.snapshot import SessionMode

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)


def build_halt_latch_mode_probe(
    session_factory: sessionmaker,  # type: ignore[type-arg]
) -> Callable[[], SessionMode]:
    """Factory: zero-arg callable for ``ExecutionProofGate.session_mode_probe``.

    On each call: fresh session, check ``HaltLatchRepository.is_engaged()``.
    Exceptions are NOT swallowed — gate fail-closes to ``HALTED``.
    """

    def _probe() -> SessionMode:
        with session_factory() as s:
            repo = HaltLatchRepository(s)
            if repo.is_engaged():
                return SessionMode.HALTED
        return SessionMode.NORMAL

    return _probe
