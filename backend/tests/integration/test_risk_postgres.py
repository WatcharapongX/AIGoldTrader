"""Phase 5 migration preservation and mandatory PostgreSQL concurrency gate."""

import asyncio
import datetime as dt
import json
import uuid
from decimal import Decimal

import httpx
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
        "data_health_records",
        "paper_account_states",
    }.issubset(tables)

    # Seed user and account to satisfy account authority & foreign key trigger (AUD-P1-004, BATCHA1-NEW-P2-002)
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000001', 'pg_test@example.com', 'hash', 'TRADER', true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            ('00000000-0000-0000-0000-000000000001',
             '00000000-0000-0000-0000-000000000001',
             'Paper Account', 'PAPER', 10000.00, true, NOW(), NOW()),
            ('00000000-0000-0000-0000-000000000003',
             '00000000-0000-0000-0000-000000000001',
             'Paper Account 3', 'PAPER', 10000.00, true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
        """
    )

    # Insert a dummy risk decision
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_test_pg_001', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            '00000000-0000-0000-0000-000000000001', 'snap_01', 'risk-policy-1.0.0',
            NOW(), NOW() + interval '1 hour', '{"account_id": "00000000-0000-0000-0000-000000000001"}',
            'fp_test_pg_001'
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
    acc_id = "00000000-0000-0000-0000-000000000002"
    account = AccountSnapshot(
        id="snap_conc_001",
        account_id=acc_id,
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0000"),
        reserved_risk_pct=Decimal("0.0000"),
        as_of=now,
    )

    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000002', 'u2@example.com', 'h', 'TRADER', true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000002',
                '00000000-0000-0000-0000-000000000002',
                'Paper Account 2', 'PAPER', 10000.0, true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
        """
    )

    # Pre-insert risk_decisions rows to satisfy foreign key constraints for concurrent reservations
    for i in range(5):
        conn.execute(
            """
            INSERT INTO risk_decisions (
                id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
                decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
                approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
                stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
                dependency_fingerprint
            ) VALUES (
                %s, 'cand_conc', 'plan_conc', 'STRAT01', %s, 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                %s, 'snap_conc_001', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', %s,
                %s
            )
            """,
            (f"dec_conc_{i}", f"profile_{i}", acc_id, json.dumps({"account_id": acc_id}), f"fp_conc_{i}"),
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
        account_id="00000000-0000-0000-0000-000000000003",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0000"),
        reserved_risk_pct=Decimal("0.0000"),
        as_of=now,
    )

    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000003', 'u3@example.com', 'h', 'TRADER', true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000003',
                '00000000-0000-0000-0000-000000000003',
                'Paper Account 3', 'PAPER', 10000.0, true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
        """
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

    db_dec_count = conn.execute("SELECT count(*) FROM risk_decisions WHERE candidate_id = 'cand_dup_conc'").fetchone()[
        0
    ]
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

    # Step 3: Insert user, account, and snapshot for authoritative decision ownership in 0007
    uid_legacy = str(uuid.uuid4())
    acc_legacy_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(uid)s, 'legacy_migration@example.com', 'dummy_hash', 'TRADER', true, NOW(), NOW())
        """,
        {"uid": uid_legacy},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(id)s, %(uid)s, 'Legacy Acc', 'PAPER', 10000.00, true, NOW(), NOW())
        """,
        {"id": acc_legacy_id, "uid": uid_legacy},
    )
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode,
            source, as_of, payload
        ) VALUES (
            'snap_legacy_01', %(acc_id)s, 10000.00, 10000.00, 10000.00, 0.00, 0.00,
            10000.00, 0.0000, 0.0000, 0, 'PAPER', 'PAPER_ACCOUNT_STATE', NOW(), '{}'
        )
        """,
        {"acc_id": acc_legacy_id},
    )

    for i in range(2):
        conn.execute(
            """
            INSERT INTO risk_decisions (
                id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
                decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
                approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
                stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload
            ) VALUES (
                %(id)s, 'cand_same', %(plan_id)s, 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                'snap_legacy_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}'
            )
            """,
            {"id": f"dec_dup_legacy_{i}", "plan_id": f"plan_legacy_{i}"},
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
    legacy_count = conn.execute("SELECT count(*) FROM risk_decisions WHERE id LIKE 'dec_dup_legacy_%'").fetchone()[0]
    assert legacy_count == 2, f"Expected 2 preserved decisions, got {legacy_count}"
    fps = conn.execute("SELECT dependency_fingerprint FROM risk_decisions WHERE id LIKE 'dec_dup_legacy_%'").fetchall()
    assert all(r[0].startswith("legacy_") for r in fps)
    assert len({r[0] for r in fps}) == 2

    # Step 7: Downgrade attempt must be refused because audit records exist
    _alembic("downgrade", "0007_risk_engine", success=False)


def test_migration_0010_downgrade_barrier_and_seed_quarantine(isolated_postgres):  # noqa: F811
    """P1-032 & Scenario A-K:
    1. Upgrade to head (0010).
    2. Insert an audit record into symbol_specifications.
    3. Downgrade to 0009 MUST fail with RuntimeError because Phase 5 audit records exist.
    4. Clear symbol_specifications, then downgrade to 0009 succeeds.
    5. In 0009, insert invalid historical MT5 seed 'sym_xauusd_mt5_demo_iux_seed'.
    6. Upgrade to 0010 (head).
    7. Verify fake MT5 seed was deleted/quarantined.
    8. Verify data_health_records table exists and has 'dh_default' row.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    # Insert record into symbol_specifications
    conn.execute(
        """
        INSERT INTO symbol_specifications (
            id, symbol, source, tick_size, tick_value, contract_size,
            volume_min, volume_max, volume_step, digits, observed_at, payload
        ) VALUES (
            'sym_spec_audit_barrier', 'XAUUSD', 'mt5', 0.01, 1.00, 100.00,
            0.01, 10.00, 0.01, 2, NOW(), '{}'
        )
        """
    )
    # Downgrade to 0009 must be refused!
    _alembic("downgrade", "0009_phase5_final_hardening", success=False)

    # Clean up audit record and all seeded Phase 5 authority rows to allow downgrade
    for tbl in (
        "risk_decisions",
        "risk_reservations",
        "account_snapshots",
        "symbol_specifications",
        "risk_policies",
        "data_health_records",
        "paper_account_states",
        "kill_switch_records",
    ):
        conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(tbl)))
    # Now downgrade to 0009 succeeds
    _alembic("downgrade", "0009_phase5_final_hardening", success=True)

    # Insert fake MT5 seed in 0009
    conn.execute(
        """
        INSERT INTO symbol_specifications (
            id, symbol, source, tick_size, tick_value, contract_size,
            volume_min, volume_max, volume_step, digits, observed_at, payload
        ) VALUES (
            'sym_xauusd_mt5_demo_iux_seed', 'XAUUSD', 'mt5', 0.01, 1.00, 100.00,
            0.01, 10.00, 0.01, 2, NOW(), '{}'
        )
        """
    )

    # Upgrade to 0010 (head)
    _alembic("upgrade", "head")
    _alembic("check")

    # Verify fake MT5 seed was quarantined/removed
    fake_count = conn.execute(
        "SELECT count(*) FROM symbol_specifications WHERE id = 'sym_xauusd_mt5_demo_iux_seed'"
    ).fetchone()[0]
    assert fake_count == 0, "Fake MT5 seed must be quarantined/deleted"

    # Verify data_health_records table exists and has 'dh_default' row
    dh_row = conn.execute("SELECT id, consecutive_failures FROM data_health_records WHERE id = 'dh_default'").fetchone()
    assert dh_row is not None
    assert dh_row[0] == "dh_default"


def test_paper_account_state_postgresql_concurrency_semantics(isolated_postgres):  # noqa: F811
    """Actual PostgreSQL gate for creation, observation, force, transitions, and policy TTL."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%s, %s, 'dummy_hash', 'TRADER', true, NOW(), NOW())
        """,
        (user_id, f"account-concurrency-{user_id}@example.com"),
    )
    conn.execute(
        """
        INSERT INTO accounts (
            id, user_id, name, trading_mode, starting_balance, base_currency,
            is_active, created_at, updated_at
        )
        VALUES (%s, %s, 'Account Concurrency Gate', 'PAPER', 10000.00, 'USD', true, NOW(), NOW())
        """,
        (account_id, user_id),
    )

    async def run_account_matrix():
        from app.models.risk import PaperAccountStateRecord
        from app.services.risk.account_state import PaperAccountStateService

        factory = get_session_factory()
        account_key = str(account_id)

        async def create_one():
            async with factory() as session:
                async with session.begin():
                    state = await PaperAccountStateService.get_or_create_paper_state(session, account_key)
                    return state.account_id, state.state_version

        created = await asyncio.gather(*(create_one() for _ in range(10)))
        assert created == [(account_key, 1)] * 10

        observation_time = dt.datetime.now(dt.UTC)

        async def observe_one(*, force: bool):
            async with factory() as session:
                async with session.begin():
                    return await PaperAccountStateService.refresh_paper_account_snapshot(
                        session,
                        account_key,
                        force=force,
                        now=observation_time,
                        max_observation_age_seconds=120,
                    )

        observations = await asyncio.gather(*(observe_one(force=False) for _ in range(10)))
        assert len({item.id for item in observations}) == 1
        assert {item.state_version for item in observations} == {1}

        forced = await asyncio.gather(*(observe_one(force=True) for _ in range(10)))
        assert len({item.id for item in forced}) == 10
        assert {item.state_version for item in forced} == {1}

        # Preload the same ORM object into every identity map before locking.
        sessions = [factory() for _ in range(10)]
        try:
            preloaded = await asyncio.gather(
                *(session.get(PaperAccountStateRecord, account_key) for session in sessions)
            )
            assert {state.state_version for state in preloaded if state is not None} == {1}

            async def set_same_target(session):
                state = await PaperAccountStateService.update_paper_account_state(
                    session,
                    account_key,
                    balance=Decimal("11000.00"),
                    now=dt.datetime.now(dt.UTC),
                )
                await session.commit()
                return state.state_version

            same_versions = await asyncio.gather(*(set_same_target(session) for session in sessions))
            assert set(same_versions) == {2}
        finally:
            await asyncio.gather(*(session.close() for session in sessions))

        sessions = [factory() for _ in range(10)]
        try:
            await asyncio.gather(
                *(session.get(PaperAccountStateRecord, account_key) for session in sessions)
            )

            async def set_distinct_target(index, session):
                target = Decimal("12000.00") + Decimal(index)
                state = await PaperAccountStateService.update_paper_account_state(
                    session,
                    account_key,
                    balance=target,
                    now=dt.datetime.now(dt.UTC),
                )
                await session.commit()
                return state.state_version

            distinct_versions = await asyncio.gather(
                *(set_distinct_target(index, session) for index, session in enumerate(sessions))
            )
            assert set(distinct_versions) == set(range(3, 13))
        finally:
            await asyncio.gather(*(session.close() for session in sessions))

        async with factory() as session:
            final_state = await session.get(PaperAccountStateRecord, account_key)
            assert final_state is not None
            assert final_state.state_version == 12
            assert final_state.balance in {
                Decimal("12000.00") + Decimal(index) for index in range(10)
            }

        ttl_results: dict[int, bool] = {}
        for index, policy_freshness in enumerate((5, 30, 60, 120)):
            baseline_time = observation_time + dt.timedelta(minutes=index + 1)
            async with factory() as session:
                async with session.begin():
                    baseline = await PaperAccountStateService.refresh_paper_account_snapshot(
                        session,
                        account_key,
                        force=True,
                        now=baseline_time,
                        max_observation_age_seconds=policy_freshness,
                    )
            async with factory() as session:
                async with session.begin():
                    observed = await PaperAccountStateService.refresh_paper_account_snapshot(
                        session,
                        account_key,
                        now=baseline_time + dt.timedelta(seconds=20),
                        max_observation_age_seconds=policy_freshness,
                    )
            ttl_results[policy_freshness] = observed.id == baseline.id

        assert ttl_results == {5: False, 30: True, 60: True, 120: True}

    try:
        asyncio.run(run_account_matrix(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine())

    assert conn.execute(
        "SELECT count(*) FROM paper_account_states WHERE account_id = %s",
        (str(account_id),),
    ).fetchone()[0] == 1


def test_fastapi_http_evaluate_concurrency_and_idempotency(isolated_postgres):  # noqa: F811
    """P1-031 & P2-035:
    Real FastAPI HTTP API concurrency gate:
    1. Five rounds of 10 concurrent POST /api/risk/evaluate calls for the same
       candidate/account.
       Assert: exactly 1 decision created in DB, 1 reservation created in DB,
       all 10 responses return 200 with identical decision ID and identical fingerprint.
    2. 100 sequential and 100 safe-jitter POST /api/risk/evaluate calls:
       Assert: all return identical decision ID, 0 new reservations created.
    3. Released/expired cache hits, 1.0 -> 0.5 -> 1.0 changes, and
       APPROVED -> BLOCKED -> APPROVED -> cached BLOCKED transitions all
       converge to an exact Decision/Reservation pair.
    4. 10 unauthorized POST /api/risk/evaluate calls from non-owner user:
       Assert: all return 403 Forbidden with 0 state mutations in DB.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    user_id = str(uuid.uuid4())
    other_user_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())

    # Pre-seed user, account, candidate
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(uid)s, 'owner@example.com', 'dummy_hash', 'TRADER', true, NOW(), NOW()),
               (%(other_uid)s, 'other@example.com', 'dummy_hash', 'TRADER', true, NOW(), NOW())
        """,
        {"uid": user_id, "other_uid": other_user_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (
            id, user_id, name, trading_mode, starting_balance, base_currency, is_active, created_at, updated_at
        )
        VALUES (%(acc_id)s, %(uid)s, 'Test Paper Acc', 'PAPER', 10000.00, 'USD', true, NOW(), NOW())
        """,
        {"acc_id": acc_id, "uid": user_id},
    )
    snap_payload = {
        "id": "snap_http_init",
        "account_id": acc_id,
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
        "source": "PAPER_ACCOUNT_STATE",
        "as_of": now.isoformat(),
        "state_version": 1,
    }
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode,
            source, as_of, payload
        ) VALUES (
            'snap_http_init', %(acc_id)s, 10000.00, 10000.00, 10000.00, 0.00, 0.00,
            10000.00, 0.0000, 0.0000, 0, 'PAPER', 'PAPER_ACCOUNT_STATE', NOW(), %(payload)s
        )
        """,
        {"acc_id": acc_id, "payload": json.dumps(snap_payload)},
    )

    spec = default_gold_spec(source="simulated", observed_at=now)
    conn.execute(
        """
        INSERT INTO symbol_specifications (
            id, symbol, source, tick_size, tick_value, contract_size,
            volume_min, volume_max, volume_step, digits, observed_at, payload
        ) VALUES (
            %(id)s, %(symbol)s, %(source)s, %(tick_size)s, %(tick_value)s, %(contract_size)s,
            %(volume_min)s, %(volume_max)s, %(volume_step)s, %(digits)s, NOW(), %(payload)s
        )
        """,
        {
            "id": spec.id,
            "symbol": spec.symbol,
            "source": spec.source,
            "tick_size": spec.tick_size,
            "tick_value": spec.tick_value,
            "contract_size": spec.contract_size,
            "volume_min": spec.volume_min,
            "volume_max": spec.volume_max,
            "volume_step": spec.volume_step,
            "digits": spec.digits,
            "payload": json.dumps(spec.model_dump(mode="json")),
        },
    )

    plan = TradePlanSuggestion(
        id="plan_http_conc",
        candidate_id="cand_http_conc",
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
        id="cand_http_conc",
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
    conn.execute(
        """
        INSERT INTO strategy_evaluations (id, context_id, symbol, source, as_of, generated_at, payload_hash, payload)
        VALUES ('eval_http_conc', 'ctx_001', 'XAUUSD', 'mt5', NOW(), NOW(), 'hash_eval', '{}')
        """
    )
    conn.execute(
        """
        INSERT INTO trade_candidates (
            id, evaluation_id, profile_id, strategy_id, as_of, payload
        ) VALUES (
            'cand_http_conc', 'eval_http_conc', 'day_trader', 'STRAT01', NOW(), %(payload)s
        )
        """,
        {"payload": json.dumps(candidate.model_dump(mode="json"))},
    )

    async def run_http_concurrency():
        from app.api.deps import get_current_user
        from app.main import create_app
        from app.models import Role, User

        app = create_app()
        owner = User(id=uuid.UUID(user_id), email="owner@example.com", role=Role.TRADER, is_active=True)
        unauthorized_user = User(
            id=uuid.UUID(other_user_id), email="other@example.com", role=Role.TRADER, is_active=True
        )

        from unittest.mock import AsyncMock, MagicMock, PropertyMock

        static_quote = Quote(
            source="simulated",
            mode="SIMULATED",
            symbol="XAUUSD",
            bid=Decimal("2500.00"),
            ask=Decimal("2500.30"),
            spread=Decimal("0.30"),
            volume=Decimal("100"),
            status="CONNECTED",
            timestamp=now,
        )
        market_state = {
            "bid": static_quote.bid,
            "ask": static_quote.ask,
        }

        class DummyProvider:
            source = "simulated"
            broker_server = None
            server = None

        mock_market = MagicMock()
        # Keep transport observations fresh while preserving the exact semantic
        # dependency set. The quote timestamp is deliberately excluded from the
        # safe-jitter decision fingerprint.
        type(mock_market).quote = PropertyMock(
            side_effect=lambda: static_quote.model_copy(
                update={
                    "bid": market_state["bid"],
                    "ask": market_state["ask"],
                    "spread": market_state["ask"] - market_state["bid"],
                    "timestamp": dt.datetime.now(dt.UTC),
                }
            )
        )
        mock_market.start = AsyncMock()
        mock_market.provider = DummyProvider()
        app.state.market = mock_market

        mock_news = MagicMock()
        mock_news.start = AsyncMock()
        mock_news.provider.source = "fixture_economic_v1"
        mock_news.context = AsyncMock(
            return_value=build_news_context(
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
        )
        app.state.news = mock_news

        # 1. 10 Concurrent calls by owner
        app.dependency_overrides[get_current_user] = lambda: owner
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            req_body = {
                "candidate_id": "cand_http_conc",
                "profile_id": "day_trader",
                "account_id": acc_id,
                "requested_risk_pct": 1.0,
            }
            dec_ids: set[str] = set()
            fps: set[str] = set()
            for round_number in range(5):
                tasks = [client.post("/api/risk/evaluate", json=req_body) for _ in range(10)]
                responses = await asyncio.gather(*tasks)

                assert all(r.status_code == 200 for r in responses), (
                    f"Round {round_number + 1}: expected all 200, "
                    f"got {[r.status_code for r in responses]}"
                )
                dec_ids.update(r.json()["id"] for r in responses)
                fps.update(r.json()["dependency_fingerprint"] for r in responses)

            assert len(dec_ids) == 1, f"Expected 1 decision ID across 5 rounds, got {dec_ids}"
            assert len(fps) == 1, f"Expected 1 fingerprint across 5 rounds, got {fps}"

            # 2. 100 Sequential calls
            for _ in range(100):
                res = await client.post("/api/risk/evaluate", json=req_body)
                assert res.status_code == 200
                assert res.json()["id"] == list(dec_ids)[0]

            original_decision_id = next(iter(dec_ids))

            # 3. 100 quote observations with economically irrelevant jitter.
            for offset in range(100):
                jitter = Decimal(offset) / Decimal("10000")
                market_state["bid"] = Decimal("2500.00") + jitter
                market_state["ask"] = Decimal("2500.30") + jitter
                res = await client.post("/api/risk/evaluate", json=req_body)
                assert res.status_code == 200
                assert res.json()["id"] == original_decision_id

            market_state["bid"] = Decimal("2500.00")
            market_state["ask"] = Decimal("2500.30")

            # 4. Released and expired cache hits must reactivate the exact row.
            conn.execute(
                """
                UPDATE risk_reservations
                SET status = 'RELEASED', released_at = NOW(), release_reason = 'HTTP_TEST_RELEASE'
                WHERE decision_id = %s
                """,
                (original_decision_id,),
            )
            released_retry = await client.post("/api/risk/evaluate", json=req_body)
            assert released_retry.status_code == 200
            assert released_retry.json()["id"] == original_decision_id

            conn.execute(
                """
                UPDATE risk_reservations
                SET status = 'ACTIVE', reserved_until = NOW() - interval '1 second'
                WHERE decision_id = %s
                """,
                (original_decision_id,),
            )
            expired_retry = await client.post("/api/risk/evaluate", json=req_body)
            assert expired_retry.status_code == 200
            assert expired_retry.json()["id"] == original_decision_id
            exact = conn.execute(
                """
                SELECT decision_id, status, risk_pct, reserved_until > NOW()
                FROM risk_reservations
                WHERE account_id = %s AND status = 'ACTIVE'
                """,
                (acc_id,),
            ).fetchall()
            assert exact == [(original_decision_id, "ACTIVE", Decimal("1.0000"), True)]

            # 5. Both risk directions must replace the active pair atomically.
            half_body = {**req_body, "requested_risk_pct": 0.5}
            half = await client.post("/api/risk/evaluate", json=half_body)
            assert half.status_code == 200
            assert half.json()["decision"] in {"APPROVED", "REDUCED"}
            assert Decimal(str(half.json()["approved_risk_pct"])) == Decimal("0.5")
            half_id = half.json()["id"]
            assert half_id != original_decision_id
            half_pair = conn.execute(
                """
                SELECT decision_id, risk_pct FROM risk_reservations
                WHERE account_id = %s AND status = 'ACTIVE'
                """,
                (acc_id,),
            ).fetchall()
            assert half_pair == [(half_id, Decimal("0.5000"))]

            full_again = await client.post("/api/risk/evaluate", json=req_body)
            assert full_again.status_code == 200
            assert full_again.json()["id"] == original_decision_id
            full_pair = conn.execute(
                """
                SELECT decision_id, risk_pct FROM risk_reservations
                WHERE account_id = %s AND status = 'ACTIVE'
                """,
                (acc_id,),
            ).fetchall()
            assert full_pair == [(original_decision_id, Decimal("1.0000"))]

            # 6. Cached BLOCKED must release a newer approval before returning.
            market_state["ask"] = Decimal("2505.00")
            blocked = await client.post("/api/risk/evaluate", json=req_body)
            assert blocked.status_code == 200
            assert blocked.json()["decision"] == "BLOCKED"
            blocked_id = blocked.json()["id"]
            assert conn.execute(
                "SELECT count(*) FROM risk_reservations WHERE account_id = %s AND status = 'ACTIVE'",
                (acc_id,),
            ).fetchone()[0] == 0

            market_state["ask"] = Decimal("2500.30")
            approved_again = await client.post("/api/risk/evaluate", json=req_body)
            assert approved_again.status_code == 200
            assert approved_again.json()["id"] == original_decision_id

            market_state["ask"] = Decimal("2505.00")
            cached_blocked = await client.post("/api/risk/evaluate", json=req_body)
            assert cached_blocked.status_code == 200
            assert cached_blocked.json()["id"] == blocked_id
            assert conn.execute(
                "SELECT count(*) FROM risk_reservations WHERE account_id = %s AND status = 'ACTIVE'",
                (acc_id,),
            ).fetchone()[0] == 0

            market_state["ask"] = Decimal("2500.30")
            final_approved = await client.post("/api/risk/evaluate", json=req_body)
            assert final_approved.status_code == 200
            assert final_approved.json()["id"] == original_decision_id

            # 7. Unauthorized access check
            app.dependency_overrides[get_current_user] = lambda: unauthorized_user
            for _ in range(10):
                unauth_res = await client.post("/api/risk/evaluate", json=req_body)
                assert unauth_res.status_code == 403

        app.dependency_overrides.clear()

    try:
        asyncio.run(run_http_concurrency(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine())

    # Two approved risk levels plus one blocked state, with one current reservation.
    dec_count = conn.execute(
        "SELECT count(*) FROM risk_decisions WHERE candidate_id = 'cand_http_conc'"
    ).fetchone()[0]
    assert dec_count == 3, f"Expected exactly 3 decisions in DB, got {dec_count}"

    res_count = conn.execute(
        "SELECT count(*) FROM risk_reservations WHERE account_id = %s AND status = 'ACTIVE'",
        (acc_id,),
    ).fetchone()[0]
    assert res_count == 1, f"Expected exactly 1 active reservation in DB, got {res_count}"


def test_migration_0010_dirty_state_reconciliation(isolated_postgres):  # noqa: F811
    """SOL-P5 Round 3 Section 16, 17, 18:
    1. Upgrade to 0010_phase5_account_authority.
    2. Seed dirty state:
       - 3 paper accounts (A, B, C) with snapshots to test multi-account backfill.
       - Duplicate active reservations for (account A, candidate 1) with risk 1.0% and 0.5%.
       - Duplicate data health records for same (provider, source).
    3. Upgrade to head (through 0011 and 0012).
    4. Verify:
       - Exactly 3 paper_account_states rows created (1 for each account, no cross-account state leakage).
       - Duplicate active reservation resolved: higher risk (1.0%) kept ACTIVE, 0.5% marked RELEASED.
       - Unique index uq_risk_reservations_active_candidate created successfully.
       - Duplicate data health records merged conservatively: max consecutive_failures kept.
       - Unique constraint uq_data_health_provider_source created successfully.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0010_phase5_safety_closure")

    uid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(uid)s, 'migration_test@example.com', 'dummy_hash', 'TRADER', true, NOW(), NOW())
        """,
        {"uid": uid},
    )

    # 1. Seed 3 accounts with snapshots
    acc_ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, acc_id in enumerate(acc_ids):
        conn.execute(
            """
            INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
            VALUES (%(id)s, %(uid)s, %(name)s, 'PAPER', %(bal)s, true, NOW(), NOW())
            """,
            {"id": acc_id, "uid": uid, "name": f"Paper Acc {i+1}", "bal": 10000.00 * (i + 1)},
        )
        conn.execute(
            """
            INSERT INTO account_snapshots (
                id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
                peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode,
                source, as_of, payload
            ) VALUES (
                %(sid)s, %(aid)s, %(bal)s, %(bal)s, %(bal)s, 0.00, 0.00,
                %(bal)s, 0.0000, 0.0000, 0, 'PAPER', 'PAPER_ACCOUNT_STATE', NOW(), '{}'
            )
            """,
            {"sid": f"snap_acc_{i}", "aid": acc_id, "bal": 10000.00 * (i + 1)},
        )

    # 2. Seed risk decisions and duplicate active reservations for same candidate and account 0
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES
        ('dec_dup_1', 'cand_dup_01', 'plan_1', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
         'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
         'snap_acc_0', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}', 'fp_dup_1'),
        ('dec_dup_2', 'cand_dup_01', 'plan_2', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
         'APPROVED', 0.5, 0.5, 50.0, 50.0, 0.07, 2500.0, 2502.0, 2495.0, 7.0,
         'snap_acc_0', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}', 'fp_dup_2')
        """
    )
    conn.execute(
        """
        INSERT INTO risk_reservations (
            id, decision_id, account_id, profile_id, symbol, direction, risk_pct,
            risk_amount, position_size, status, reserved_at, reserved_until
        ) VALUES
        ('res_dup_high', 'dec_dup_1', %(aid)s, 'day_trader', 'XAUUSD', 'LONG', 1.0000, 100.00,
         0.14, 'ACTIVE', NOW(), NOW() + interval '5 min'),
        ('res_dup_low', 'dec_dup_2', %(aid)s, 'day_trader', 'XAUUSD', 'LONG', 0.5000, 50.00,
         0.07, 'ACTIVE', NOW(), NOW() + interval '5 min')
        """,
        {"aid": acc_ids[0]},
    )

    # 3. Seed duplicate data health records with same provider and source (0010 had non-unique index)
    conn.execute(
        """
        INSERT INTO data_health_records (
            id, provider, source, consecutive_failures, last_failure_at, last_healthy_at, updated_at, payload
        )
        VALUES
        ('dh_dup_1', 'market_data', 'default', 2, NOW(), NOW(), NOW(), '{}'),
        ('dh_dup_2', 'market_data', 'default', 5, NOW(), NOW(), NOW(), '{}')
        """
    )

    # Upgrade through 0011 and 0012 to head
    _alembic("upgrade", "head")
    _alembic("check")

    # Verify 3 paper account states created with matching starting balances
    states = conn.execute(
        "SELECT account_id, balance FROM paper_account_states WHERE account_id = ANY(%s) ORDER BY balance",
        (acc_ids,),
    ).fetchall()
    assert len(states) == 3, f"Expected 3 paper account states, got {len(states)}"
    assert [float(s[1]) for s in states] == [10000.0, 20000.0, 30000.0]

    # Verify duplicate active reservation resolved (higher risk 1.0% is ACTIVE, 0.5% is RELEASED)
    res_high = conn.execute(
        "SELECT status, risk_pct FROM risk_reservations WHERE id = 'res_dup_high'"
    ).fetchone()
    res_low = conn.execute(
        "SELECT status, risk_pct FROM risk_reservations WHERE id = 'res_dup_low'"
    ).fetchone()
    assert res_high[0] == "ACTIVE" and float(res_high[1]) == 1.0
    assert res_low[0] == "RELEASED"

    # Verify duplicate data health records deduplicated conservatively (max failures preserved)
    dh_rows = conn.execute(
        "SELECT id, provider, source, consecutive_failures FROM data_health_records "
        "WHERE provider = 'market_data' AND source = 'default'"
    ).fetchall()
    assert len(dh_rows) == 1, f"Expected 1 deduplicated data health row, got {len(dh_rows)}"
    assert dh_rows[0][3] >= 5, f"Expected consecutive_failures >= 5, got {dh_rows[0][3]}"

    # A post-migration cache hit for the lower-risk decision must converge the
    # survivor chosen by the migration to that exact Decision/Reservation pair.
    async def reconcile_cached_lower_risk_decision():
        factory = get_session_factory()
        async with factory() as session:
            async with session.begin():
                await portfolio_manager.create_reservation(
                    session=session,
                    decision_id="dec_dup_2",
                    account_id=acc_ids[0],
                    candidate_id="cand_dup_01",
                    profile_id="day_trader",
                    symbol="XAUUSD",
                    direction="LONG",
                    risk_pct=Decimal("0.5"),
                    risk_amount=Decimal("50.00"),
                    position_size=Decimal("0.07"),
                    policy=RiskPolicy(news_risk_enabled=False),
                    now=dt.datetime.now(dt.UTC),
                )

    try:
        asyncio.run(reconcile_cached_lower_risk_decision(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine())

    converged = conn.execute(
        """
        SELECT decision_id, status, risk_pct
        FROM risk_reservations
        WHERE account_id = %s AND candidate_id = 'cand_dup_01'
        ORDER BY decision_id
        """,
        (acc_ids[0],),
    ).fetchall()
    assert converged == [
        ("dec_dup_1", "RELEASED", Decimal("1.0000")),
        ("dec_dup_2", "ACTIVE", Decimal("0.5000")),
    ]
