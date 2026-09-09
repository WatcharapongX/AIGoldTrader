"""Phase 2 native PostgreSQL market storage; preserves foundation revisions."""
import sqlalchemy as sa

from alembic import op

revision = "0003_phase2_market_data"
down_revision = "0002_phase1_schema_alignment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("symbols", sa.Column("default_spread", sa.Numeric(18, 5), nullable=False, server_default="0.30"))
    op.create_table(
        "ticks",
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("symbols.id"), primary_key=True),
        sa.Column("source", sa.String(30), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True),
        *[sa.Column(name, sa.Numeric(18, 5), nullable=False) for name in ("bid", "ask", "spread")],
        sa.Column("volume", sa.Numeric(20, 5), nullable=False),
    )
    op.create_table(
        "candles",
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("symbols.id"), primary_key=True),
        sa.Column("source", sa.String(30), primary_key=True),
        sa.Column("timeframe", sa.String(3), primary_key=True),
        sa.Column("bucket_start", sa.DateTime(timezone=True), primary_key=True),
        *[sa.Column(name, sa.Numeric(18, 5), nullable=False)
          for name in ("open", "high", "low", "close", "bid_close", "ask_close")],
        sa.Column("volume", sa.Numeric(20, 5), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
    )


def downgrade():
    op.drop_table("candles")
    op.drop_table("ticks")
    op.drop_column("symbols", "default_spread")
