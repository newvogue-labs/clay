"""create provider pool schema tables (S1 provider-pool)

Revision ID: 0016_provider_pool
Revises: 0015_ai_agent_runs
Create Date: 2026-06-17

Использует pg-native DDL (CREATE TYPE / CREATE TABLE) через op.execute,
т.к. SQLAlchemy Enum с create_type=False на PG всё равно триггерит
create_type через NamedType._on_table_create.
"""
from collections.abc import Sequence

from alembic import op


revision: str = "0016_provider_pool"
down_revision: str | None = "0015_ai_agent_runs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


_ENUM_DDL: list[str] = [
    "CREATE TYPE ops.provider_route_class AS ENUM ('upstream', 'downstream', 'local')",
    "CREATE TYPE ops.provider_trust AS ENUM ('eu', 'us', 'cn', 'local')",
    "CREATE TYPE ops.provider_egress AS ENUM ('realmoney_ok', 'demo_only')",
    "CREATE TYPE ops.key_state AS ENUM ('available', 'cooling', 'exhausted', 'dead')",
    "CREATE TYPE ops.health_outcome AS ENUM ('success', 'auth_fail', 'quota', 'blocked', 'timeout', 'bad_request', 'upstream')",
]

_DROP_ENUMS: list[str] = [
    "DROP TYPE IF EXISTS ops.health_outcome",
    "DROP TYPE IF EXISTS ops.key_state",
    "DROP TYPE IF EXISTS ops.provider_egress",
    "DROP TYPE IF EXISTS ops.provider_trust",
    "DROP TYPE IF EXISTS ops.provider_route_class",
]

_CREATE_PROVIDER = """
CREATE TABLE ops.provider (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(64) NOT NULL,
    route_class ops.provider_route_class NOT NULL,
    base_url    TEXT,
    trust       ops.provider_trust NOT NULL,
    egress      ops.provider_egress NOT NULL DEFAULT 'demo_only',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name)
);
"""

_CREATE_PROVIDER_KEY = """
CREATE TABLE ops.provider_key (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id        BIGINT NOT NULL REFERENCES ops.provider(id) ON DELETE CASCADE,
    account_label      VARCHAR(64) NOT NULL,
    key_ref            VARCHAR(128) NOT NULL,
    state              ops.key_state NOT NULL DEFAULT 'available',
    consecutive_fails  INT NOT NULL DEFAULT 0,
    last_outcome       ops.health_outcome,
    cooling_until      TIMESTAMPTZ,
    reset_at           TIMESTAMPTZ,
    reset_tz           VARCHAR(48),
    rpm_limit          INT,
    rpd_limit          INT,
    rpd_used           INT NOT NULL DEFAULT 0,
    daily_token_limit  BIGINT,
    daily_token_used   BIGINT NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider_id, account_label)
);
"""

_CREATE_PROVIDER_DEPLOYMENT = """
CREATE TABLE ops.provider_deployment (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name      VARCHAR(128) NOT NULL,
    provider_key_id BIGINT REFERENCES ops.provider_key(id) ON DELETE CASCADE,
    provider_id     BIGINT NOT NULL REFERENCES ops.provider(id) ON DELETE CASCADE,
    upstream_model  VARCHAR(160) NOT NULL,
    params          JSONB NOT NULL DEFAULT '{}',
    weight          INT NOT NULL DEFAULT 1,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (model_name, provider_key_id, upstream_model)
);
"""

_CREATE_PROVIDER_HEALTH = """
CREATE TABLE ops.provider_health (
    time             TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider_key_id  BIGINT,
    deployment_id    BIGINT,
    model_name       VARCHAR(128) NOT NULL,
    outcome          ops.health_outcome NOT NULL,
    latency_ms       INT,
    tokens           INT,
    error_excerpt    TEXT
);
"""

_CREATE_HYPERTABLE = "SELECT create_hypertable('ops.provider_health', 'time', if_not_exists => TRUE)"

_CREATE_INDEXES: list[str] = [
    "CREATE INDEX ix_provider_key_state ON ops.provider_key (state)",
    "CREATE INDEX ix_provider_key_reset_at ON ops.provider_key (reset_at)",
    "CREATE INDEX ix_provider_deployment_model_name ON ops.provider_deployment (model_name)",
    "CREATE INDEX ix_provider_health_key_time ON ops.provider_health (provider_key_id, time DESC)",
]

_DROP_INDEXES: list[str] = [
    "DROP INDEX IF EXISTS ops.ix_provider_health_key_time",
    "DROP INDEX IF EXISTS ops.ix_provider_deployment_model_name",
    "DROP INDEX IF EXISTS ops.ix_provider_key_reset_at",
    "DROP INDEX IF EXISTS ops.ix_provider_key_state",
]

_DROP_TABLES: list[str] = [
    "DROP TABLE IF EXISTS ops.provider_health CASCADE",
    "DROP TABLE IF EXISTS ops.provider_deployment CASCADE",
    "DROP TABLE IF EXISTS ops.provider_key CASCADE",
    "DROP TABLE IF EXISTS ops.provider CASCADE",
]


def upgrade() -> None:
    for sql in _ENUM_DDL:
        op.execute(sql)
    op.execute(_CREATE_PROVIDER)
    op.execute(_CREATE_PROVIDER_KEY)
    op.execute(_CREATE_PROVIDER_DEPLOYMENT)
    op.execute(_CREATE_PROVIDER_HEALTH)
    op.execute(_CREATE_HYPERTABLE)
    for sql in _CREATE_INDEXES:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DROP_INDEXES:
        op.execute(sql)
    for sql in _DROP_TABLES:
        op.execute(sql)
    for sql in _DROP_ENUMS:
        op.execute(sql)
