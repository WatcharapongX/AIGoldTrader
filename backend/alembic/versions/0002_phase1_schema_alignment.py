"""Align Phase 1 JSON types with the documented PostgreSQL JSONB design.

Revision ID: 0002_phase1_schema_alignment
Revises: 0001_initial

Preserve the applied initial revision and the existing refresh-token unique index.
JSONB preserves values, not JSON whitespace/key ordering; preflight existing JSON
for duplicate keys and JSONB-incompatible values before upgrading populated DBs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_phase1_schema_alignment"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("audit_logs", "before", True),
    ("audit_logs", "after", True),
    ("symbols", "session_hours", False),
    ("system_events", "payload", True),
)


def upgrade() -> None:
    # SQLite unit tests intentionally retain the ORM's JSON variant.
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, nullable in _COLUMNS:
        op.alter_column(
            table, column, existing_type=sa.JSON(), type_=postgresql.JSONB(),
            existing_nullable=nullable, postgresql_using=f'"{column}"::jsonb',
        )
    op.alter_column("symbols", "session_hours", server_default=sa.text("'{}'::jsonb"))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, nullable in reversed(_COLUMNS):
        op.alter_column(
            table, column, existing_type=postgresql.JSONB(), type_=sa.JSON(),
            existing_nullable=nullable, postgresql_using=f'"{column}"::json',
        )
    op.alter_column("symbols", "session_hours", server_default=sa.text("'{}'::json"))
