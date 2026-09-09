"""Immutable profile versions, evaluations, candidate evidence and lifecycle transitions."""

import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PAYLOAD = JSON().with_variant(JSONB(), "postgresql")


class TraderProfileRecord(Base):
    __tablename__ = "trader_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    config_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (UniqueConstraint("profile_id", "config_id", name="uq_trader_profile_version"),)


class StrategyEvaluationRecord(Base):
    __tablename__ = "strategy_evaluations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (Index("ix_strategy_evaluation_asof", "symbol", "source", "as_of"),)


class TradeCandidateRecord(Base):
    __tablename__ = "trade_candidates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("strategy_evaluations.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (UniqueConstraint("evaluation_id", "profile_id", "strategy_id", name="uq_strategy_candidate"),)


class CandidateTransitionRecord(Base):
    __tablename__ = "candidate_transitions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), ForeignKey("trade_candidates.id"), nullable=False)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (Index("ix_candidate_transition_asof", "candidate_id", "as_of"),)
