"""SQLAlchemy declarative base + naming convention (docs/04 §3)."""

from sqlalchemy import MetaData
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Generic UUID type — PostgreSQL: native UUID, SQLite: CHAR(32) (ใช้ใน tests)
Uuid = SAUuid(as_uuid=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
