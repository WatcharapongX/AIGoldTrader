from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import MetaData, TypeDecorator
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent GUID/UUID type.

    PostgreSQL: native UUID.
    SQLite: CHAR(32) storing hex values, seamlessly coercing str or uuid.UUID.
    """

    impl = SAUuid(as_uuid=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is not None:
            if isinstance(value, str):
                return uuid.UUID(value)
            return value
        return None

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# Generic UUID type — PostgreSQL: native UUID, SQLite: CHAR(32) (ใช้ใน tests)
Uuid = GUID


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
