"""Batch A.3: Referential Integrity Closure and Native Account Foreign Key.

Revision ID: 0015_batch_a3_risk_account_fk
Revises: 0014_batch_a2_account_authority
Create Date: 2026-09-17

Solves BATCHA2-NEW-P1-001 and BATCHA2-NEW-P2-001:
1. Converts risk_decisions.account_id to native UUID.
2. Enforces real foreign key to accounts(id) with ON DELETE RESTRICT semantics.
3. Enforces continuous database-level payload equality via check constraint.
4. Removes redundant 0014 workaround trigger/function.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "0015_batch_a3_risk_account_fk"
down_revision: str | None = "0014_batch_a2_account_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.0015_batch_a3_risk_account_fk")


def _run_preflight_checks(bind: sa.engine.Connection) -> None:
    """Preflight checks ensuring all rows satisfy strict referential integrity."""
    logger.info("Executing 0015 preflight verification...")

    # Fetch all rows from risk_decisions
    rows = bind.execute(sa.text("SELECT id, account_id, payload FROM risk_decisions")).fetchall()
    if not rows:
        logger.info("Preflight 0015: risk_decisions is empty. Preflight passed.")
        return

    # Check 1: Every account_id parses as UUID
    # Check 2: Every account_id exists in accounts(id)
    # Check 3: Payload has account_id and it parses as UUID
    # Check 4: Payload account_id equals relational account_id
    for r in rows:
        row_id, rel_account_id, payload = r[0], str(r[1]), r[2]
        try:
            parsed_rel = uuid.UUID(rel_account_id)
        except (ValueError, TypeError) as err:
            raise RuntimeError(
                f"Preflight 0015 FAIL: risk_decision '{row_id}' has malformed account_id '{rel_account_id}'"
            ) from err

        # Check account existence in accounts table
        acc_exists = bind.execute(
            sa.text("SELECT 1 FROM accounts WHERE id = :acc_id"),
            {"acc_id": str(parsed_rel)},
        ).scalar()
        if not acc_exists:
            raise RuntimeError(
                f"Preflight 0015 FAIL: risk_decision '{row_id}' references non-existent account '{parsed_rel}'"
            )

        # Check payload
        if not payload or not isinstance(payload, dict):
            raise RuntimeError(f"Preflight 0015 FAIL: risk_decision '{row_id}' has missing or non-dict payload")

        payload_account_id = payload.get("account_id")
        if not payload_account_id:
            raise RuntimeError(f"Preflight 0015 FAIL: risk_decision '{row_id}' payload is missing 'account_id'")

        try:
            parsed_payload = uuid.UUID(str(payload_account_id))
        except (ValueError, TypeError) as err:
            raise RuntimeError(
                f"Preflight 0015 FAIL: risk_decision '{row_id}' payload account_id '{payload_account_id}' is malformed"
            ) from err

        if parsed_payload != parsed_rel:
            raise RuntimeError(
                f"Preflight 0015 FAIL: risk_decision '{row_id}' relational account '{parsed_rel}' "
                f"does not match payload account '{parsed_payload}'"
            )

    logger.info("Preflight 0015: All %d existing risk_decisions rows passed verification.", len(rows))


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1. Run Preflight
    if not context.is_offline_mode():
        _run_preflight_checks(bind)

    if is_pg:
        # 2. Drop 0014 workaround trigger & function
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_risk_decision_account_fk ON risk_decisions;"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS check_risk_decision_account_exists();"))

        # 3. Drop 0014 check constraint
        op.execute(sa.text(
            "ALTER TABLE risk_decisions DROP CONSTRAINT IF EXISTS ck_risk_decision_account_id_strict_uuid;"
        ))

        # 4. Alter column type to UUID
        op.execute(sa.text("ALTER TABLE risk_decisions ALTER COLUMN account_id TYPE UUID USING account_id::uuid;"))

        # 5. Add real Foreign Key with ON DELETE RESTRICT
        op.execute(sa.text(
            "ALTER TABLE risk_decisions "
            "ADD CONSTRAINT fk_risk_decisions_account_id_accounts "
            "FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT;"
        ))

        # 6. Add continuous payload consistency check constraint
        op.execute(sa.text(
            "ALTER TABLE risk_decisions "
            "ADD CONSTRAINT ck_risk_decision_payload_account_id "
            "CHECK ((payload ? 'account_id') AND ((payload ->> 'account_id')::uuid = account_id));"
        ))
    else:
        # SQLite batch mode
        with op.batch_alter_table("risk_decisions") as batch_op:
            batch_op.create_foreign_key(
                "fk_risk_decisions_account_id_accounts",
                "accounts",
                ["account_id"],
                ["id"],
                ondelete="RESTRICT",
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # 1. Drop payload check constraint
        op.execute(sa.text("ALTER TABLE risk_decisions DROP CONSTRAINT IF EXISTS ck_risk_decision_payload_account_id;"))

        # 2. Drop real Foreign Key
        op.execute(sa.text(
            "ALTER TABLE risk_decisions DROP CONSTRAINT IF EXISTS fk_risk_decisions_account_id_accounts;"
        ))

        # 3. Alter column back to VARCHAR(64)
        op.execute(sa.text(
            "ALTER TABLE risk_decisions ALTER COLUMN account_id TYPE VARCHAR(64) USING account_id::text;"
        ))

        # 4. Re-add regex check constraint
        op.execute(sa.text(
            "ALTER TABLE risk_decisions "
            "ADD CONSTRAINT ck_risk_decision_account_id_strict_uuid "
            "CHECK (account_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');"
        ))

        # 5. Recreate function & trigger
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION check_risk_decision_account_exists()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM accounts WHERE id = NEW.account_id::uuid) THEN
                    RAISE EXCEPTION 'Foreign key violation: account % does not exist in accounts', NEW.account_id;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_risk_decision_account_fk
            AFTER INSERT OR UPDATE ON risk_decisions
            FOR EACH ROW EXECUTE FUNCTION check_risk_decision_account_exists();
        """))
    else:
        with op.batch_alter_table("risk_decisions") as batch_op:
            batch_op.drop_constraint("fk_risk_decisions_account_id_accounts", type_="foreignkey")
