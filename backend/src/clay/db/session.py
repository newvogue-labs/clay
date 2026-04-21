from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from clay.settings.ingestion import IngestionSettings


SQLITE_SCHEMA_TRANSLATE_MAP = {
    "market": None,
    "context": None,
    "ops": None,
    "demo": None,
    "review": None,
}


def build_engine(settings: IngestionSettings | None = None) -> Engine:
    resolved = settings or IngestionSettings()
    engine_kwargs: dict[str, object] = {"future": True}

    if resolved.database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["execution_options"] = {
            "schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP,
        }

    return create_engine(resolved.database_url, **engine_kwargs)


def build_session_factory(
    settings: IngestionSettings | None = None,
) -> sessionmaker:
    return sessionmaker(
        bind=build_engine(settings),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
