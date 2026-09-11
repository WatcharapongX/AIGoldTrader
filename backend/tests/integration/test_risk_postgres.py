"""Phase 5 migration preservation and mandatory PostgreSQL concurrency gate."""

import asyncio
import datetime as dt
from decimal import Decimal

import pytest
from psycopg import sql
from sqlalchemy import text
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.services.risk.domain import (
    AccountSnapshot,
    RiskPolicy,
)
from app.services.risk.portfolio import portfolio_manager

pytestmark = pytest.mark.integration


def test_risk_migration_idempotence_and_preservation(isolated_postgres):  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))

    _alembic("upgrade", "head")
    _alembic("check")

    # Verify tables created
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (schema,)
        ).fetchall()
    }
    assert {
        "risk_policies",
        "symbol_specifications",
        "account_snapshots",
        "risk_decisions",
        "risk_reservations",
        "kill_switch_records",
    }.issubset(tables)

    # Insert a dummy risk decision
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload
        ) VALUES (
            'dec_test_pg_001', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            'snap_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}'
        )
        """
    )

    # Downgrade must fail/be blocked because records exist
    _alembic("downgrade", "0006_strategy", success=False)
    assert conn.execute("SELECT count(*) FROM risk_decisions").fetchone()[0] == 1


def test_mandatory_postgresql_concurrency_oversubscription_gate(isolated_postgres):  # noqa: F811
    """MANDATORY GATE:

    Simultaneously execute 5 risk reservations (each requesting 1.0% risk) on an account
    with max_account_risk_pct = 3.0%.
    Assert:
    - Aggregate approved reserved risk NEVER exceeds 3.0%!
    - Concurrency row locks prevent race condition oversubscription.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    now = dt.datetime.now(dt.UTC)
    policy = RiskPolicy(
        max_risk_per_trade_pct=Decimal("1.0"),
        min_risk_per_trade_pct=Decimal("0.1"),
        max_account_risk_pct=Decimal("3.0"),
        max_symbol_risk_pct=Decimal("3.0"),
        max_directional_risk_pct=Decimal("3.0"),
        max_concurrent_trades=10,
    )
    account = AccountSnapshot(
        id="snap_conc_001",
        account_id="acc_conc_001",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0000"),
        reserved_risk_pct=Decimal("0.0000"),
        as_of=now,
    )

    # Pre-insert risk_decisions rows to satisfy foreign key constraints for concurrent reservations
    for i in range(5):
        conn.execute(
            """
            INSERT INTO risk_decisions (
                id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
                decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
                approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
                stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload
            ) VALUES (
                %s, 'cand_conc', 'plan_conc', 'STRAT01', %s, 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                'snap_conc_001', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}'
            )
            """,
            (f"dec_conc_{i}", f"profile_{i}"),
        )

    async def run_concurrent_requests():
        factory = get_session_factory()
        results = []

        async def worker(worker_id: int):
            # Each worker uses an independent session to simulate independent concurrent requests
            async with factory() as session:
                # Set search_path for this connection
                await session.execute(text(f'SET search_path TO "{schema}"'))
                check = await portfolio_manager.check_budget_and_reserve(
                    session=session,
                    account=account,
                    policy=policy,
                    symbol="XAUUSD",
                    direction="LONG",
                    requested_risk_pct=Decimal("1.0"),
                    profile_id=f"profile_{worker_id}",
                    decision_id=f"dec_conc_{worker_id}",
                    position_size=Decimal("0.14"),
                    now=now,
                )
                if check.allowed:
                    await session.commit()
                results.append(check)

        # Launch 5 concurrent workers simultaneously
        await asyncio.gather(*(worker(i) for i in range(5)))
        return results

    try:
        results = asyncio.run(run_concurrent_requests(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine())

    allowed_results = [r for r in results if r.allowed]
    blocked_results = [r for r in results if not r.allowed]

    # Total approved risk across all concurrent workers
    total_approved_risk = sum((r.approved_risk_pct for r in allowed_results), Decimal("0"))

    # ASSERTIONS:
    # 1. Total approved risk MUST NEVER exceed max_account_risk_pct (3.0%)
    assert total_approved_risk <= Decimal("3.0000"), f"Race condition oversubscribed: {total_approved_risk}%"
    # 2. Exactly 3 allowed (3 x 1.0% = 3.0%), 2 blocked
    assert len(allowed_results) == 3, f"Expected 3 allowed, got {len(allowed_results)}"
    assert len(blocked_results) == 2, f"Expected 2 blocked, got {len(blocked_results)}"
    # 3. Database records match
    db_count = conn.execute("SELECT count(*) FROM risk_reservations WHERE status = 'ACTIVE'").fetchone()[0]
    assert db_count == 3
    db_sum = conn.execute("SELECT sum(risk_pct) FROM risk_reservations WHERE status = 'ACTIVE'").fetchone()[0]
    assert Decimal(str(db_sum)) == Decimal("3.0000")
