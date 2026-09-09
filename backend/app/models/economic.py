"""Append-only economic occurrence identity and canonical revision history."""

import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EconomicOccurrence(Base):
    __tablename__ = "economic_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    occurrence_key: Mapped[str] = mapped_column(String(100), nullable=False)
    __table_args__ = (UniqueConstraint("source", "provider_event_id", "occurrence_key", name="uq_economic_occurrence"),)


class EconomicRevision(Base):
    __tablename__ = "economic_event_revisions"
    event_id: Mapped[str] = mapped_column(String(100), ForeignKey("economic_events.id"), primary_key=True)
    revision_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    available_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    __table_args__ = (Index("ix_economic_available", "available_at", "event_id"),)
