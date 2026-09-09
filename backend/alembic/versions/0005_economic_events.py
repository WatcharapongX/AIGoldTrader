"""Economic occurrence identities and append-only point-in-time revisions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_economic_events"
down_revision = "0004_market_unknown_ask"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "economic_events",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("provider_event_id", sa.String(100), nullable=False),
        sa.Column("occurrence_key", sa.String(100), nullable=False),
        sa.UniqueConstraint("source", "provider_event_id", "occurrence_key", name="uq_economic_occurrence"),
    )
    op.create_table(
        "economic_event_revisions",
        sa.Column("event_id", sa.String(100), sa.ForeignKey("economic_events.id"), primary_key=True),
        sa.Column("revision_version", sa.Integer(), primary_key=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
    )
    op.create_index("ix_economic_available", "economic_event_revisions", ["available_at", "event_id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM economic_events")):
        raise RuntimeError("Downgrade blocked: preserve economic event revision history")
    op.drop_index("ix_economic_available", table_name="economic_event_revisions")
    op.drop_table("economic_event_revisions")
    op.drop_table("economic_events")
