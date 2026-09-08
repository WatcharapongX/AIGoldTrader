"""system_events — เหตุการณ์ระบบสำหรับ monitoring/kill switch (docs/04 §2.10)."""

import datetime as dt
import enum
import uuid

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, Uuid

JsonType = JSONB().with_variant(JSON(), "sqlite")


class EventCategory(str, enum.Enum):
    DATA = "DATA"
    BROKER = "BROKER"
    AI = "AI"
    DB = "DB"
    REDIS = "REDIS"
    WS = "WS"
    SYSTEM = "SYSTEM"


class EventSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory, name="event_category", native_enum=False), default=EventCategory.SYSTEM
    )
    severity: Mapped[EventSeverity] = mapped_column(
        Enum(EventSeverity, name="event_severity", native_enum=False), default=EventSeverity.INFO
    )
    code: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(String(1000))
    payload: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), default="-")
