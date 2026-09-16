"""Batch A.1 comprehensive verification test suite on real PostgreSQL.

Covers:
1. BATCHA-P1-001: Safe migration 0012 -> 0013 matrix (Cases 1-8):
   - Case 1: account_snapshot_id match -> backfilled to snapshot account UUID
   - Case 2: risk_reservations match -> backfilled to reservation account UUID
   - Case 3: Both match and agree -> backfilled to agreed UUID
   - Case 4: Both match and disagree -> preflight aborts before writes
   - Case 5: Neither matches (orphan) -> preflight aborts before writes
   - Case 6: Legacy alias matches exactly 1 Account row -> resolved to Account UUID
   - Case 7: Legacy alias matches >1 Account row (multi-tenant collision) -> preflight aborts
   - Case 8: Legacy reference does not match any Account row -> preflight aborts
2. Migration atomicity & rollback on preflight failure.
3. BATCHA-P1-003: Terminal transition atomic reservation revocation concurrency race.
4. BATCHA-P1-002: Cross-tenant ambiguous account name resolution (ADMIN & system rejection, tenant isolation).
"""

import asyncio
import datetime as dt
import json
import uuid
from decimal import Decimal

import psycopg.errors
import pytest
from psycopg import sql
from sqlalchemy import text
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.errors import ForbiddenError, ValidationError
from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.models import User
from app.services.market_data.domain import Quote
from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as build_news_context
from app.services.risk.account_resolver import resolve_canonical_account
from app.services.risk.domain import AccountSnapshot, RiskPolicy, default_gold_spec
from app.services.risk.engine import risk_engine
from app.services.risk.repository import persist_risk_decision
from app.services.strategy.domain import (
    Evidence,
    SetupCandidate,
    Target,
    TradePlanSuggestion,
)
from app.services.strategy.lifecycle import (
    apply_terminal_candidate_transition,
    resolve_candidate_current_lifecycle,
)

pytestmark = pytest.mark.integration


