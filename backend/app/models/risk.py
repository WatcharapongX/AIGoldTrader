"""Phase 5 models: versioned risk policies, symbol specs, account snapshots,
immutable decisions, reservations, and kill switch records.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PAYLOAD = JSON().with_variant(JSONB(), "postgresql")


class RiskPolicyRecord(Base):
    __tablename__ = "risk_policies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (
        Index(
            "uq_risk_policy_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )


class SymbolSpecificationRecord(Base):
    __tablename__ = "symbol_specifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(18, 5), nullable=False)
    tick_value: Mapped[Decimal] = mapped_column(Numeric(18, 5), nullable=False)
    contract_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume_min: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume_max: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume_step: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    digits: Mapped[int] = mapped_column(nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (Index("ix_symbol_spec_symbol_source", "symbol", "source", "observed_at"),)


class AccountSnapshotRecord(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    free_margin: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    daily_realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    weekly_realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    peak_equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    open_risk_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    reserved_risk_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"), nullable=False)
    consecutive_losses: Mapped[int] = mapped_column(default=0, nullable=False)
    trading_mode: Mapped[str] = mapped_column(String(20), default="PAPER", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="CONFIGURED_TEST", nullable=False)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (Index("ix_account_snapshot_as_of", "account_id", "as_of"),)


class RiskDecisionRecord(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # APPROVED, REDUCED, BLOCKED
    requested_risk_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    approved_risk_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    requested_risk_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    approved_risk_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    position_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    entry_lower: Mapped[Decimal] = mapped_column(Numeric(18, 5), nullable=False)
    entry_upper: Mapped[Decimal] = mapped_column(Numeric(18, 5), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(18, 5), nullable=False)
    stop_distance: Mapped[Decimal] = mapped_column(Numeric(18, 5), nullable=False)
    account_snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (
        Index("ix_risk_decision_candidate", "candidate_id", "profile_id"),
        Index("ix_risk_decision_as_of", "symbol", "as_of"),
        Index("ix_risk_decision_fingerprint", "candidate_id", "profile_id", "dependency_fingerprint"),
        UniqueConstraint("candidate_id", "profile_id", "dependency_fingerprint", name="uq_risk_decision_deterministic"),
    )


class RiskReservationRecord(Base):
    __tablename__ = "risk_reservations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("risk_decisions.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    risk_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    risk_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    position_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, RELEASED, EXPIRED
    reserved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_until: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (
        Index("ix_risk_reservation_active", "account_id", "status", "reserved_until"),
        Index("ix_risk_reservation_symbol", "symbol", "direction", "status"),
        UniqueConstraint("decision_id", name="uq_risk_reservation_decision"),
    )


class KillSwitchRecord(Base):
    __tablename__ = "kill_switch_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)  # ACTIVE, INACTIVE
    # MANUAL, AUTOMATIC_DAILY_LOSS, AUTOMATIC_DRAWDOWN, AUTOMATIC_DATA_HEALTH
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_th: Mapped[str] = mapped_column(String(500), nullable=False)
    activated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    cleared_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleared_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False)
    __table_args__ = (Index("ix_kill_switch_active", "state", "activated_at"),)


class DataHealthRecord(Base):
    __tablename__ = "data_health_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(default=0, nullable=False)
    last_failure_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_healthy_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(PAYLOAD, nullable=False, default=dict)
    __table_args__ = (Index("ix_data_health_provider_source", "provider", "source"),)
