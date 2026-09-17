"""Batch A.2: Canonical Account Authority Hardening and Database Invariants.

Enforces:
- AUD-P1-004, BATCHA1-NEW-P1-001, BATCHA1-NEW-P2-002:
  - Strong preflight verification: all RiskDecision account_ids are valid UUIDs,
    all accounts exist in accounts table, relational and payload account_ids are synchronized,
    and no legacy aliases remain across risk tables.
  - Replaces length check constraint with strict UUID regex constraint:
    account_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  - Installs database-level trigger trg_risk_decision_account_fk in PostgreSQL
    to enforce relational foreign-key integrity between risk_decisions and accounts.
- Dialect-aware execution supporting both PostgreSQL 18 and SQLite.
"""

import json
import uuid

import sqlalchemy as sa

from alembic import context, op

revision = "0014_batch_a2_account_authority"
down_revision = "0013_batch_a_risk_authority"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not context.is_offline_mode():
        # 1. Preflight Validation: all RiskDecision account_ids must be valid UUIDs
        rows = bind.execute(sa.text("SELECT id, account_id, payload FROM risk_decisions")).fetchall()
        for r_id, acc_id, payload in rows:
            try:
                parsed_u = uuid.UUID(str(acc_id))
            except (ValueError, TypeError):
                raise RuntimeError(
                    f"Migration 0014 preflight failed: risk_decisions row '{r_id}' "
                    f"has non-UUID account_id '{acc_id}'"
                ) from None

            # Ensure payload is synchronized with relational account_id
            if payload is not None:
                p_dict = json.loads(payload) if isinstance(payload, str) else dict(payload)
                p_acc = p_dict.get("account_id")
                if p_acc and p_acc != str(parsed_u):
                    raise RuntimeError(
                        f"Migration 0014 preflight failed: risk_decisions row '{r_id}' "
                        f"has payload account_id mismatch (relational={acc_id} vs payload={p_acc})"
                    )

        # 2. Preflight Validation: all referenced accounts must exist in accounts table
        if is_postgres:
            orphans = bind.execute(
                sa.text(
                    "SELECT id, account_id FROM risk_decisions "
                    "WHERE account_id::uuid NOT IN (SELECT id FROM accounts)"
                )
            ).fetchall()
        else:
            # SQLite: accounts.id may be stored as 32-char hex without hyphens or standard UUID string
            orphans = bind.execute(
                sa.text(
                    "SELECT id, account_id FROM risk_decisions "
                    "WHERE account_id NOT IN (SELECT id FROM accounts) "
                    "AND replace(lower(account_id), '-', '') NOT IN (SELECT lower(id) FROM accounts)"
                )
            ).fetchall()

        if orphans:
            orphan_details = [f"id={r[0]} acc={r[1]}" for r in orphans[:5]]
            raise RuntimeError(
                f"Migration 0014 preflight failed: {len(orphans)} risk_decisions row(s) "
                f"reference non-existent accounts: {orphan_details}"
            )

        # 3. Preflight Validation: verify no legacy aliases remain across other risk tables
        for tbl in ("paper_account_states", "account_snapshots", "risk_reservations"):
            if is_postgres:
                tbl_exists = bind.execute(
                    sa.text("SELECT to_regclass(:t)"),
                    {"t": tbl},
                ).scalar()
            else:
                tbl_exists = bind.execute(
                    sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :t"),
                    {"t": tbl},
                ).fetchone()
            if not tbl_exists:
                continue

            tbl_rows = bind.execute(
                sa.text(f"SELECT DISTINCT account_id FROM {tbl} WHERE account_id IS NOT NULL")  # noqa: S608
            ).fetchall()
            for r in tbl_rows:
                try:
                    uuid.UUID(str(r[0]))
                except (ValueError, TypeError):
                    raise RuntimeError(
                        f"Migration 0014 preflight failed: table '{tbl}' contains legacy alias '{r[0]}'"
                    ) from None

    # 4. Schema Invariant Updates
    if is_postgres:
        # Drop legacy length-36 check constraint
        bind.execute(
            sa.text(
                "ALTER TABLE risk_decisions "
                "DROP CONSTRAINT IF EXISTS ck_risk_decisions_ck_risk_decision_account_id_uuid"
            )
        )

        # Add strict UUID regex check constraint
        bind.execute(
            sa.text(
                "ALTER TABLE risk_decisions "
                "ADD CONSTRAINT ck_risk_decision_account_id_strict_uuid "
                "CHECK (account_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')"
            )
        )

        # Install database trigger for relational foreign-key enforcement
        bind.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION check_risk_decision_account_exists()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM accounts WHERE id = NEW.account_id::uuid) THEN
                        RAISE EXCEPTION 'Foreign key violation: account_id % does not exist in accounts',
                            NEW.account_id;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        bind.execute(
            sa.text(
                """
                DROP TRIGGER IF EXISTS trg_risk_decision_account_fk ON risk_decisions;
                CREATE TRIGGER trg_risk_decision_account_fk
                AFTER INSERT OR UPDATE ON risk_decisions
                FOR EACH ROW EXECUTE FUNCTION check_risk_decision_account_exists();
                """
            )
        )


def downgrade():
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_risk_decision_account_fk ON risk_decisions;"))
        bind.execute(sa.text("DROP FUNCTION IF EXISTS check_risk_decision_account_exists();"))
        bind.execute(
            sa.text(
                "ALTER TABLE risk_decisions "
                "DROP CONSTRAINT IF EXISTS ck_risk_decision_account_id_strict_uuid"
            )
        )
        bind.execute(
            sa.text(
                "ALTER TABLE risk_decisions "
                "ADD CONSTRAINT ck_risk_decisions_ck_risk_decision_account_id_uuid "
                "CHECK (length(account_id) = 36)"
            )
        )