def _make_candidate(cand_id: str, plan_id: str = "plan_race", status: str = "READY") -> SetupCandidate:
    now = dt.datetime.now(dt.UTC)
    plan = TradePlanSuggestion(
        id=plan_id,
        candidate_id=cand_id,
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
    return SetupCandidate(
        id=cand_id,
        profile_id="day_trader",
        strategy_id="STRAT01",
        strategy_version="1.0.0",
        symbol="XAUUSD",
        direction="LONG",
        status=status,
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


def test_migration_0012_to_0013_success_matrix(isolated_postgres):  # noqa: F811
    """Verifies Cases 1, 2, 3, 6 of safe migration backfill and invariant enforcement."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))

    # 1. Upgrade to baseline 0012
    _alembic("upgrade", "0012_phase5_reconciliation")

    # 2. Seed Users & Accounts
    u1_id = str(uuid.uuid4())
    u2_id = str(uuid.uuid4())
    acc1_id = str(uuid.uuid4())
    acc2_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES
            (%(u1)s, 'user1@example.com', 'hash1', 'TRADER', true, NOW(), NOW()),
            (%(u2)s, 'user2@example.com', 'hash2', 'TRADER', true, NOW(), NOW())
        """,
        {"u1": u1_id, "u2": u2_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(acc1)s, %(u1)s, 'legacy_alias_unique', 'PAPER', 10000.00, true, NOW(), NOW()),
            (%(acc2)s, %(u2)s, 'account_two', 'PAPER', 20000.00, true, NOW(), NOW())
        """,
        {"acc1": acc1_id, "acc2": acc2_id, "u1": u1_id, "u2": u2_id},
    )

    # 3. Seed snapshots
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode,
            source, as_of, payload
        ) VALUES
            ('snap_acc1', %(acc1)s, 10000.0, 10000.0, 10000.0, 0.0, 0.0, 10000.0, 0.0, 0.0, 0,
             'PAPER', 'PAPER_ACCOUNT_STATE', NOW(), '{}'),
            ('snap_acc2', %(acc2)s, 20000.0, 20000.0, 20000.0, 0.0, 0.0, 20000.0, 0.0, 0.0, 0,
             'PAPER', 'PAPER_ACCOUNT_STATE', NOW(), '{}')
        """,
        {"acc1": acc1_id, "acc2": acc2_id},
    )

    # Case 1: dec1 matched by snapshot (snap_acc1 -> acc1_id)
    # Case 2: dec2 matched by reservation (res_dec2 -> acc2_id)
    # Case 3: dec3 matched by both snapshot & reservation in agreement (snap_acc1 -> acc1_id)
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES
            ('dec_case1', 'cand1', 'plan1', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
             'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
             'snap_acc1', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
             '{"id": "dec_case1", "account_id": null}', 'fp_case1'),
            ('dec_case2', 'cand2', 'plan2', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
             'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
             'snap_placeholder_case2', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
             '{"id": "dec_case2"}', 'fp_case2'),
            ('dec_case3', 'cand3', 'plan3', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
             'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
             'snap_acc1', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
             '{"id": "dec_case3", "account_id": "old_val"}', 'fp_case3')
        """
    )

    # Reservation for Case 2 (points to acc2_id) and Case 3 (points to acc1_id)
    conn.execute(
        """
        INSERT INTO risk_reservations (
            id, decision_id, candidate_id, account_id, profile_id, symbol, direction,
            risk_pct, risk_amount, position_size, status, reserved_at, reserved_until
        ) VALUES
            ('res_case2', 'dec_case2', 'cand2', %(acc2)s, 'day_trader', 'XAUUSD', 'LONG',
             1.0, 100.0, 0.14, 'ACTIVE', NOW(), NOW() + interval '1 hour'),
            ('res_case3', 'dec_case3', 'cand3', %(acc1)s, 'day_trader', 'XAUUSD', 'LONG',
             1.0, 100.0, 0.14, 'ACTIVE', NOW(), NOW() + interval '1 hour')
        """,
        {"acc1": acc1_id, "acc2": acc2_id},
    )

    # Case 6: legacy alias in paper_account_states matching exactly one Account row
    conn.execute(
        """
        INSERT INTO paper_account_states (
            account_id, state_version, balance, equity, free_margin, peak_equity,
            state_updated_at, last_observed_at, payload
        ) VALUES (
            'legacy_alias_unique', 1, 10000.0, 10000.0, 10000.0, 10000.0,
            NOW(), NOW(), '{}'
        )
        """
    )

    # 4. Upgrade to head (0013)
    _alembic("upgrade", "head")
    _alembic("check")

    # 5. Assert backfilled values
    row1 = conn.execute("SELECT account_id, payload FROM risk_decisions WHERE id = 'dec_case1'").fetchone()
    assert row1[0] == acc1_id
    assert json.loads(row1[1] if isinstance(row1[1], str) else json.dumps(row1[1]))["account_id"] == acc1_id

    row2 = conn.execute("SELECT account_id, payload FROM risk_decisions WHERE id = 'dec_case2'").fetchone()
    assert row2[0] == acc2_id
    assert json.loads(row2[1] if isinstance(row2[1], str) else json.dumps(row2[1]))["account_id"] == acc2_id

    row3 = conn.execute("SELECT account_id, payload FROM risk_decisions WHERE id = 'dec_case3'").fetchone()
    assert row3[0] == acc1_id
    assert json.loads(row3[1] if isinstance(row3[1], str) else json.dumps(row3[1]))["account_id"] == acc1_id

    # Assert Case 6: alias resolved to acc1_id in paper_account_states
    pas_row = conn.execute("SELECT account_id FROM paper_account_states").fetchone()
    assert pas_row[0] == acc1_id

    # 6. Verify constraints: check constraint ck_risk_decision_account_id_uuid rejects non-UUID
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO risk_decisions (
                id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
                decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
                approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
                stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
                dependency_fingerprint
            ) VALUES (
                'dec_invalid_uuid', 'c_inv', 'p_inv', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                'not-a-36-char-uuid', 'snap_acc1', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}',
                'fp_inv'
            )
            """
        )


