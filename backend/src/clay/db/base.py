from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {"ix": "ix_%(table_name)s_%(column_0_name)s"}


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for Clay storage models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
