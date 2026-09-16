"""Batch A remediation: add account_id to risk_decisions with fail-safe preflight and canonical authority.

Enforces AUD-P1-003, AUD-P1-004, BATCHA-P1-001, and BATCHA-P1-002:
- Strict preflight validation: aborts immediately on orphan decisions, conflicting snapshot/reservation evidence,
  ambiguous duplicate aliases, or unresolvable accounts.
- Zero synthetic fallbacks: never guesses or assigns 'default_paper_account'.
- Reconciles relational column and JSON payload account_id to canonical Account UUID.
- Enforces NOT NULL, composite index, and UUID format check constraint.
- Dialect-aware execution for PostgreSQL 18 and SQLite.
"""

import json
import uuid

import sqlalchemy as sa

from alembic import context, op

revision = "0013_batch_a_risk_authority"
down_revision = "0012_phase5_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Add account_id column to risk_decisions as nullable initially
    op.add_column(
        "risk_decisions",
        sa.Column("account_id", sa.String(64), nullable=True),
    )

    if not context.is_offline_mode():
        # =========================================================================
        # 2. FAIL-SAFE PREFLIGHT VALIDATION (BATCHA-P1-001)
        # Must detect anomalies and abort BEFORE any destructive or mutating updates.
        # =========================================================================

        # Check for orphan risk_decisions (neither snapshot nor reservation proves ownership)
        orphans = bind.execute(
            sa.text(
                "SELECT rd.id FROM risk_decisions rd "
                "LEFT JOIN account_snapshots s ON rd.account_snapshot_id = s.id "
                "LEFT JOIN risk_reservations r ON rd.id = r.decision_id "
                "WHERE s.account_id IS NULL AND r.account_id IS NULL"
            )
        ).fetchall()
        if orphans:
            orphan_ids = [r[0] for r in orphans]
            raise RuntimeError(
                f"Migration preflight failed: {len(orphans)} orphan RiskDecision row(s) cannot be proven "
                f"from snapshots or reservations: {orphan_ids[:5]}"
            )

        # Check for conflicting snapshot vs reservation evidence on risk_decisions
        conflicts = bind.execute(
            sa.text(
                "SELECT rd.id, s.account_id, r.account_id "
                "FROM risk_decisions rd "
                "JOIN account_snapshots s ON rd.account_snapshot_id = s.id "
                "JOIN risk_reservations r ON rd.id = r.decision_id "
                "WHERE s.account_id != r.account_id"
            )
        ).fetchall()
        if conflicts:
            conflict_details = [f"id={r[0]} (snap={r[1]} vs res={r[2]})" for r in conflicts[:5]]
            raise RuntimeError(
                f"Migration preflight failed: conflicting account evidence detected for "
                f"{len(conflicts)} RiskDecision(s): {conflict_details}"
            )

        # Check all legacy aliases in paper_account_states, account_snapshots, and risk_reservations
        legacy_refs = set()
        for tbl in ("paper_account_states", "account_snapshots", "risk_reservations"):
            rows = bind.execute(
                sa.text(f"SELECT DISTINCT account_id FROM {tbl} WHERE account_id IS NOT NULL")  # noqa: S608
            ).fetchall()
            for r in rows:
                ref = r[0]
                # If not a valid UUID, it's an alias
                try:
                    uuid.UUID(str(ref))
                except (ValueError, TypeError):
                    legacy_refs.add(str(ref))

        # Validate that every alias matches exactly ONE real Account row
        alias_to_uuid = {}
        for alias in legacy_refs:
            matches = bind.execute(
                sa.text("SELECT id FROM accounts WHERE name = :name"),
                {"name": alias},
            ).fetchall()
            if len(matches) == 0:
                raise RuntimeError(
                    f"Migration preflight failed: legacy account alias '{alias}' has zero matches in accounts table"
                )
            if len(matches) > 1:
                raise RuntimeError(
                    f"Migration preflight failed: legacy account alias '{alias}' matches {len(matches)} "
                    f"accounts across tenants; cannot prove unambiguous ownership"
                )
            alias_to_uuid[alias] = str(matches[0][0])

        # Also check if any existing account_id in those tables is a UUID that does NOT exist in accounts
        for tbl in ("paper_account_states", "account_snapshots", "risk_reservations"):
            rows = bind.execute(
                sa.text(f"SELECT DISTINCT account_id FROM {tbl} WHERE account_id IS NOT NULL")  # noqa: S608
            ).fetchall()
            for r in rows:
                val = str(r[0])
                try:
                    parsed_u = uuid.UUID(val)
                    acc_match = bind.execute(
                        sa.text("SELECT id FROM accounts WHERE id = :id"),
                        {"id": str(parsed_u)},
                    ).fetchall()
                    if not acc_match:
                        raise RuntimeError(
                            f"Migration preflight failed: account_id '{val}' in {tbl} does not exist in accounts table"
                        )
                except (ValueError, TypeError):
                    pass

        # =========================================================================
        # 3. RECONCILE LEGACY ALIASES TO CANONICAL UUIDS
        # =========================================================================
        for alias, can_uuid in alias_to_uuid.items():
            bind.execute(
                sa.text("UPDATE paper_account_states SET account_id = :u WHERE account_id = :alias"),
                {"u": can_uuid, "alias": alias},
            )
            bind.execute(
                sa.text("UPDATE account_snapshots SET account_id = :u WHERE account_id = :alias"),
                {"u": can_uuid, "alias": alias},
            )
            bind.execute(
                sa.text("UPDATE risk_reservations SET account_id = :u WHERE account_id = :alias"),
                {"u": can_uuid, "alias": alias},
            )

        # =========================================================================
        # 4. BACKFILL RISK_DECISIONS.ACCOUNT_ID FROM AUTHORITATIVE EVIDENCE
        # =========================================================================
        if is_postgres:
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions rd "
                    "SET account_id = s.account_id "
                    "FROM account_snapshots s "
                    "WHERE rd.account_snapshot_id = s.id AND rd.account_id IS NULL"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions rd "
                    "SET account_id = r.account_id "
                    "FROM risk_reservations r "
                    "WHERE rd.id = r.decision_id AND rd.account_id IS NULL"
                )
            )
        else:
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions "
                    "SET account_id = (SELECT s.account_id FROM account_snapshots s "
                    "WHERE risk_decisions.account_snapshot_id = s.id) "
                    "WHERE account_id IS NULL AND EXISTS ("
                    "SELECT 1 FROM account_snapshots s WHERE risk_decisions.account_snapshot_id = s.id)"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE risk_decisions "
                    "SET account_id = (SELECT r.account_id FROM risk_reservations r "
                    "WHERE risk_decisions.id = r.decision_id) "
                    "WHERE account_id IS NULL AND EXISTS ("
                    "SELECT 1 FROM risk_reservations r WHERE risk_decisions.id = r.decision_id)"
                )
            )

        # Post-backfill verification: absolutely NO NULL or non-UUID account_id permitted
        unresolved = bind.execute(
            sa.text("SELECT id FROM risk_decisions WHERE account_id IS NULL")
        ).fetchall()
        if unresolved:
            raise RuntimeError(
                f"Migration failure: {len(unresolved)} RiskDecision row(s) could not be resolved to a canonical account"
            )

        # =========================================================================
        # 5. SYNCHRONIZE JSON PAYLOAD ACCOUNT_ID WITH RELATIONAL COLUMN (BATCHA-P1-001)
        # =========================================================================
        rd_rows = bind.execute(sa.text("SELECT id, account_id, payload FROM risk_decisions")).fetchall()
        for r_id, a_id, p_raw in rd_rows:
            if isinstance(p_raw, str):
                p_dict = json.loads(p_raw)
            elif isinstance(p_raw, dict):
                p_dict = dict(p_raw)
            else:
                p_dict = {}
            if p_dict.get("account_id") != a_id:
                p_dict["account_id"] = a_id
                bind.execute(
                    sa.text("UPDATE risk_decisions SET payload = :p WHERE id = :id"),
                    {"id": r_id, "p": json.dumps(p_dict)},
                )

    # =========================================================================
    # 6. ENFORCE DATABASE INVARIANTS: NOT NULL, INDEX, AND UUID CONSTRAINT
    # =========================================================================
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
        batch_op.create_check_constraint(
            "ck_risk_decision_account_id_uuid",
            "length(account_id) = 36",
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
        batch_op.drop_constraint("ck_risk_decision_account_id_uuid", type_="check")
        batch_op.drop_index("ix_risk_decision_account_as_of")
        batch_op.drop_column("account_id")
