from pathlib import Path

import pytest

from clay.api.dependencies import get_db_session, get_ingestion_settings
from clay.api.main import create_app
from clay.db import Base, build_engine, build_session_factory
from clay.db import models_context, models_demo, models_market, models_ops, models_review  # noqa: F401
from clay.settings.ingestion import IngestionSettings


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> IngestionSettings:
    return IngestionSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'clay-test.db'}",
        market_symbols=["BTCUSDT", "ETHUSDT"],
        market_timeframes=["5m", "15m"],
    )


@pytest.fixture
def sqlite_engine(sqlite_settings: IngestionSettings):
    engine = build_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def sqlite_session_factory(sqlite_engine, sqlite_settings: IngestionSettings):
    return build_session_factory(sqlite_settings)


@pytest.fixture
def db_session(sqlite_session_factory):
    with sqlite_session_factory() as session:
        yield session


@pytest.fixture
def app_with_sqlite(sqlite_session_factory, sqlite_settings: IngestionSettings):
    app = create_app()
    async def override_db_session():
        with sqlite_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_ingestion_settings] = lambda: sqlite_settings
    yield app
    app.dependency_overrides.clear()
