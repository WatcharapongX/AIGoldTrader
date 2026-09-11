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
from app.services.market_data.domain import Quote
from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as build_news_context
from app.services.risk.domain import (
    AccountSnapshot,
    RiskPolicy,
    default_gold_spec,
)
from app.services.risk.engine import risk_engine
from app.services.risk.portfolio import portfolio_manager
from app.services.risk.repository import persist_risk_decision
from app.services.strategy.domain import (
    Evidence,
    SetupCandidate,
    Target,
    TradePlanSuggestion,
)

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


def test_duplicate_concurrency_idempotency_gate(isolated_postgres):  # noqa: F811
    """MANDATORY GATE (SOL-P5-P1-002, 004, SOL-P5-NEW-P1-015):
    10 concurrent duplicate workers evaluate the exact same candidate/profile.
    Assert:
    - 0 unhandled IntegrityErrors / 500s.
    - Exactly 1 RiskDecision persisted for that fingerprint.
    - Exactly 1 RiskReservation persisted.
    - Budget consumed once (1.0%, not 10.0%).
    - All workers receive the identical canonical decision.
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
        id="snap_dup_conc_001",
        account_id="acc_dup_conc_001",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0000"),
        reserved_risk_pct=Decimal("0.0000"),
        as_of=now,
    )
    spec = default_gold_spec(source="simulated", observed_at=now)
    quote = Quote(
        symbol="XAUUSD",
        timestamp=now,
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        volume=Decimal("100"),
        source="simulated",
        mode="SIMULATED",
        spread=Decimal("0.30"),
        status="CONNECTED",
    )
    plan = TradePlanSuggestion(
        id="plan_dup_conc",
        candidate_id="cand_dup_conc",
        symbol="XAUUSD",
        direction="LONG",
        entry_type="LIMIT_ZONE",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        entry_source_id="h1_fvg",
        stop_loss=Decimal("2495.00"),
        stop_source_id="h1_swing_low",
        invalidation_th="หลุดแนวรับ 2495.00",
        targets=(
            Target(name="TP1", price=Decimal("2510.00"), source_id="h4_high", rr=Decimal("1.5")),
            Target(name="TP2", price=Decimal("2520.00"), source_id="d1_high", rr=Decimal("3.0")),
        ),
        score=85,
        evidence=(Evidence(code="EV1", description_th="SMC Confirmation"),),
        warnings_th=(),
        news_state="CALM",
        status="SUGGESTION_ONLY",
        as_of=now,
        context_id="ctx_001",
        expires_at=now + dt.timedelta(hours=2),
    )
    candidate = SetupCandidate(
        id="cand_dup_conc",
        profile_id="day_trader",
        strategy_id="STRAT01",
        strategy_version="1.0.0",
        symbol="XAUUSD",
        direction="LONG",
        status="READY",
        score=85,
        detected_at=now - dt.timedelta(minutes=10),
        confirmed_at=now,
        expires_at=now + dt.timedelta(hours=2),
        context_id="ctx_001",
        upstream_ids=("ctx_001",),
        evidence=(Evidence(code="EV1", description_th="SMC Confirmation"),),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="หลุดแนวรับ 2495.00",
        plan=plan,
    )
    news_ctx = build_news_context(
        events=[],
        as_of=now,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )

    async def run_10_concurrent_duplicates():
        factory = get_session_factory()
        decisions = []

        async def worker():
            async with factory() as session:
                await session.execute(text(f'SET search_path TO "{schema}"'))
                dec = await risk_engine.evaluate_candidate(
                    session=session,
                    candidate=candidate,
                    plan=plan,
                    account=account,
                    policy=policy,
                    spec=spec,
                    quote=quote,
                    news_context=news_ctx,
                    as_of=now,
                )
                if dec.decision != "BLOCKED":
                    await persist_risk_decision(session, dec)
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
                decisions.append(dec)

        await asyncio.gather(*(worker() for _ in range(10)))
        return decisions

    try:
        decisions = asyncio.run(run_10_concurrent_duplicates(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine())

    assert len(decisions) == 10
    decision_ids = {d.id for d in decisions}
    assert len(decision_ids) == 1, f"Expected exactly 1 distinct decision ID, got {decision_ids}"
    approved_pcts = {d.approved_risk_pct for d in decisions}
    assert approved_pcts == {Decimal("1.0000")}

    db_dec_count = conn.execute("SELECT count(*) FROM risk_decisions WHERE candidate_id = 'cand_dup_conc'").fetchone()[0]
    assert db_dec_count == 1, f"Expected 1 decision in DB, got {db_dec_count}"

    db_res_count = conn.execute("SELECT count(*) FROM risk_reservations WHERE status = 'ACTIVE'").fetchone()[0]
    assert db_res_count == 1, f"Expected 1 active reservation, got {db_res_count}"

    db_sum = conn.execute("SELECT sum(risk_pct) FROM risk_reservations WHERE status = 'ACTIVE'").fetchone()[0]
    assert Decimal(str(db_sum)) == Decimal("1.0000")


def test_migration_0007_to_0009_matrix(isolated_postgres):  # noqa: F811
    """MANDATORY MIGRATION MATRIX (SOL-P5-NEW-P1-016, 017, 018):
    1. Migrate up to 0007.
    2. Insert an ACTIVE kill switch.
    3. Insert legacy decisions.
    4. Upgrade to head (0008 + 0009).
    5. Assert:
       - ACTIVE kill switch remains the latest and active record (never superseded by inactive bootstrap).
       - Legacy decisions are preserved and upgraded to unique fingerprints.
       - Alembic check passes.
       - Downgrade refused when audit tables are populated.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))

    # Step 1: Migrate up to 0007
    _alembic("upgrade", "0007_risk_engine")

    # Step 2: Insert historical ACTIVE kill switch in 0007
    conn.execute(
        """
        INSERT INTO kill_switch_records (
            id, state, trigger_type, reason_th, activated_at, activated_by, policy_version, payload
        ) VALUES (
            'ks_hist_active_01', 'ACTIVE', 'MANUAL', 'ปิดระบบฉุกเฉินก่อนไมเกรต',
            NOW(), 'operator_admin', 'risk-policy-1.0.0', '{}'
        )
        """
    )

    # Step 3: Insert legacy decisions in 0007
    for i in range(2):
        conn.execute(
            f"""
            INSERT INTO risk_decisions (
                id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
                decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
                approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
                stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload
            ) VALUES (
                'dec_dup_legacy_{i}', 'cand_legacy_{i}', 'plan_legacy', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                'snap_legacy_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{{}}'
            )
            """
        )

    # Step 4: Upgrade through head (0008 + 0009)
    _alembic("upgrade", "head")
    _alembic("check")

    # Step 5: Verify ACTIVE kill switch is still the latest and active state
    latest_ks = conn.execute(
        "SELECT id, state, activated_at FROM kill_switch_records ORDER BY activated_at DESC, id DESC LIMIT 1"
    ).fetchone()
    assert latest_ks[1] == "ACTIVE", f"Expected ACTIVE kill switch after migration, got {latest_ks[1]}"

    # Step 6: Verify legacy decisions are preserved and have unique fingerprints
    legacy_count = conn.execute(
        "SELECT count(*) FROM risk_decisions WHERE id LIKE 'dec_dup_legacy_%'"
    ).fetchone()[0]
    assert legacy_count == 2, f"Expected 2 preserved decisions, got {legacy_count}"
    fps = conn.execute(
        "SELECT dependency_fingerprint FROM risk_decisions WHERE id LIKE 'dec_dup_legacy_%'"
    ).fetchall()
    assert all(r[0].startswith("legacy_") for r in fps)
    assert len({r[0] for r in fps}) == 2

    # Step 7: Downgrade attempt must be refused because audit records exist
    _alembic("downgrade", "0007_risk_engine", success=False)
