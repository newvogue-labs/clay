"""Order Ledger reconcile-service — venue-state reconciliation.

Dormant by default; not wired to any production code path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from clay.execution.adapter.domain import Fill, OrderSnapshot
from clay.execution.adapter.enums import OrderState
from clay.db.models_orders import OrderCurrentState
from clay.execution.ledger.controller import OrderLedgerController
from clay.execution.ledger.errors import IllegalTransitionError
from clay.execution.ledger.repository import OrderLedgerRepository
from clay.execution.ledger.states import LedgerState


# ---------------------------------------------------------------------------
# D2: venue → ledger state mapping
# ---------------------------------------------------------------------------


def map_venue_state(state: OrderState) -> LedgerState:
    """Чистая функция: ``OrderState`` → ``LedgerState``.

    Маппинг определён ADR-12b:
    - new → ACKNOWLEDGED (venue подтвердил принятие)
    - partially_filled → PARTIALLY_FILLED
    - filled → FILLED
    - canceled → CANCELED
    - rejected → REJECTED
    - expired → EXPIRED
    """
    _MAP: dict[OrderState, LedgerState] = {
        OrderState.NEW: LedgerState.ACKNOWLEDGED,
        OrderState.PARTIALLY_FILLED: LedgerState.PARTIALLY_FILLED,
        OrderState.FILLED: LedgerState.FILLED,
        OrderState.CANCELED: LedgerState.CANCELED,
        OrderState.REJECTED: LedgerState.REJECTED,
        OrderState.EXPIRED: LedgerState.EXPIRED,
    }
    return _MAP[state]


# ---------------------------------------------------------------------------
# D3: reconcile taxonomy
# ---------------------------------------------------------------------------


class ReconcileMismatchKind(StrEnum):
    """Тип расхождения между venue и ledger."""

    STATE_DRIFT = "state_drift"
    ILLEGAL_DRIFT = "illegal_drift"
    VENUE_ORPHAN = "venue_orphan"
    LEDGER_ORPHAN = "ledger_orphan"


@dataclass(frozen=True)
class Mismatch:
    """Единичное расхождение при reconcile."""

    kind: ReconcileMismatchKind
    client_order_id: str | None
    venue_order_id: str | None
    detail: str


@dataclass
class ReconcileReport:
    """Результат reconcile-symbol."""

    healed: list[str] = field(default_factory=list)
    mismatches: list[Mismatch] = field(default_factory=list)

    @property
    def has_fatal(self) -> bool:
        """Есть ли ``MISMATCH`` с ``ILLEGAL_DRIFT`` или ``VENUE_ORPHAN``."""
        return any(
            m.kind
            in {ReconcileMismatchKind.ILLEGAL_DRIFT, ReconcileMismatchKind.VENUE_ORPHAN}
            for m in self.mismatches
        )


# ---------------------------------------------------------------------------
# D4: adapter protocol (for type-checking)
# ---------------------------------------------------------------------------


class ReconcileAdapter(Protocol):
    """Протокол read-ops, необходимых reconcile-сервису.

    Не импортирует ``BaseExchangeAdapter`` — минимальный контракт.
    """

    async def reconcile_orders(
        self, symbol: str, since: datetime
    ) -> list[OrderSnapshot]: ...

    async def get_open_orders(
        self, symbol: str | None = None
    ) -> list[OrderSnapshot]: ...

    async def get_my_trades(
        self, symbol: str, *, since: datetime | None = None, from_id: str | None = None
    ) -> list[Fill]: ...


# ---------------------------------------------------------------------------
# D4: service
# ---------------------------------------------------------------------------


class OrderReconcileService:
    """Standalone reconcile-сервис: сверяет venue-истину с ledger-проекциями.

    Dormant; не открывает сетевых/боевых сайд-эффектов кроме
    ``adapter.reconcile_orders``, ``adapter.get_open_orders`` и
    ``controller.apply_transition``.
    """

    def __init__(
        self,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        adapter: ReconcileAdapter,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    async def reconcile_symbol(
        self, symbol: str, since: datetime, *, venue: str
    ) -> ReconcileReport:
        """Сверить venue-истину с ledger для одного ``symbol``.

        Алгоритм:
        1) venue truth = reconcile_orders ∪ get_open_orders (dedup по venue_order_id)
        2) активные проекции = list_active_projections()
        3) матч venue-снапшотов к проекциям (heal через record_fills для fill-bearing)
        4) fills с venue_order_id без проекции → LEDGER_ORPHAN
        5) невстреченные проекции → LEDGER_ORPHAN
        6) upsert bookmark → вернуть ReconcileReport
        """
        report = ReconcileReport()

        # --- Шаг 1: venue truth (order-states) ---
        reconcile_snapshots = await self._adapter.reconcile_orders(symbol, since)
        open_snapshots = await self._adapter.get_open_orders(symbol)

        venue_by_void: dict[str, OrderSnapshot] = {}
        for snap in reconcile_snapshots:
            venue_by_void[snap.venue_order_id] = snap
        for snap in open_snapshots:
            existing = venue_by_void.get(snap.venue_order_id)
            if existing is None or _venue_more_advanced(snap.state, existing.state):
                venue_by_void[snap.venue_order_id] = snap

        # --- Шаг 2: fills ingestion (cursor-based) ---
        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)
            bookmark = repo.get_reconcile_bookmark(
                venue=venue, entity_type="fills", symbol=symbol
            )
            from_id = bookmark.last_trade_id if bookmark else None

        fills_raw = await self._adapter.get_my_trades(
            symbol, since=since, from_id=from_id
        )
        fills_by_voi: dict[str, list[Fill]] = {}
        for f in fills_raw:
            fills_by_voi.setdefault(f.venue_order_id, []).append(f)

        # --- Шаг 3: активные проекции ---
        with self._session_factory() as s:
            repo = OrderLedgerRepository(s)
            active = repo.list_active_projections()

        proj_by_cid: dict[str, OrderCurrentState] = {
            p.client_order_id: p for p in active
        }
        proj_by_void: dict[str, OrderCurrentState] = {}
        for p in active:
            if p.venue_order_id is not None:
                proj_by_void[p.venue_order_id] = p

        # --- Шаг 4: матч venue-снапшотов ---
        matched_cids: set[str] = set()
        ingested_fills: list[Fill] = []
        for snap in venue_by_void.values():
            proj = proj_by_cid.get(snap.client_order_id)
            if proj is None:
                void_proj = proj_by_void.get(snap.venue_order_id)
                if void_proj is not None:
                    proj = void_proj

            if proj is not None:
                matched_cids.add(proj.client_order_id)
                target = map_venue_state(snap.state)
                current = LedgerState(proj.lifecycle_state)

                if target == current:
                    continue

                fills_for_voi = fills_by_voi.get(snap.venue_order_id, [])
                try:
                    controller = OrderLedgerController(
                        self._session_factory, now_fn=self._now_fn
                    )
                    if (
                        target
                        in {
                            LedgerState.PARTIALLY_FILLED,
                            LedgerState.FILLED,
                        }
                        and fills_for_voi
                    ):
                        controller.record_fills(
                            client_order_id=proj.client_order_id,
                            fills=fills_for_voi,
                            to_state=target,
                            expected_version=proj.version,
                        )
                        ingested_fills.extend(fills_for_voi)
                    else:
                        controller.apply_transition(
                            client_order_id=proj.client_order_id,
                            expected_version=proj.version,
                            to_state=target,
                            venue_order_id=snap.venue_order_id,
                            payload={
                                "reason_code": "STATE_DRIFT",
                                "source": "reconcile",
                            },
                        )
                    report.healed.append(proj.client_order_id)
                except IllegalTransitionError:
                    report.mismatches.append(
                        Mismatch(
                            kind=ReconcileMismatchKind.ILLEGAL_DRIFT,
                            client_order_id=proj.client_order_id,
                            venue_order_id=snap.venue_order_id,
                            detail=f"{current.value} -> {target.value} illegal",
                        )
                    )
            else:
                report.mismatches.append(
                    Mismatch(
                        kind=ReconcileMismatchKind.VENUE_ORPHAN,
                        client_order_id=snap.client_order_id,
                        venue_order_id=snap.venue_order_id,
                        detail=f"venue order {snap.venue_order_id} not in ledger",
                    )
                )

        # --- Шаг 5: orphan fills (venue_order_id без проекции) ---
        for voi, fills_for_voi in fills_by_voi.items():
            if voi in proj_by_void:
                continue
            matched_void = any(s.venue_order_id == voi for s in venue_by_void.values())
            if not matched_void:
                report.mismatches.append(
                    Mismatch(
                        kind=ReconcileMismatchKind.LEDGER_ORPHAN,
                        client_order_id=None,
                        venue_order_id=voi,
                        detail=f"fill on unknown order {voi}",
                    )
                )

        # --- Шаг 6: невстреченные проекции ---
        for proj in active:
            if proj.client_order_id not in matched_cids:
                report.mismatches.append(
                    Mismatch(
                        kind=ReconcileMismatchKind.LEDGER_ORPHAN,
                        client_order_id=proj.client_order_id,
                        venue_order_id=proj.venue_order_id,
                        detail=f"active projection {proj.client_order_id} not in venue",
                    )
                )

        # --- Шаг 7: upsert bookmark ---
        # D-12c fix: advance cursor only to the latest *ingested* fill
        # (the ones actually written via record_fills). This prevents
        # skipping fills on the next run when orphan fills are present.
        if ingested_fills:
            anchor = max(ingested_fills, key=lambda f: f.transact_time)
            with self._session_factory() as s:
                repo = OrderLedgerRepository(s)
                repo.upsert_reconcile_bookmark(
                    venue=venue,
                    entity_type="fills",
                    symbol=symbol,
                    last_trade_id=anchor.trade_id,
                    last_timestamp=anchor.transact_time,
                    now=self._now_fn(),
                )
                s.commit()
        elif fills_raw:
            # fills_raw non-empty but all orphan → do NOT advance bookmark
            # (next run re-fetches them). Signal-only mismatch.
            report.mismatches.append(
                Mismatch(
                    kind=ReconcileMismatchKind.LEDGER_ORPHAN,
                    client_order_id=None,
                    venue_order_id=None,
                    detail="cursor_not_advanced: orphan fills ahead",
                )
            )

        return report


def _venue_more_advanced(a: OrderState, b: OrderState) -> bool:
    """Определить, является ли ``a`` более продвинутым/терминальным, чем ``b``.

    Терминальные состояния всегда «выше»; среди остальных — ``filled > partially_filled > new``.
    """
    _RANK: dict[OrderState, int] = {
        OrderState.NEW: 0,
        OrderState.PARTIALLY_FILLED: 1,
        OrderState.FILLED: 2,
        OrderState.CANCELED: 2,
        OrderState.REJECTED: 2,
        OrderState.EXPIRED: 2,
    }
    return _RANK[a] > _RANK[b]
