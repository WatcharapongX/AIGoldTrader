"""Native PostgreSQL market storage; source is part of each idempotency key."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Uuid


class MarketTick(Base):
    __tablename__ = "ticks"
    symbol_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("symbols.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    bid: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    ask: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    spread: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 5))


class MarketCandle(Base):
    __tablename__ = "candles"
    symbol_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("symbols.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(3), primary_key=True)
    bucket_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 5))
    bid_close: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    ask_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    is_closed: Mapped[bool] = mapped_column(Boolean)
