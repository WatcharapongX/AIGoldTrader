"""D5 backtest persistence: runs, simulated trades, equity points.

Backtest-specific tables only; never reuse live order/position/reservation tables.
Payload JSON holds the immutable canonical evidence (fingerprints, config, metrics).
"""

import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PAYLOAD = JSON().with_variant(JSONB(), "postgresql")


class BacktestRunRecord(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    simulation_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (Index("ix_backtest_runs_owner_created", "owner_id", "created_at"),)


class BacktestTradeRecord(Base):
    __tablename__ = "backtest_trades"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    planned_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)


class BacktestEquityPointRecord(Base):
    __tablename__ = "backtest_equity_points"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), nullable=False, index=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
