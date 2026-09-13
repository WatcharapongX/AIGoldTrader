"""Phase 5 Final Acceptance: persistent PaperAccountState, active reservation canonical intent uniqueness,
data health authority uniqueness, and audit-preserving downgrade barrier.
"""

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision = "0011_phase5_final_acceptance"
down_revision = "0010_phase5_safety_closure"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    now = dt.datetime.now(dt.UTC)
    payload_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    # 1. Create paper_account_states table as authoritative economic state of truth
    op.create_table(
        "paper_account_states",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("equity", sa.Numeric(18, 2), nullable=False),
        sa.Column("free_margin", sa.Numeric(18, 2), nullable=False),
        sa.Column("daily_realized_pnl", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("weekly_realized_pnl", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("floating_pnl", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("peak_equity", sa.Numeric(18, 2), nullable=False),
        sa.Column("open_risk_pct", sa.Numeric(10, 4), nullable=False, server_default="0.0000"),
        sa.Column("reserved_risk_pct", sa.Numeric(10, 4), nullable=False, server_default="0.0000"),
        sa.Column("open_positions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_loss_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", payload_type, nullable=False, server_default="{}"),
    )

    # 2. Add candidate_id column and unique constraint to risk_reservations
    op.add_column("risk_reservations", sa.Column("candidate_id", sa.String(64), nullable=True))

    # Backfill candidate_id from risk_decisions
    if not context.is_offline_mode():
        bind.execute(
            sa.text(
                "UPDATE risk_reservations "
                "SET candidate_id = ("
                "    SELECT candidate_id FROM risk_decisions "
                "    WHERE risk_decisions.id = risk_reservations.decision_id"
                ") "
                "WHERE candidate_id IS NULL"
            )
        )

        # Reconcile dirty duplicate active reservations deterministically (SOL High Round 3 Section 16)
        # Retain the one with the highest risk_pct (most conservative), release any duplicates
        dup_query = sa.text(
            "SELECT account_id, candidate_id "
            "FROM risk_reservations "
            "WHERE status = 'ACTIVE' AND candidate_id IS NOT NULL "
            "GROUP BY account_id, candidate_id "
            "HAVING COUNT(*) > 1"
        )
        dups = bind.execute(dup_query).fetchall()
        for d in dups:
            acc_id, cand_id = d[0], d[1]
            res_rows = bind.execute(
                sa.text(
                    "SELECT id, risk_pct FROM risk_reservations "
                    "WHERE account_id = :acc_id AND candidate_id = :cand_id AND status = 'ACTIVE' "
                    "ORDER BY risk_pct DESC, reserved_at DESC"
                ),
                {"acc_id": acc_id, "cand_id": cand_id},
            ).fetchall()
            if len(res_rows) > 1:
                for rem in res_rows[1:]:
                    bind.execute(
                        sa.text(
                            "UPDATE risk_reservations "
                            "SET status = 'RELEASED', "
                            "release_reason = 'MIGRATION_RECONCILED_DUPLICATE_ACTIVE_RESERVATION', "
                            "released_at = :now "
                            "WHERE id = :r_id"
                        ),
                        {"r_id": rem[0], "now": now},
                    )

    # Partial unique index for one active reservation per candidate/intent
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        bind.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
        op.create_index(
            "ix_risk_reservation_active_candidate",
            "risk_reservations",
            ["account_id", "candidate_id"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )
    else:
        op.create_index(
            "ix_risk_reservation_active_candidate",
            "risk_reservations",
            ["account_id", "candidate_id"],
            unique=True,
            sqlite_where=sa.text("status = 'ACTIVE'"),
        )

    # 3. Deduplicate dirty data_health_records before adding Unique constraint (SOL High Round 3 Section 17)
    if not context.is_offline_mode():
        dup_dh = bind.execute(
            sa.text(
                "SELECT provider, source "
                "FROM data_health_records "
                "GROUP BY provider, source "
                "HAVING COUNT(*) > 1"
            )
        ).fetchall()
        for d in dup_dh:
            prov, src = d[0], d[1]
            rows = bind.execute(
                sa.text(
                    "SELECT id, consecutive_failures, last_failure_at, last_healthy_at, updated_at "
                    "FROM data_health_records "
                    "WHERE provider = :prov AND source = :src "
                    "ORDER BY updated_at DESC"
                ),
                {"prov": prov, "src": src},
            ).fetchall()
            if len(rows) > 1:
                max_fails = max(r[1] for r in rows)
                fail_times = [r[2] for r in rows if r[2] is not None]
                latest_fail = max(fail_times) if fail_times else None
                health_times = [r[3] for r in rows if r[3] is not None]
                latest_health = max(health_times) if health_times else None
                latest_upd = max(r[4] for r in rows)
                keep_id = rows[0][0]

                bind.execute(
                    sa.text(
                        "UPDATE data_health_records "
                        "SET consecutive_failures = :fails, last_failure_at = :fail_at, "
                        "last_healthy_at = :health_at, updated_at = :upd_at "
                        "WHERE id = :keep_id"
                    ),
                    {
                        "fails": max_fails,
                        "fail_at": latest_fail,
                        "health_at": latest_health,
                        "upd_at": latest_upd,
                        "keep_id": keep_id,
                    },
                )
                for rem in rows[1:]:
                    bind.execute(
                        sa.text("DELETE FROM data_health_records WHERE id = :rem_id"),
                        {"rem_id": rem[0]},
                    )

    with op.batch_alter_table("data_health_records") as batch_op:
        batch_op.create_unique_constraint(
            "uq_data_health_provider_source",
            ["provider", "source"],
        )

    # 4. Bootstrap paper_account_states row per account (SOL High Round 3 Section 18)
    if not context.is_offline_mode():
        snaps = bind.execute(
            sa.text(
                "SELECT s.account_id, s.balance, s.equity, s.free_margin, s.daily_realized_pnl, "
                "s.weekly_realized_pnl, s.peak_equity, s.open_risk_pct, s.reserved_risk_pct, "
                "s.consecutive_losses, s.as_of, s.payload "
                "FROM account_snapshots s "
                "JOIN ("
                "    SELECT account_id, MAX(as_of) as max_as_of "
                "    FROM account_snapshots "
                "    GROUP BY account_id"
                ") m ON s.account_id = m.account_id AND s.as_of = m.max_as_of"
            )
        ).fetchall()
        for snap in snaps:
            acc_id = snap[0]
            bal = snap[1]
            eq = snap[2]
            fm = snap[3] if snap[3] is not None else eq
            dpnl = snap[4]
            wpnl = snap[5]
            peq = snap[6]
            orp = snap[7]
            rrp = snap[8]
            cl = snap[9]
            as_of = snap[10]
            bind.execute(
                sa.text(
                    "INSERT INTO paper_account_states "
                    "(account_id, state_version, balance, equity, free_margin, daily_realized_pnl, "
                    "weekly_realized_pnl, floating_pnl, peak_equity, open_risk_pct, reserved_risk_pct, "
                    "open_positions_count, consecutive_losses, last_loss_at, cooldown_until, "
                    "state_updated_at, last_observed_at, payload) "
                    "VALUES (:acc_id, 1, :bal, :eq, :fm, :dpnl, :wpnl, 0.00, :peq, :orp, :rrp, "
                    "0, :cl, NULL, NULL, :as_of, :now, '{}') "
                    "ON CONFLICT (account_id) DO NOTHING"
                ),
                {
                    "acc_id": acc_id,
                    "bal": bal,
                    "eq": eq,
                    "fm": fm,
                    "dpnl": dpnl,
                    "wpnl": wpnl,
                    "peq": peq,
                    "orp": orp,
                    "rrp": rrp,
                    "cl": cl,
                    "as_of": as_of,
                    "now": now,
                },
            )


def downgrade():
    bind = op.get_bind()

    # STRICT FORWARD SAFETY BARRIER:
    # Refuse downgrade if ANY Phase 5 audit or authority data exists in ANY table,
    # including bootstrap rows. Destructive downgrade of authoritative state is prohibited.
    tables_to_protect = (
        "paper_account_states",
        "data_health_records",
        "risk_policies",
        "symbol_specifications",
        "account_snapshots",
        "risk_decisions",
        "risk_reservations",
        "kill_switch_records",
    )
    for table in tables_to_protect:
        count = bind.scalar(sa.select(sa.func.count()).select_from(sa.table(table)))
        if count and count > 0:
            raise RuntimeError(
                f"Downgrade blocked by safety barrier: Phase 5 authority/audit records exist in {table} ({count} rows)"
            )

    # If all tables are completely empty, drop additions cleanly
    with op.batch_alter_table("data_health_records") as batch_op:
        batch_op.drop_constraint("uq_data_health_provider_source", type_="unique")
    op.drop_index("ix_risk_reservation_active_candidate", table_name="risk_reservations")
    with op.batch_alter_table("risk_reservations") as batch_op:
        batch_op.drop_column("candidate_id")
    op.drop_table("paper_account_states")