def test_migration_0012_to_0013_case4_conflict_aborts_and_rolls_back(isolated_postgres):  # noqa: F811
    """Case 4: Conflicting snapshot vs reservation evidence aborts and rolls back to 0012."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    u1 = str(uuid.uuid4())
    u2 = str(uuid.uuid4())
    acc1 = str(uuid.uuid4())
    acc2 = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES
            (%(u1)s, 'u1@ex.com', 'h', 'TRADER', true, NOW(), NOW()),
            (%(u2)s, 'u2@ex.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u1": u1, "u2": u2},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(a1)s, %(u1)s, 'acc1', 'PAPER', 10000.0, true, NOW(), NOW()),
            (%(a2)s, %(u2)s, 'acc2', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"a1": acc1, "a2": acc2, "u1": u1, "u2": u2},
    )
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode,
            source, as_of, payload
        ) VALUES (
            'snap_conf1', %(a1)s, 10000.0, 10000.0, 10000.0, 0.0, 0.0, 10000.0,
            0.0, 0.0, 0, 'PAPER', 'PAPER_ACCOUNT_STATE', NOW(), '{}'
        )
        """,
        {"a1": acc1},
    )
    # Decision points to snap_conf1 (acc1), but reservation points to acc2 -> CONFLICT
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_conf', 'c_conf', 'p_conf', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            'snap_conf1', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}', 'fp_conf'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO risk_reservations (
            id, decision_id, candidate_id, account_id, profile_id, symbol, direction,
            risk_pct, risk_amount, position_size, status, reserved_at, reserved_until
        ) VALUES (
            'res_conf', 'dec_conf', 'c_conf', %(a2)s, 'day_trader', 'XAUUSD', 'LONG',
            1.0, 100.0, 0.14, 'ACTIVE', NOW(), NOW() + interval '1 hour'
        )
        """,
        {"a2": acc2},
    )

    # Migration MUST fail
    _alembic("upgrade", "head", success=False)

    # Rollback verification: DB remains at 0012
    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == "0012_phase5_reconciliation"


def test_migration_0012_to_0013_case5_orphan_aborts_and_rolls_back(isolated_postgres):  # noqa: F811
    """Case 5: Orphan risk_decisions row with no snapshot or reservation evidence aborts."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    # Decision with non-existent snapshot and no reservation -> orphan
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_orphan', 'c_orph', 'p_orph', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            'snap_nonexistent_orphan', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour', '{}', 'fp_orph'
        )
        """
    )

    # Migration MUST fail
    _alembic("upgrade", "head", success=False)

    # Version check
    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == "0012_phase5_reconciliation"


def test_migration_0012_to_0013_case7_ambiguous_alias_aborts_and_rolls_back(isolated_postgres):  # noqa: F811
    """Case 7: Legacy alias matching >1 account across tenants aborts migration."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    u1 = str(uuid.uuid4())
    u2 = str(uuid.uuid4())
    acc1 = str(uuid.uuid4())
    acc2 = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES
            (%(u1)s, 'u1@ex.com', 'h', 'TRADER', true, NOW(), NOW()),
            (%(u2)s, 'u2@ex.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u1": u1, "u2": u2},
    )
    # Duplicate account name across tenants
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(a1)s, %(u1)s, 'colliding_account', 'PAPER', 10000.0, true, NOW(), NOW()),
            (%(a2)s, %(u2)s, 'colliding_account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"a1": acc1, "a2": acc2, "u1": u1, "u2": u2},
    )
    # Legacy alias in paper_account_states
    conn.execute(
        """
        INSERT INTO paper_account_states (
            account_id, state_version, balance, equity, free_margin, peak_equity,
            state_updated_at, last_observed_at, payload
        ) VALUES (
            'colliding_account', 1, 10000.0, 10000.0, 10000.0, 10000.0,
            NOW(), NOW(), '{}'
        )
        """
    )

    # Migration MUST fail due to multi-tenant ambiguity
    _alembic("upgrade", "head", success=False)

    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == "0012_phase5_reconciliation"


