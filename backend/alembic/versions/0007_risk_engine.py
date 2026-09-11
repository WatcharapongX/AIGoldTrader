"""Phase 5 risk engine, portfolio risk reservations, and kill switch records."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_risk_engine"
down_revision = "0006_strategy"
branch_labels = None
depends_on = None
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "risk_policies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(64), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSON, nullable=False),
    )
    op.create_table(
        "symbol_specifications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("tick_size", sa.Numeric(18, 5), nullable=False),
        sa.Column("tick_value", sa.Numeric(18, 5), nullable=False),
        sa.Column("contract_size", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume_min", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume_max", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume_step", sa.Numeric(18, 4), nullable=False),
        sa.Column("digits", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSON, nullable=False),
    )
    op.create_index(
        "ix_symbol_spec_symbol_source",
        "symbol_specifications",
        ["symbol", "source", "observed_at"],
    )
    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("equity", sa.Numeric(18, 2), nullable=False),
        sa.Column("free_margin", sa.Numeric(18, 2), nullable=True),
        sa.Column("daily_realized_pnl", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("weekly_realized_pnl", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("peak_equity", sa.Numeric(18, 2), nullable=False),
        sa.Column("open_risk_pct", sa.Numeric(10, 4), nullable=False, server_default="0.0000"),
        sa.Column("reserved_risk_pct", sa.Numeric(10, 4), nullable=False, server_default="0.0000"),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trading_mode", sa.String(20), nullable=False, server_default="PAPER"),
        sa.Column("source", sa.String(40), nullable=False, server_default="CONFIGURED_TEST"),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSON, nullable=False),
    )
    op.create_index(
        "ix_account_snapshot_as_of",
        "account_snapshots",
        ["account_id", "as_of"],
    )
    op.create_table(
        "risk_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("strategy_id", sa.String(32), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("requested_risk_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("approved_risk_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("requested_risk_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("approved_risk_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("position_size", sa.Numeric(18, 4), nullable=False),
        sa.Column("entry_lower", sa.Numeric(18, 5), nullable=False),
        sa.Column("entry_upper", sa.Numeric(18, 5), nullable=False),
        sa.Column("stop_loss", sa.Numeric(18, 5), nullable=False),
        sa.Column("stop_distance", sa.Numeric(18, 5), nullable=False),
        sa.Column("account_snapshot_id", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSON, nullable=False),
    )
    op.create_index(
        "ix_risk_decision_candidate",
        "risk_decisions",
        ["candidate_id", "profile_id"],
    )
    op.create_index(
        "ix_risk_decision_as_of",
        "risk_decisions",
        ["symbol", "as_of"],
    )
    op.create_table(
        "risk_reservations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "decision_id",
            sa.String(64),
            sa.ForeignKey("risk_decisions.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("risk_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("risk_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("position_size", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(200), nullable=True),
    )
    op.create_index(
        "ix_risk_reservation_active",
        "risk_reservations",
        ["account_id", "status", "reserved_until"],
    )
    op.create_index(
        "ix_risk_reservation_symbol",
        "risk_reservations",
        ["symbol", "direction", "status"],
    )
    op.create_table(
        "kill_switch_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("trigger_type", sa.String(30), nullable=False),
        sa.Column("reason_th", sa.String(500), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.String(64), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_by", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("payload", JSON, nullable=False),
    )
    op.create_index(
        "ix_kill_switch_active",
        "kill_switch_records",
        ["state", "activated_at"],
    )


def downgrade():
    for table in ("risk_decisions", "risk_reservations", "kill_switch_records"):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(table))):
            raise RuntimeError("Downgrade blocked: preserve risk history and audit records")
    op.drop_index("ix_kill_switch_active", table_name="kill_switch_records")
    op.drop_table("kill_switch_records")
    op.drop_index("ix_risk_reservation_symbol", table_name="risk_reservations")
    op.drop_index("ix_risk_reservation_active", table_name="risk_reservations")
    op.drop_table("risk_reservations")
    op.drop_index("ix_risk_decision_as_of", table_name="risk_decisions")
    op.drop_index("ix_risk_decision_candidate", table_name="risk_decisions")
    op.drop_table("risk_decisions")
    op.drop_index("ix_account_snapshot_as_of", table_name="account_snapshots")
    op.drop_table("account_snapshots")
    op.drop_index("ix_symbol_spec_symbol_source", table_name="symbol_specifications")
    op.drop_table("symbol_specifications")
    op.drop_table("risk_policies")
