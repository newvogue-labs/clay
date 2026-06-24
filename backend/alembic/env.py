from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from clay.db.base import Base
from clay.db import models_context, models_demo, models_knowledge, models_market, models_ops, models_review, models_validation  # noqa: F401 — models imported for Alembic autogenerate target metadata
from clay.settings.ingestion import IngestionSettings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = IngestionSettings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Схемы, которыми владеют SQLAlchemy-модели Clay. Всё остальное
# (служебные схемы TimescaleDB, chunk-таблицы в _timescaledb_internal,
# information_schema, pg_catalog, public) должно быть НЕВИДИМО для
# autogenerate, чтобы он не предлагал create/drop для объектов вне модели.
APP_SCHEMAS = frozenset({
    "context",
    "demo",
    "knowledge",
    "market",
    "ops",
    "review",
    "validation",
})

def include_name(name, type_, parent_names):
    # Сравниваем/рефлектим только объекты в схемах, которыми владеет Clay.
    if type_ == "schema":
        return name in APP_SCHEMAS
    return True

def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