def test_migration_0012_to_0013_case8_nonexistent_account_aborts_and_rolls_back(isolated_postgres):  # noqa: F811
    """Case 8: Legacy reference matching 0 account rows aborts migration."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    conn.execute(
        """
        INSERT INTO paper_account_states (
            account_id, state_version, balance, equity, free_margin, peak_equity,
            state_updated_at, last_observed_at, payload
        ) VALUES (
            'ghost_nonexistent_acc', 1, 10000.0, 10000.0, 10000.0, 10000.0,
            NOW(), NOW(), '{}'
        )
        """
    )

    # Migration MUST fail
    _alembic("upgrade", "head", success=False)

    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == "0012_phase5_reconciliation"


def test_terminal_transition_atomic_revocation_concurrency(isolated_postgres):  # noqa: F811
    """BATCHA-P1-003: Concurrent Risk evaluate vs Terminal transition.

    Verifies:
    1. Lock serialization on predecessor candidate row.
    2. Atomic revocation of reservations upon terminal transition (INVALIDATED).
    3. Exactly 0 active reservations remaining after terminal transition.
    4. Zero deadlocks or uncaught exceptions.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    now = dt.datetime.now(dt.UTC)
    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'race_trader@example.com', 'hash', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'race_acc', 'PAPER', 10000.00, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )

    policy = RiskPolicy(
        max_risk_per_trade_pct=Decimal("1.0"),
        min_risk_per_trade_pct=Decimal("0.1"),
        max_account_risk_pct=Decimal("3.0"),
        max_symbol_risk_pct=Decimal("3.0"),
        max_directional_risk_pct=Decimal("3.0"),
        max_concurrent_trades=10,
    )
    account = AccountSnapshot(
        id="snap_race_001",
        account_id=acc_id,
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
    candidate = _make_candidate("cand_race_001")
    plan = candidate.plan
    assert plan is not None

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

    # Insert candidate into database first
    conn.execute(
        """
        INSERT INTO strategy_evaluations (
            id, context_id, symbol, source, as_of, generated_at, payload_hash, payload
        ) VALUES (
            'eval_race_001', 'ctx_race_001', 'XAUUSD', 'simulated', NOW(), NOW(), 'fp_eval', '{}'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO trade_candidates (
            id, evaluation_id, profile_id, strategy_id, as_of, payload
        ) VALUES (
            %(cand_id)s, 'eval_race_001', 'day_trader', 'STRAT01', NOW(), %(payload)s
        )
        """,
        {"cand_id": candidate.id, "payload": json.dumps(candidate.model_dump(mode="json"))},
    )

    loop = new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_race():
        factory = get_session_factory()

        async def worker_risk():
            async with factory() as session:
                await session.execute(text(f'SET search_path TO "{schema}"'))
                # 1. Lock candidate row and resolve current lifecycle (AUD-P1-001)
                lifecycle = await resolve_candidate_current_lifecycle(
                    session=session,
                    candidate_id=candidate.id,
                    profile_id=candidate.profile_id,
                    for_update=True,
                )
                if lifecycle.is_terminal:
                    return None

                # 2. Evaluate and attempt reservation
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
                    candidate_lifecycle_status=lifecycle.current_status,
                    candidate_transition_count=lifecycle.transition_count,
                )
                if dec.decision == "APPROVED":
                    await persist_risk_decision(session, dec)
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
                return dec

        async def worker_terminal():
            # Small yield to let risk worker engage concurrently
            await asyncio.sleep(0.01)
            async with factory() as session:
                await session.execute(text(f'SET search_path TO "{schema}"'))
                # Apply atomic terminal transition
                trans = await apply_terminal_candidate_transition(
                    session=session,
                    candidate_id=candidate.id,
                    target_status="INVALIDATED",
                    reason_th="ยกเลิกตามเงื่อนไขตลาด",
                    now=now,
                )
                await session.commit()
                return trans

        results = await asyncio.gather(worker_risk(), worker_terminal(), return_exceptions=True)
        return results

    try:
        res = loop.run_until_complete(run_race())
    finally:
        loop.run_until_complete(dispose_engine())
        loop.close()

    # Verify no unhandled exceptions crashed the run
    for r in res:
        if isinstance(r, Exception):
            raise r

    # Crucial assertion: Active reservations for cand_race_001 must be ZERO
    active_res = conn.execute(
        "SELECT count(*) FROM risk_reservations WHERE candidate_id = 'cand_race_001' AND status = 'ACTIVE'"
    ).fetchone()[0]
    assert active_res == 0, f"Expected 0 active reservations after terminal transition, found {active_res}"

    # Verify transition record exists
    transitions = conn.execute(
        "SELECT payload FROM candidate_transitions WHERE candidate_id = 'cand_race_001'"
    ).fetchall()
    assert any(
        (json.loads(t[0]) if isinstance(t[0], str) else t[0]).get("to_status") == "INVALIDATED"
        for t in transitions
    )


