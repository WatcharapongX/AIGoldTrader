"""D5: backtest runs/trades/equity persistence (backtest-only tables).

Revision ID: 0017_backtest_runs
Revises: 0016_batch_b_refresh_families
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_backtest_runs"
down_revision: str | None = "0016_batch_b_refresh_families"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYLOAD = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("strategy_id", sa.String(32), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("simulation_fingerprint", sa.String(64), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", PAYLOAD, nullable=False),
    )
    op.create_index("ix_backtest_runs_owner_id", "backtest_runs", ["owner_id"])
    op.create_index("ix_backtest_runs_owner_created", "backtest_runs", ["owner_id", "created_at"])
    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(80), sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("candidate_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", PAYLOAD, nullable=False),
    )
    op.create_index("ix_backtest_trades_run_id", "backtest_trades", ["run_id"])
    op.create_table(
        "backtest_equity_points",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("run_id", sa.String(80), sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", PAYLOAD, nullable=False),
    )
    op.create_index("ix_backtest_equity_points_run_id", "backtest_equity_points", ["run_id"])


def downgrade() -> None:
    op.drop_table("backtest_equity_points")
    op.drop_table("backtest_trades")
    op.drop_table("backtest_runs")
