"""Custom SQLAlchemy column types for Clay.

Currently exposes :class:`UTCDateTime`, a ``TypeDecorator`` that
guarantees every ``DateTime(timezone=True)`` value written or read
through Clay's runtime-state tables is a timezone-aware ``datetime`` in
UTC, regardless of the backend in use.

Why this exists
---------------

PostgreSQL preserves timezone-aware ``datetime`` values across
round-trips; SQLite does not — it returns naive ``datetime`` even when
the column is declared with ``DateTime(timezone=True)``. A3+ restore
logic compares stored timestamps to ``datetime.now(UTC)``, which raises
``TypeError`` when one operand is naive and the other is aware. This
decorator is the single seam where that mismatch is normalized, so the
rest of the codebase can treat round-tripped timestamps as UTC-aware
without per-call ``.replace(tzinfo=...)`` workarounds.

The decorator is intentionally narrow:

- It is applied **only** to the 6 runtime-state tables introduced in
  alembic revision ``0008_ops_runtime_state``. The earlier
  ``ops``-schema tables (``ingest_runs``, ``connector_status_history``,
  ``source_health_events``) keep raw ``DateTime(timezone=True)`` so this
  change is non-breaking for existing data and tests.
- It does not change the on-disk column type. The migration in
  ``0008`` does not need to be touched.
- It is placed in this module (``db/types.py``) rather than
  ``db/session.py`` because ``session.py`` is reserved for engine
  construction and the schema translate map. Type definitions are an
  independent concern.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator):
    """``DateTime(timezone=True)`` that always round-trips as UTC-aware.

    On bind (Python -> DB):

    - ``None`` -> ``None``
    - naive ``datetime`` -> interpreted as UTC (``tzinfo=UTC``)
    - aware ``datetime`` -> converted to UTC (``astimezone(UTC)``)

    On result (DB -> Python):

    - ``None`` -> ``None``
    - naive ``datetime`` (SQLite) -> tagged as UTC
    - aware ``datetime`` (PostgreSQL) -> converted to UTC

    The resulting ``datetime`` is always ``tzinfo == datetime.UTC``,
    which makes round-trip equality with ``datetime.now(UTC)`` safe and
    removes the need for ``.replace(tzinfo=...)`` workarounds in
    downstream code and tests.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