def test_rbac_and_ambiguous_account_resolution(isolated_postgres):  # noqa: F811
    """BATCHA-P1-002: Rejection of ambiguous account names and tenant isolation."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u1_id = str(uuid.uuid4())
    u2_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    acc1_id = str(uuid.uuid4())
    acc2_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES
            (%(u1)s, 'trader1@example.com', 'h1', 'TRADER', true, NOW(), NOW()),
            (%(u2)s, 'trader2@example.com', 'h2', 'TRADER', true, NOW(), NOW()),
            (%(adm)s, 'admin@example.com', 'hadm', 'ADMIN', true, NOW(), NOW())
        """,
        {"u1": u1_id, "u2": u2_id, "adm": admin_id},
    )
    # Both tenants have an account with the identical name 'default_paper_account'
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(acc1)s, %(u1)s, 'default_paper_account', 'PAPER', 10000.0, true, NOW(), NOW()),
            (%(acc2)s, %(u2)s, 'default_paper_account', 'PAPER', 20000.0, true, NOW(), NOW())
        """,
        {"acc1": acc1_id, "acc2": acc2_id, "u1": u1_id, "u2": u2_id},
    )

    loop = new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_checks():
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text(f'SET search_path TO "{schema}"'))

            user_1 = await session.get(User, u1_id)
            user_2 = await session.get(User, u2_id)
            admin_user = await session.get(User, admin_id)

            assert user_1 is not None and user_2 is not None and admin_user is not None

            # 1. Non-admin User 1 resolves ambiguous name -> strictly user 1's account
            row1, canon1 = await resolve_canonical_account(session, "default_paper_account", user=user_1)
            assert canon1 == acc1_id
            assert str(row1.id) == acc1_id

            # 2. Non-admin User 2 resolves ambiguous name -> strictly user 2's account
            row2, canon2 = await resolve_canonical_account(session, "default_paper_account", user=user_2)
            assert canon2 == acc2_id
            assert str(row2.id) == acc2_id

            # 3. Admin user resolves ambiguous name -> raises ValidationError (ambiguity rejected)
            with pytest.raises(
                ValidationError,
                match="Ambiguous account name 'default_paper_account' matches 2 accounts",
            ):
                await resolve_canonical_account(session, "default_paper_account", user=admin_user)

            # 4. System/userless call resolves ambiguous name -> raises ValidationError
            with pytest.raises(
                ValidationError,
                match="Ambiguous account name 'default_paper_account' matches 2 accounts",
            ):
                await resolve_canonical_account(session, "default_paper_account", user=None)

            # 5. Cross-tenant isolation: User 1 attempts to resolve User 2's UUID -> ForbiddenError
            with pytest.raises(ForbiddenError):
                await resolve_canonical_account(session, acc2_id, user=user_1)

    try:
        loop.run_until_complete(run_checks())
    finally:
        loop.run_until_complete(dispose_engine())
        loop.close()
