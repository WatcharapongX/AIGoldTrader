"""symbols — contract spec ต่อ symbol (docs/04 §2.2, FR-MD-08)."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, Uuid

# JSONB บน Postgres, JSON บน SQLite (tests)
JsonType = JSONB().with_variant(JSON(), "sqlite")


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    asset_class: Mapped[str] = mapped_column(String(30), default="METAL")
    digits: Mapped[int] = mapped_column(Integer, default=2)
    contract_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=100)
    tick_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1)
    min_stop_distance: Mapped[Decimal] = mapped_column(Numeric(18, 5), default=0)
    default_spread: Mapped[Decimal] = mapped_column(Numeric(18, 5), default=0.30, server_default="0.30")
    session_hours: Mapped[dict] = mapped_column(JsonType, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
