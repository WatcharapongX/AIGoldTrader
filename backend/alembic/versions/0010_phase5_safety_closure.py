"""Phase 5 Safety Closure: persistent data health tracking, old MT5 seed quarantine, and downgrade audit protection."""

import datetime as dt
import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0010_phase5_safety_closure"
down_revision = "0009_phase5_final_hardening"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    now = dt.datetime.now(dt.UTC)
    epoch = dt.datetime(1970, 1, 1, 0, 0, 0, tzinfo=dt.UTC)

    # 1. Create data_health_records table for cross-process atomic data health tracking
    payload_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "data_health_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_healthy_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", payload_type, nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_data_health_provider_source",
        "data_health_records",
        ["provider", "source"],
    )

    if not context.is_offline_mode():
        # Seed initial data health tracking row
        bind.execute(
            sa.text(
                "INSERT INTO data_health_records "
                "(id, provider, source, consecutive_failures, last_failure_at, last_healthy_at, updated_at, payload) "
                "VALUES ('dh_default', 'mt5', 'mt5_demo_iux', 0, NULL, :now, :now, '{}') "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"now": now},
        )

        # 2. Repair old stamped databases: remove unverified fake MT5 seed if present
        bind.execute(
            sa.text(
                "DELETE FROM symbol_specifications WHERE id = 'sym_xauusd_mt5_demo_iux_seed'"
            )
        )

        # 3. Ensure Kill Switch ks_bootstrap timestamp is ancient epoch if historical records exist
        ks_count = bind.scalar(
            sa.select(sa.func.count())
            .select_from(sa.table("kill_switch_records"))
            .where(sa.column("id") != "ks_bootstrap")
        )
        if ks_count and ks_count > 0:
            bind.execute(
                sa.text("UPDATE kill_switch_records SET activated_at = :epoch WHERE id = 'ks_bootstrap'"),
                {"epoch": epoch},
            )

        # 4. Ensure any legacy decisions have unique dependency_fingerprint
        bind.execute(
            sa.text(
                "UPDATE risk_decisions "
                "SET dependency_fingerprint = 'legacy_' || id "
                "WHERE dependency_fingerprint IS NULL OR dependency_fingerprint = 'legacy_fingerprint'"
            )
        )


def downgrade():
    bind = op.get_bind()

    # STRICT FORWARD SAFETY BARRIER:
    # If ANY Phase 5 authority/audit data exists (beyond bootstrap seeds), refuse downgrade to protect audit history.
    for table in ("risk_decisions", "risk_reservations", "symbol_specifications"):
        count = bind.scalar(sa.select(sa.func.count()).select_from(sa.table(table)))
        if count and count > 0:
            raise RuntimeError(f"Downgrade blocked: Phase 5 audit records exist in {table}")

    # Check non-bootstrap policies
    pol_count = bind.scalar(
        sa.select(sa.func.count())
        .select_from(sa.table("risk_policies"))
        .where(sa.column("id") != "pol_risk-policy-1.0.0")
    )
    if pol_count and pol_count > 0:
        raise RuntimeError("Downgrade blocked: Phase 5 audit records exist in risk_policies")

    # Check non-bootstrap account snapshots
    snap_count = bind.scalar(
        sa.select(sa.func.count())
        .select_from(sa.table("account_snapshots"))
        .where(sa.column("id") != "snap_default_paper_account_init")
    )
    if snap_count and snap_count > 0:
        raise RuntimeError("Downgrade blocked: Phase 5 audit records exist in account_snapshots")

    # Check non-bootstrap kill switch records
    ks_count = bind.scalar(
        sa.select(sa.func.count())
        .select_from(sa.table("kill_switch_records"))
        .where(sa.column("id") != "ks_bootstrap")
    )
    if ks_count and ks_count > 0:
        raise RuntimeError("Downgrade blocked: Phase 5 audit records exist in kill_switch_records")

    # Drop data_health_records table
    op.drop_index("ix_data_health_provider_source", table_name="data_health_records")
    op.drop_table("data_health_records")
