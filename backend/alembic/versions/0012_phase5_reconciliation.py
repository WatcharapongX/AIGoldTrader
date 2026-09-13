"""Phase 5 Round 3 Reconciliation: forward migration for already-stamped 0011 databases.

Reconciles multi-account paper state backfill and enforces strict downgrade safety barrier.
"""

import datetime as dt

import sqlalchemy as sa

from alembic import context, op

revision = "0012_phase5_reconciliation"
down_revision = "0011_phase5_final_acceptance"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    now = dt.datetime.now(dt.UTC)

    if not context.is_offline_mode():
        # 1. Backfill any missing accounts in paper_account_states from account_snapshots per account
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
    # Refuse downgrade if ANY Phase 5 audit or authority data exists in ANY table.
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
