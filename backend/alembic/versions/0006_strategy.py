"""Phase 4 immutable analysis-only evaluation history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_strategy"
down_revision = "0005_economic_events"
branch_labels = None
depends_on = None
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "trader_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("config_id", sa.String(64), nullable=False),
        sa.Column("payload", JSON, nullable=False),
        sa.UniqueConstraint("profile_id", "config_id", name="uq_trader_profile_version"),
    )
    op.create_table(
        "strategy_evaluations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("context_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", JSON, nullable=False),
    )
    op.create_index("ix_strategy_evaluation_asof", "strategy_evaluations", ["symbol", "source", "as_of"])
    op.create_table(
        "trade_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("evaluation_id", sa.String(64), sa.ForeignKey("strategy_evaluations.id"), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("strategy_id", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSON, nullable=False),
        sa.UniqueConstraint("evaluation_id", "profile_id", "strategy_id", name="uq_strategy_candidate"),
    )
    op.create_table(
        "candidate_transitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("candidate_id", sa.String(64), sa.ForeignKey("trade_candidates.id"), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSON, nullable=False),
    )
    op.create_index("ix_candidate_transition_asof", "candidate_transitions", ["candidate_id", "as_of"])


def downgrade():
    for table in ("strategy_evaluations", "trader_profiles"):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(table))):
            raise RuntimeError("Downgrade blocked: preserve strategy evaluation/profile history")
    op.drop_index("ix_candidate_transition_asof", table_name="candidate_transitions")
    op.drop_table("candidate_transitions")
    op.drop_table("trade_candidates")
    op.drop_index("ix_strategy_evaluation_asof", table_name="strategy_evaluations")
    op.drop_table("strategy_evaluations")
    op.drop_table("trader_profiles")
