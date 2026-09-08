"""initial schema — users, sessions, accounts, symbols, audit_logs, system_events (docs/04 §2).

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "TRADER", "VIEWER", name="user_role", native_enum=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_refresh_token_hash", "sessions", ["refresh_token_hash"], unique=True)

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "trading_mode",
            sa.Enum("BACKTEST", "PAPER", "SEMI_AUTO", "LIVE", name="trading_mode", native_enum=False),
            nullable=False,
        ),
        sa.Column("starting_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("base_currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "symbols",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(20), nullable=False),
        sa.Column("asset_class", sa.String(30), nullable=False, server_default="METAL"),
        sa.Column("digits", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("contract_size", sa.Numeric(18, 4), nullable=False, server_default="100"),
        sa.Column("tick_value", sa.Numeric(18, 6), nullable=False, server_default="1"),
        sa.Column("min_stop_distance", sa.Numeric(18, 5), nullable=False, server_default="0"),
        sa.Column("session_hours", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_symbols_name", "symbols", ["name"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="API"),
        sa.Column("correlation_id", sa.String(64), nullable=False, server_default="-"),
        sa.Column("ip", sa.String(45), nullable=True),
    )
    op.create_index("ix_audit_logs_ts", "audit_logs", ["ts"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.create_table(
        "system_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "category",
            sa.Enum("DATA", "BROKER", "AI", "DB", "REDIS", "WS", "SYSTEM", name="event_category", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("INFO", "WARNING", "CRITICAL", name="event_severity", native_enum=False),
            nullable=False,
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_system_events_ts", "system_events", ["ts"])
    op.create_index("ix_system_events_code", "system_events", ["code"])


def downgrade() -> None:
    op.drop_table("system_events")
    op.drop_table("audit_logs")
    op.drop_table("symbols")
    op.drop_table("accounts")
    op.drop_table("sessions")
    op.drop_table("users")
    sa.Enum(name="event_category").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="event_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="trading_mode").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
