"""accounts — trading account ต่อ user (docs/04 §2.1, INV-08)."""

import datetime as dt
import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Uuid


class TradingMode(str, enum.Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    SEMI_AUTO = "SEMI_AUTO"
    LIVE = "LIVE"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    trading_mode: Mapped[TradingMode] = mapped_column(
        Enum(TradingMode, name="trading_mode", native_enum=False), default=TradingMode.PAPER
    )
    starting_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
