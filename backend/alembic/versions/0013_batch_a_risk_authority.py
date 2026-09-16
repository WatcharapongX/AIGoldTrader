"""Batch A remediation: add account_id to risk_decisions with backfill and canonical authority.

Enforces account isolation and invariant matching for AUD-P1-003 and AUD-P1-004.
"""

import sqlalchemy as sa

from alembic import context, op

revision = "0013_batch_a_risk_authority"
down_revision = "0012_phase5_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # 1. Add account_id column to risk_decisions as nullable initially
    op.add_column(
        "risk_decisions",
        sa.Column("account_id", sa.String(64), nullable=True),
    )

    if not context.is_offline_mode():
        if bind.dialect.name == "postgresql":
            # 2. Backfill account_id from joined account_snapshots table
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions rd "
                    "SET account_id = s.account_id "
                    "FROM account_snapshots s "
                    "WHERE rd.account_snapshot_id = s.id AND rd.account_id IS NULL"
                )
            )

            # 3. Defensive backfill from risk_reservations if snapshot match was absent
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions rd "
                    "SET account_id = r.account_id "
                    "FROM risk_reservations r "
                    "WHERE rd.id = r.decision_id AND rd.account_id IS NULL"
                )
            )

            # 4. Fallback for any orphaned decision rows
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions "
                    "SET account_id = 'default_paper_account' "
                    "WHERE account_id IS NULL"
                )
            )

            # 5. Reconcile any account name aliases in paper_account_states and account_snapshots to canonical Account UUIDs
            bind.execute(
                sa.text(
                    "UPDATE paper_account_states p "
                    "SET account_id = CAST(a.id AS VARCHAR) "
                    "FROM accounts a "
                    "WHERE p.account_id = a.name"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE account_snapshots s "
                    "SET account_id = CAST(a.id AS VARCHAR) "
                    "FROM accounts a "
                    "WHERE s.account_id = a.name"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions rd "
                    "SET account_id = CAST(a.id AS VARCHAR) "
                    "FROM accounts a "
                    "WHERE rd.account_id = a.name"
                )
            )
        else:
            # SQLite / standard SQL correlated updates
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions "
                    "SET account_id = (SELECT s.account_id FROM account_snapshots s WHERE risk_decisions.account_snapshot_id = s.id) "
                    "WHERE account_id IS NULL AND EXISTS (SELECT 1 FROM account_snapshots s WHERE risk_decisions.account_snapshot_id = s.id)"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions "
                    "SET account_id = (SELECT r.account_id FROM risk_reservations r WHERE risk_decisions.id = r.decision_id) "
                    "WHERE account_id IS NULL AND EXISTS (SELECT 1 FROM risk_reservations r WHERE risk_decisions.id = r.decision_id)"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions "
                    "SET account_id = 'default_paper_account' "
                    "WHERE account_id IS NULL"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE paper_account_states "
                    "SET account_id = (SELECT CAST(a.id AS VARCHAR) FROM accounts a WHERE paper_account_states.account_id = a.name) "
                    "WHERE EXISTS (SELECT 1 FROM accounts a WHERE paper_account_states.account_id = a.name)"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE account_snapshots "
                    "SET account_id = (SELECT CAST(a.id AS VARCHAR) FROM accounts a WHERE account_snapshots.account_id = a.name) "
                    "WHERE EXISTS (SELECT 1 FROM accounts a WHERE account_snapshots.account_id = a.name)"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions "
                    "SET account_id = (SELECT CAST(a.id AS VARCHAR) FROM accounts a WHERE risk_decisions.account_id = a.name) "
                    "WHERE EXISTS (SELECT 1 FROM accounts a WHERE risk_decisions.account_id = a.name)"
                )
            )

    # 6. Alter column to NOT NULL and create index (batch_alter_table supports SQLite & Postgres)
    with op.batch_alter_table("risk_decisions") as batch_op:
        batch_op.alter_column(
            "account_id",
            existing_type=sa.String(64),
            nullable=False,
        )
        batch_op.create_index(
            "ix_risk_decision_account_as_of",
            ["account_id", "as_of"],
        )


def downgrade():
    bind = op.get_bind()

    # STRICT FORWARD SAFETY BARRIER:
    # Refuse downgrade if authority or audit records exist in risk_decisions
    count = bind.scalar(sa.select(sa.func.count()).select_from(sa.table("risk_decisions")))
    if count and count > 0:
        raise RuntimeError(
            f"Downgrade blocked by safety barrier: authority records exist in risk_decisions ({count} rows)"
        )

    with op.batch_alter_table("risk_decisions") as batch_op:
        batch_op.drop_index("ix_risk_decision_account_as_of")
        batch_op.drop_column("account_id")
