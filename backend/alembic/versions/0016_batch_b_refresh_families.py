"""Batch B1: atomic refresh rotation and session families.

Revision ID: 0016_batch_b_refresh_families
Revises: 0015_batch_a3_risk_account_fk
Create Date: 2026-09-18

Existing rows are retained and assigned deterministic one-row families. Active
legacy sessions are revoked once because their credentials predate the atomic
consume model. Downgrade never reactivates those sessions.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_batch_b_refresh_families"
down_revision: str | None = "0015_batch_a3_risk_account_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("family_id", sa.Uuid(), nullable=True))
    op.add_column("sessions", sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(sa.text("UPDATE sessions SET family_id = id WHERE family_id IS NULL"))
    op.execute(sa.text("UPDATE sessions SET revoked_at = CURRENT_TIMESTAMP WHERE revoked_at IS NULL"))

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("family_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_index("ix_sessions_family_id", ["family_id"], unique=False)


def downgrade() -> None:
    # Never undo cutover revocations when rolling schema back.
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_family_id")
        batch_op.drop_column("consumed_at")
        batch_op.drop_column("family_id")
