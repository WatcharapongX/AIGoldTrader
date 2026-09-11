"""Phase 5 Final Hardening: singleton policy index, legacy decision repair, kill switch timestamp repair, and audit safety."""

import datetime as dt
import json
import sqlalchemy as sa
from alembic import context, op

revision = "0009_phase5_final_hardening"
down_revision = "0008_phase5_hardening"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    now = dt.datetime.now(dt.UTC)
    epoch = dt.datetime(1970, 1, 1, 0, 0, 0, tzinfo=dt.UTC)

    if not context.is_offline_mode():
        # 1. Repair Kill Switch bootstrap timestamp:
        # If other kill_switch_records exist (e.g. historical ACTIVE states), ensure ks_bootstrap
        # has an ancient timestamp (epoch) so that historical state is preserved as authoritative.
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

        # 2. Repair legacy decisions with unique deterministic fingerprints
        # before asserting deterministic unique index
        bind.execute(
            sa.text(
                "UPDATE risk_decisions "
                "SET dependency_fingerprint = 'legacy_' || id "
                "WHERE dependency_fingerprint = 'legacy_fingerprint'"
            )
        )

        # 3. Singleton active Risk Policy: partial unique index on is_active = true
        # First, deactivate any duplicate active policies if multiple exist, keeping the newest
        active_policies = bind.execute(
            sa.text("SELECT id, created_at FROM risk_policies WHERE is_active = true ORDER BY created_at DESC")
        ).fetchall()
        if len(active_policies) > 1:
            deactivate_ids = [r[0] for r in active_policies[1:]]
            bind.execute(
                sa.text("UPDATE risk_policies SET is_active = false WHERE id = ANY(:ids)"),
                {"ids": deactivate_ids},
            )

    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_risk_policy_single_active",
            "risk_policies",
            ["is_active"],
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        )

    if not context.is_offline_mode():
        # 4. Seed authoritative active RiskPolicy if none exists
        has_active_policy = bind.scalar(
            sa.select(sa.func.count())
            .select_from(sa.table("risk_policies"))
            .where(sa.column("is_active") == True)  # noqa: E712
        )
        if not has_active_policy:
            default_policy_payload = {
                "version": "risk-policy-1.0.0",
                "max_risk_per_trade_pct": "1.0",
                "min_risk_per_trade_pct": "0.1",
                "max_account_risk_pct": "3.0",
                "max_symbol_risk_pct": "2.0",
                "max_directional_risk_pct": "2.0",
                "max_concurrent_trades": 3,
                "daily_loss_limit_pct": "3.0",
                "weekly_loss_limit_pct": "6.0",
                "max_drawdown_pct": "10.0",
                "cooldown_consecutive_losses": 3,
                "cooldown_period_minutes": 60,
                "max_spread_multiplier": "2.0",
                "max_spread_absolute": "1.50",
                "quote_freshness_seconds": 5,
                "account_freshness_seconds": 60,
                "news_risk_enabled": True,
                "news_high_impact_blackout_pre_minutes": 5,
                "news_high_impact_pre_minutes": 15,
                "news_high_impact_post_minutes": 15,
                "news_reduction_factor": "0.5",
                "min_volume": "0.01",
                "max_volume": "10.00",
                "volume_step": "0.01",
                "reservation_ttl_seconds": 300,
            }
            bind.execute(
                sa.text(
                    "INSERT INTO risk_policies (id, version, is_active, created_at, payload) "
                    "VALUES ('pol_risk-policy-1.0.0', 'risk-policy-1.0.0', true, :now, :payload) "
                    "ON CONFLICT (version) DO UPDATE SET is_active = true"
                ),
                {"now": now, "payload": json.dumps(default_policy_payload)},
            )

        # 5. Seed authoritative default paper Account and Snapshot if missing
        admin_user_id = bind.scalar(
            sa.text("SELECT id FROM users WHERE role = 'ADMIN' ORDER BY created_at ASC LIMIT 1")
        )
        if admin_user_id is not None:
            acc_exists = bind.scalar(
                sa.text("SELECT id FROM accounts WHERE name = 'default_paper_account' LIMIT 1")
            )
            if not acc_exists:
                bind.execute(
                    sa.text(
                        "INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, base_currency, is_active, created_at, updated_at) "
                        "VALUES ('a0000000-0000-0000-0000-000000000001', :user_id, 'default_paper_account', 'PAPER', 10000.00, 'USD', true, :now, :now) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {"user_id": admin_user_id, "now": now},
                )

            snap_exists = bind.scalar(
                sa.text("SELECT id FROM account_snapshots WHERE account_id = 'default_paper_account' LIMIT 1")
            )
            if not snap_exists:
                snap_payload = {
                    "id": "snap_default_paper_account_init",
                    "account_id": "default_paper_account",
                    "balance": "10000.00",
                    "equity": "10000.00",
                    "free_margin": "10000.00",
                    "daily_realized_pnl": "0.00",
                    "weekly_realized_pnl": "0.00",
                    "peak_equity": "10000.00",
                    "open_risk_pct": "0.0000",
                    "reserved_risk_pct": "0.0000",
                    "consecutive_losses": 0,
                    "trading_mode": "PAPER",
                    "source": "CONFIGURED_PAPER",
                    "as_of": now.isoformat(),
                }
                bind.execute(
                    sa.text(
                        "INSERT INTO account_snapshots (id, account_id, balance, equity, free_margin, daily_realized_pnl, "
                        "weekly_realized_pnl, peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, "
                        "trading_mode, source, as_of, payload) "
                        "VALUES ('snap_default_paper_account_init', 'default_paper_account', 10000.00, 10000.00, 10000.00, "
                        "0.00, 0.00, 10000.00, 0.0000, 0.0000, 0, 'PAPER', 'CONFIGURED_PAPER', :now, :payload) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {"now": now, "payload": json.dumps(snap_payload)},
                )

        # 6. Seed authoritative MT5 broker symbol spec if table is empty
        spec_exists = bind.scalar(sa.text("SELECT id FROM symbol_specifications WHERE symbol = 'XAUUSD' LIMIT 1"))
        if not spec_exists:
            spec_payload = {
                "id": "sym_xauusd_mt5_demo_iux_seed",
                "symbol": "XAUUSD",
                "source": "mt5_demo_iux",
                "tick_size": "0.01",
                "tick_value": "1.00",
                "contract_size": "100.00",
                "volume_min": "0.01",
                "volume_max": "20.00",
                "volume_step": "0.01",
                "digits": 2,
                "observed_at": now.isoformat(),
            }
            bind.execute(
                sa.text(
                    "INSERT INTO symbol_specifications (id, symbol, source, tick_size, tick_value, contract_size, "
                    "volume_min, volume_max, volume_step, digits, observed_at, payload) "
                    "VALUES ('sym_xauusd_mt5_demo_iux_seed', 'XAUUSD', 'mt5_demo_iux', 0.01, 1.00, 100.00, "
                    "0.01, 20.00, 0.01, 2, :now, :payload) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"now": now, "payload": json.dumps(spec_payload)},
            )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index("uq_risk_policy_single_active", table_name="risk_policies")

    if not context.is_offline_mode():
        op.execute(sa.text("DELETE FROM account_snapshots WHERE id = 'snap_default_paper_account_init'"))
        op.execute(sa.text("DELETE FROM accounts WHERE id = 'a0000000-0000-0000-0000-000000000001'"))
        op.execute(sa.text("DELETE FROM symbol_specifications WHERE id = 'sym_xauusd_mt5_demo_iux_seed'"))
        op.execute(sa.text("DELETE FROM risk_policies WHERE id = 'pol_risk-policy-1.0.0'"))
