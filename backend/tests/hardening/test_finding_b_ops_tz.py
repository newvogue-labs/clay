"""Finding B: ``tz``-safe legacy ops datetime columns (hardening #5).

A2.5 introduced :class:`UTCDateTime` (``clay/db/types.py``) for the 6
newly-persisted runtime-state tables. The 3 legacy ``ops``-schema
tables (``ingest_runs``, ``connector_status_history``,
``source_health_events``) were intentionally left on raw
``DateTime(timezone=True)`` to avoid a behavioural change. On SQLite
that meant these columns round-tripped as **naive** datetimes, so any
caller that compared them with ``datetime.now(UTC)`` would crash with
``TypeError: can't subtract offset-naive and offset-aware``.

Two production code paths were latent bombs:

1. ``api/routes/health.py:87`` — ``(datetime.now(UTC) - latest.started_at)``
   inside ``_check_ingest_freshness`` (drives ``/health/ready``).
2. ``scheduler/jobs.py:486-497`` — ``OpsRetentionJob.run`` builds
   ``cutoff = now - timedelta(...)`` and DELETEs with
   ``time_col < cutoff`` against all three tables.

Slice FIX-B promotes the 5 legacy datetime columns to ``UTCDateTime``.
The on-disk type does not change (``UTCDateTime.impl =
DateTime(timezone=True)``) so no alembic migration is needed — the
autogenerate diff is empty.

Four tests, in this order:

1. **Round-trip** — write/read each of the 3 tables through a real
   SQLite session; assert ``tzinfo is not None`` and the UTC value
   survives (pre-fix returned naive).
2. **Readiness regression** — re-implement the readiness arithmetic
   inline (``now(UTC) - latest.started_at``) to demonstrate that the
   pre-fix latent TypeError is gone.
3. **Retention regression** — pre-seed an old IngestRun, run
   ``OpsRetentionJob.run()`` against SQLite, assert it prunes
   without TypeError.
4. **Autogenerate proof** — render ``InType.compile(dialect=...)`` for
   the changed columns to demonstrate the SQLAlchemy DDL string is
   identical to the pre-fix ``DateTime(timezone=True)`` (this is the
   static reason no alembic migration is needed; the in-session
   autogenerate run is in the finding_b report).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from clay.audit.writer import AuditWriter
from clay.db import Base, build_engine, build_session_factory
from clay.db.models_ops import IngestRun
from clay.db.repositories_ops import OpsRepository
from clay.db.types import UTCDateTime
from clay.scheduler.jobs import OpsRetentionJob
from clay.settings.ingestion import IngestionSettings


# =========================================================================
#  1) Round-trip: 3 legacy ops tables → UTC-aware on SQLite
# =========================================================================


def _build_session_factory(tmp_path) -> sessionmaker:
    db_path = tmp_path / "finding-b.db"
    settings = IngestionSettings(database_url=f"sqlite+pysqlite:///{db_path}")
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    return build_session_factory(settings)


def test_ingest_run_round_trips_utc_aware_on_sqlite(tmp_path) -> None:
    factory = _build_session_factory(tmp_path)
    aware_now = datetime.now(UTC)

    with factory() as session:
        repo = OpsRepository(session)
        run = repo.create_ingest_run(
            source_name="binance_spot",
            source_type="market",
            status="running",
            started_at=aware_now,
        )
        run_id = run.id
        repo.finalize_ingest_run(
            run,
            status="completed",
            finished_at=aware_now + timedelta(seconds=42),
        )
        session.commit()

    with factory() as session:
        row = session.get(IngestRun, run_id)
        assert row is not None
        assert row.started_at.tzinfo is not None
        assert row.started_at == aware_now
        assert row.finished_at is not None
        assert row.finished_at.tzinfo is not None


def test_connector_status_round_trips_utc_aware_on_sqlite(tmp_path) -> None:
    factory = _build_session_factory(tmp_path)
    aware_now = datetime.now(UTC)

    with factory() as session:
        repo = OpsRepository(session)
        repo.record_connector_status(
            connector_id="demo-news",
            connector_type="news",
            status="healthy",
            observed_at=aware_now,
        )
        session.commit()

    with factory() as session:
        repo = OpsRepository(session)
        rows = repo.latest_connector_statuses()
        assert len(rows) == 1
        assert rows[0].observed_at.tzinfo is not None
        assert rows[0].observed_at == aware_now


def test_source_health_event_round_trips_utc_aware_on_sqlite(tmp_path) -> None:
    factory = _build_session_factory(tmp_path)
    aware_now = datetime.now(UTC)

    with factory() as session:
        repo = OpsRepository(session)
        repo.record_source_health_event(
            source_name="binance_spot",
            severity="error",
            message="boom",
            recorded_at=aware_now,
        )
        session.commit()

    with factory() as session:
        repo = OpsRepository(session)
        rows = repo.latest_incidents(limit=5, active_only=False)
        assert len(rows) == 1
        assert rows[0].recorded_at.tzinfo is not None
        assert rows[0].recorded_at == aware_now
        assert rows[0].resolved_at is None


# =========================================================================
#  2) Readiness regression: now(UTC) - latest.started_at on SQLite
# =========================================================================


def test_readiness_arithmetic_no_typeerror_on_sqlite(tmp_path) -> None:
    """Reproduce the readiness arithmetic from
    ``api/routes/health.py:_check_ingest_freshness:87``:

        age = (datetime.now(UTC) - latest.started_at).total_seconds()

    Pre-fix this raised ``TypeError`` on SQLite because the raw
    ``DateTime(timezone=True)`` column round-tripped as naive.
    """
    factory = _build_session_factory(tmp_path)

    with factory() as session:
        repo = OpsRepository(session)
        repo.create_ingest_run(
            source_name="binance_spot",
            source_type="market",
            status="completed",
            started_at=datetime.now(UTC) - timedelta(seconds=5),
        )
        session.commit()

    with factory() as session:
        repo = OpsRepository(session)
        latest = repo.latest_ingest_run()
        assert latest is not None
        age = (datetime.now(UTC) - latest.started_at).total_seconds()
        assert age >= 0.0
        assert age < 60.0


# =========================================================================
#  3) OpsRetentionJob regression: prune runs on SQLite without TypeError
# =========================================================================


def test_ops_retention_prunes_old_ingest_run_on_sqlite(tmp_path) -> None:
    factory = _build_session_factory(tmp_path)
    audit_writer = AuditWriter(tmp_path / "audit_state", max_bytes=0)

    stale_started_at = datetime.now(UTC) - timedelta(days=400)
    fresh_started_at = datetime.now(UTC) - timedelta(hours=1)

    with factory() as session:
        repo = OpsRepository(session)
        stale = repo.create_ingest_run(
            source_name="binance_spot",
            source_type="market",
            status="failed",
            started_at=stale_started_at,
        )
        stale_id = stale.id
        repo.create_ingest_run(
            source_name="binance_spot",
            source_type="market",
            status="completed",
            started_at=fresh_started_at,
        )
        session.commit()

    job = OpsRetentionJob(
        session_factory=factory,
        audit_writer=audit_writer,
    )
    job.run()

    with factory() as session:
        assert session.get(IngestRun, stale_id) is None
        remaining = session.query(IngestRun).count()
        assert remaining == 1


# =========================================================================
#  4) Autogenerate-empty proof: UTCDateTime DDL == DateTime(timezone=True) DDL
# =========================================================================


def test_utcdatetime_compiles_to_same_ddl_as_datetime_with_tz() -> None:
    """Static proof that no alembic migration is needed:
    ``UTCDateTime.impl = DateTime(timezone=True)``, so the rendered
    DDL is byte-for-byte identical to the pre-fix column type.
    """
    from sqlalchemy import DateTime, MetaData, Column, Table
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateTable

    md = MetaData()
    pre = Table(
        "pre",
        md,
        Column("ts", DateTime(timezone=True)),
    )
    post = Table(
        "post",
        md,
        Column("ts", UTCDateTime()),
    )
    pre_ddl = str(CreateTable(pre).compile(dialect=sqlite.dialect()))
    post_ddl = str(CreateTable(post).compile(dialect=sqlite.dialect()))

    # Strip the table name; we only care that the column DDL matches.
    pre_col = pre_ddl.split("(", 1)[1].split(")", 1)[0]
    post_col = post_ddl.split("(", 1)[1].split(")", 1)[0]
    assert pre_col == post_col


def test_utcdatetime_runtime_sqlite_schema_matches_datetime_with_tz(
    tmp_path,
) -> None:
    """Runtime equivalent of ``alembic revision --autogenerate``: create
    two equivalent tables — one with raw ``DateTime(timezone=True)``
    (pre-fix), one with ``UTCDateTime`` (post-fix) — on the same SQLite
    file, then ``inspect`` the schema. The stored column types
    (``DATETIME``) and nullability must match exactly. This is the
    strongest proof available without PG: alembic's autogenerate
    compares ``inspector.get_columns(...)`` results, and this is
    what those would see.
    """
    from sqlalchemy import DateTime, Integer, MetaData, Column, Table, inspect
    from clay.db.session import build_engine

    db_path = tmp_path / "schema-compare.db"
    settings = IngestionSettings(database_url=f"sqlite+pysqlite:///{db_path}")
    engine = build_engine(settings)

    md = MetaData()
    Table(
        "pre",
        md,
        Column("id", Integer(), primary_key=True),
        Column("ts", DateTime(timezone=True), nullable=True),
    )
    Table(
        "post",
        md,
        Column("id", Integer(), primary_key=True),
        Column("ts", UTCDateTime(), nullable=True),
    )
    md.create_all(engine)

    with engine.connect() as connection:
        inspector = inspect(connection)
        pre_cols = [
            (c["name"], str(c["type"]), c["nullable"])
            for c in inspector.get_columns("pre")
        ]
        post_cols = [
            (c["name"], str(c["type"]), c["nullable"])
            for c in inspector.get_columns("post")
        ]
    assert pre_cols == post_cols
