"""Order-ledger ORM models (D-12b).

Three tables in ``ops`` schema that form the foundation of the order
journal.  Not yet wired to any production code — schema + models + tests only.

- ``OrderEvent``       — append-only event journal (one row per state change)
- ``OrderCurrentState`` — singleton current-state snapshot per order
- ``OrderFillRecord``  — trade-level fill records (named to avoid collision
  with the domain ``Fill`` dataclass in ``adapter.domain``)
"""

from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from clay.db.base import Base
from clay.db.types import UTCDateTime


class OrderEvent(Base):
    """Append-only event journal for order lifecycle.

    One row per state change.  ``ledger_seq`` is a surrogate auto-increment
    PK that preserves insertion order across concurrent venue writes.
    """

    __tablename__ = "order_events"
    __table_args__ = (
        Index(
            "ix_order_events_client_order_id_ledger_seq",
            "client_order_id",
            "ledger_seq",
        ),
        Index("ix_order_events_venue_order_id", "venue_order_id"),
        Index(
            "ix_order_events_semantic_hash_created_at",
            "semantic_hash",
            "created_at",
        ),
        {"schema": "ops"},
    )

    ledger_seq: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    venue_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    venue: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class OrderCurrentState(Base):
    """Current-state snapshot for a single order (one row per client_order_id).

    Updated on every meaningful state transition.  ``version`` is an
    optimistic-lock counter.
    """

    __tablename__ = "order_current_state"
    __table_args__ = (
        Index("ix_order_current_state_semantic_hash", "semantic_hash"),
        Index(
            "ix_order_current_state_venue_venue_order_id",
            "venue",
            "venue_order_id",
        ),
        {"schema": "ops"},
    )

    client_order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    venue: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    venue_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(Text, nullable=False)
    filled_qty: Mapped[str] = mapped_column(Text, nullable=False, server_default="0")
    last_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    semantic_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class OrderFillRecord(Base):
    """Trade-level fill record for an order.

    Named ``OrderFillRecord`` (not ``Fill``) to avoid collision with the
    domain ``Fill`` dataclass in ``clay.execution.adapter.domain``.
    """

    __tablename__ = "fills"
    __table_args__ = (
        UniqueConstraint("venue", "trade_id", name="uq_fills_venue_trade_id"),
        Index("ix_fills_venue_order_id", "venue_order_id"),
        Index("ix_fills_client_order_id", "client_order_id"),
        {"schema": "ops"},
    )

    fill_pk: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    venue: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    venue_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    client_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[str] = mapped_column(Text, nullable=False)
    commission: Mapped[str | None] = mapped_column(Text, nullable=True)
    commission_asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transact_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
