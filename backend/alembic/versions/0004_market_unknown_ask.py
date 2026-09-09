"""Represent unavailable historical ask-close honestly; preserve all existing data."""
import sqlalchemy as sa

from alembic import op

revision = "0004_market_unknown_ask"
down_revision = "0003_phase2_market_data"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("candles") as batch:
        batch.alter_column("ask_close", existing_type=sa.Numeric(18, 5), nullable=True)


def downgrade():
    # Never fabricate an ask or delete real candles to satisfy the older contract.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM candles WHERE ask_close IS NULL")):
        raise RuntimeError("Downgrade blocked: historical ask-close is unknown; retain revision 0004")
    with op.batch_alter_table("candles") as batch:
        batch.alter_column("ask_close", existing_type=sa.Numeric(18, 5), nullable=False)
