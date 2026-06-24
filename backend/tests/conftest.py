import os
import tempfile

# Герметизация: module-level singleton в bootstrap не должен ходить в реальный PG.
# Создаём file-based SQLite с таблицами, выставляем URL в environ ДО импорта
# clay-модулей, чтобы IngestionSettings() в bootstrap.py подхватил SQLite,
# а не live 5432. setdefault — не перезаписывает явно заданный env (CI, smoke).
_tmp_db_path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ.setdefault("CLAY_DATABASE_URL", f"sqlite+pysqlite:///{_tmp_db_path}")

# Импортируем модели для регистрации в Base.metadata до create_all
from clay.db import Base, build_engine, build_session_factory  # noqa: E402 — DB URL setup must precede clay imports
from clay.db import models_context, models_demo, models_knowledge, models_market, models_ops, models_review, models_validation  # noqa: F401, E402
from clay.settings.ingestion import IngestionSettings  # noqa: E402

# Создаём таблицы в bootstrap-БД (ai_assignments, ai_control_state и т.д.)
# чтобы AIControlService.__init__ с session_factory не упал на "no such table".
_bs_engine = build_engine(IngestionSettings(database_url=os.environ["CLAY_DATABASE_URL"]))
Base.metadata.create_all(_bs_engine)
_bs_engine.dispose()

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from clay.api.dependencies import get_db_session, get_ingestion_settings  # noqa: E402
from clay.api.main import create_app  # noqa: E402


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
        session = sqlite_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_ingestion_settings] = lambda: sqlite_settings
    yield app
    app.dependency_overrides.clear()
