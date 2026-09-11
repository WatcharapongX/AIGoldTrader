"""Phase 5 Corrective Hardening: deterministic fingerprint, reservation uniqueness, and kill switch bootstrap."""

import datetime as dt
import sqlalchemy as sa
from alembic import op

revision = "0008_phase5_hardening"
down_revision = "0007_risk_engine"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add dependency_fingerprint to risk_decisions
    op.add_column(
        "risk_decisions",
        sa.Column("dependency_fingerprint", sa.String(64), nullable=True),
    )
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE risk_decisions "
            "SET dependency_fingerprint = 'legacy_' || id "
            "WHERE dependency_fingerprint IS NULL OR dependency_fingerprint = 'legacy_fingerprint'"
        )
    )
    with op.batch_alter_table("risk_decisions") as batch_op:
        batch_op.alter_column("dependency_fingerprint", nullable=False)
        batch_op.create_index(
            "ix_risk_decision_fingerprint",
            ["candidate_id", "profile_id", "dependency_fingerprint"],
        )
        batch_op.create_unique_constraint(
            "uq_risk_decision_deterministic",
            ["candidate_id", "profile_id", "dependency_fingerprint"],
        )

    # 2. Reservation uniqueness per decision
    with op.batch_alter_table("risk_reservations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_risk_reservation_decision",
            ["decision_id"],
        )

    # 3. Seed authoritative bootstrap INACTIVE state for Kill Switch if table is empty
    # Use ancient epoch timestamp so historical ACTIVE records are strictly newer and authoritative
    epoch = dt.datetime(1970, 1, 1, 0, 0, 0, tzinfo=dt.UTC)
    bind.execute(
        sa.text(
            "INSERT INTO kill_switch_records "
            "(id, state, trigger_type, reason_th, activated_at, activated_by, policy_version, payload) "
            "VALUES ('ks_bootstrap', 'INACTIVE', 'MANUAL', 'ระบบเริ่มต้นทำงานในสภาวะปกติ (System Bootstrap)', "
            ":epoch, 'system_bootstrap', 'risk-policy-1.0.0', '{}') "
            "ON CONFLICT DO NOTHING"
        ),
        {"epoch": epoch},
    )


def downgrade():
    for table in ("risk_decisions", "risk_reservations"):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(table))):
            raise RuntimeError(f"Downgrade blocked: preserve {table} audit history")

    ks_non_bootstrap = op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(sa.table("kill_switch_records"))
        .where(sa.column("id") != "ks_bootstrap")
    )
    if ks_non_bootstrap:
        raise RuntimeError("Downgrade blocked: preserve kill_switch_records audit history")

    op.execute(sa.text("DELETE FROM kill_switch_records WHERE id = 'ks_bootstrap'"))

    with op.batch_alter_table("risk_reservations") as batch_op:
        batch_op.drop_constraint("uq_risk_reservation_decision", type_="unique")

    with op.batch_alter_table("risk_decisions") as batch_op:
        batch_op.drop_constraint("uq_risk_decision_deterministic", type_="unique")
        batch_op.drop_index("ix_risk_decision_fingerprint")
        batch_op.drop_column("dependency_fingerprint")
