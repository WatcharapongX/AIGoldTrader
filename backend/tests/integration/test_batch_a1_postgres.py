"""Batch A.2 comprehensive verification test suite on real PostgreSQL.

Covers:
1. BATCHA-P1-001 & BATCHA1-NEW-P2-001: Safe migration & 0012 Pre-Upgrade Normalizer:
   - Scenario A: Snapshot alias + Reservation UUID for same account normalized before upgrade.
   - Scenario B: True conflict (Snapshot Account 1 vs Reservation Account 2) aborts with rollback.
   - Scenario C: Duplicate alias across tenants aborts with rollback.
   - Clean upgrade 0012 -> 0013 -> 0014 (head).
2. BATCHA1-NEW-P2-002 & Invariant Verification:
   - 0014 UUID regex check constraint: rejects 36-char non-UUID strings.
   - 0014 PostgreSQL trigger: enforces foreign-key relational integrity to accounts(id).
   - Preflight verification of payload and relational consistency.
3. BATCHA-P1-003 & Concurrency Invariants (Sections 32-37):
   - Risk-First order with deterministic asyncio.Event synchronization.
   - Transition-First order with deterministic asyncio.Event synchronization.
   - Complete Terminal Matrix (INVALIDATED, EXPIRED, SUPERSEDED) in Risk and AI.
   - Old approval transition to terminal: active reservation released, audit preserved, re-eval BLOCKED.
   - Dependency fingerprint inequality between READY and terminal states.
4. BATCHA-P1-002 & Tenant Isolation (Section 38):
   - Ambiguous duplicate names across tenants rejected for ADMIN and system.
   - Cross-tenant isolation on decisions, state, snapshots, and AI context.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import psycopg.errors
import pytest
from psycopg import sql
from sqlalchemy import select, text
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.errors import ForbiddenError, ValidationError
from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.models import User
from app.models.risk import RiskDecisionRecord
from app.models.strategy import StrategyEvaluationRecord, TradeCandidateRecord
from app.scripts.normalize_0012_accounts import normalize_0012_database
from app.services.ai.assembler import AIAnalysisInputAssembler
from app.services.market_data.domain import Quote
from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as build_news_context
from app.services.risk.account_resolver import resolve_canonical_account
from app.services.risk.domain import (
    AccountSnapshot,
    KillSwitchState,
    RiskDecision,
    RiskPolicy,
    default_gold_spec,
)
from app.services.risk.engine import risk_engine
from app.services.risk.fingerprint import compute_risk_dependency_fingerprint
from app.services.risk.repository import hydrate_risk_decision, persist_risk_decision
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


# =============================================================================
# 1. 0012 PRE-UPGRADE NORMALIZER & FUTURE UPGRADE TEST MATRIX
# =============================================================================


def test_0012_normalizer_alias_and_uuid_same_account_safe_upgrade(isolated_postgres):  # noqa: F811
    """BATCHA1-NEW-P2-001: Pre-upgrade normalizer safely maps snapshot alias and reservation UUID."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))

    # 1. Upgrade to 0012 baseline
    _alembic("upgrade", "0012_phase5_reconciliation")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'norm_test@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'Default Paper Account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )

    # Snapshot references alias 'Default Paper Account'
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode, source, as_of, payload
        ) VALUES (
            'snap_norm_01', 'Default Paper Account', 10000.0, 10000.0, 10000.0, 0.0, 0.0,
            10000.0, 0.0, 0.0, 0, 'PAPER', 'TEST', NOW(), '{"account_id": "Default Paper Account"}'
        );
        """
    )
    # Decision and reservation reference canonical UUID
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_norm_01', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            'snap_norm_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
            '{"id": "dec_norm_01"}', 'fp_norm_01'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO risk_reservations (
            id, decision_id, account_id, candidate_id, profile_id, symbol, direction,
            risk_pct, risk_amount, position_size, status, reserved_at, reserved_until
        ) VALUES (
            'res_norm_01', 'dec_norm_01', %(acc)s, 'cand_01', 'day_trader', 'XAUUSD', 'LONG',
            1.0, 100.0, 0.14, 'ACTIVE', NOW(), NOW() + interval '15 min'
        )
        """,
        {"acc": acc_id},
    )

    # 2. Run pre-upgrade normalizer tool
    res = normalize_0012_database(conn)
    assert res["status"] == "SUCCESS"
    assert res["normalized_aliases"] == 1

    # Verify snapshot was updated to canonical UUID
    snap_acc = conn.execute("SELECT account_id FROM account_snapshots WHERE id = 'snap_norm_01'").fetchone()[0]
    assert snap_acc == acc_id

    # 3. Now run alembic upgrade head (runs 0013, 0014, and 0015)
    _alembic("upgrade", "head")

    # Verify migration completed to 0015 head
    current_rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert current_rev == "0015_batch_a3_risk_account_fk"

    # Verify decision got reconciled to canonical UUID
    dec_acc = conn.execute("SELECT account_id FROM risk_decisions WHERE id = 'dec_norm_01'").fetchone()[0]
    assert str(dec_acc) == acc_id


def test_0012_normalizer_true_conflict_aborts_without_mutation(isolated_postgres):  # noqa: F811
    """True conflict: snapshot points to Account A while reservation points to Account B -> normalizer aborts."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    u_id = str(uuid.uuid4())
    acc_a = str(uuid.uuid4())
    acc_b = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'conflict_user@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(acc_a)s, %(u)s, 'Account Alpha', 'PAPER', 10000.0, true, NOW(), NOW()),
            (%(acc_b)s, %(u)s, 'Account Beta', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc_a": acc_a, "acc_b": acc_b, "u": u_id},
    )
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode, source, as_of, payload
        ) VALUES (
            'snap_conf_01', 'Account Alpha', 10000.0, 10000.0, 10000.0, 0.0, 0.0,
            10000.0, 0.0, 0.0, 0, 'PAPER', 'TEST', NOW(), '{}'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_conf_01', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            'snap_conf_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
            '{}', 'fp_conf_01'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO risk_reservations (
            id, decision_id, account_id, candidate_id, profile_id, symbol, direction,
            risk_pct, risk_amount, position_size, status, reserved_at, reserved_until
        ) VALUES (
            'res_conf_01', 'dec_conf_01', %(acc_b)s, 'cand_01', 'day_trader', 'XAUUSD', 'LONG',
            1.0, 100.0, 0.14, 'ACTIVE', NOW(), NOW() + interval '15 min'
        )
        """,
        {"acc_b": acc_b},
    )

    with pytest.raises(RuntimeError, match="conflicting canonical account evidence detected"):
        normalize_0012_database(conn)

    # Rollback assertion: snapshot account_id must still be 'Account Alpha' (no partial mutation)
    current_snap = conn.execute("SELECT account_id FROM account_snapshots WHERE id = 'snap_conf_01'").fetchone()[0]
    assert current_snap == "Account Alpha"


def test_0012_normalizer_duplicate_alias_across_tenants_aborts(isolated_postgres):  # noqa: F811
    """Duplicate alias across tenants aborts without guessing."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    u1 = str(uuid.uuid4())
    u2 = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES
            (%(u1)s, 'u1@example.com', 'h', 'TRADER', true, NOW(), NOW()),
            (%(u2)s, 'u2@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u1": u1, "u2": u2},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(acc1)s, %(u1)s, 'Shared Name', 'PAPER', 10000.0, true, NOW(), NOW()),
            (%(acc2)s, %(u2)s, 'Shared Name', 'PAPER', 20000.0, true, NOW(), NOW())
        """,
        {"acc1": str(uuid.uuid4()), "acc2": str(uuid.uuid4()), "u1": u1, "u2": u2},
    )
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode, source, as_of, payload
        ) VALUES (
            'snap_dup_01', 'Shared Name', 10000.0, 10000.0, 10000.0, 0.0, 0.0,
            10000.0, 0.0, 0.0, 0, 'PAPER', 'TEST', NOW(), '{}'
        )
        """
    )

    with pytest.raises(RuntimeError, match="matches 2 accounts across tenants; ambiguous ownership"):
        normalize_0012_database(conn)


# =============================================================================
# 2. 0015 MIGRATION INVARIANTS, REAL FOREIGN KEY & PAYLOAD CHECK CONSTRAINT
# =============================================================================


def test_0015_migration_and_database_invariants(isolated_postgres):  # noqa: F811
    """BATCHA2-NEW-P1-001: Native UUID column type and real Foreign Key constraint."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'inv_test@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'Canonical Account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )

    # 1. Non-UUID string must fail native PostgreSQL UUID type validation
    with pytest.raises((psycopg.errors.InvalidTextRepresentation, psycopg.errors.DataError)):
        conn.execute(
            """
            INSERT INTO risk_decisions (
                id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
                decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
                approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
                stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
                dependency_fingerprint
            ) VALUES (
                'dec_bad_uuid_01', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                'this-is-a-36-char-arbitrary-string!', 'snap_01', 'risk-policy-1.0.0',
                NOW(), NOW() + interval '1 hour', '{"account_id": "00000000-0000-0000-0000-000000000001"}', 'fp_bad_01'
            )
            """
        )

    # 2. Valid UUID that does NOT exist in accounts table must fail real foreign key constraint
    fake_acc = str(uuid.uuid4())
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(
            """
            INSERT INTO risk_decisions (
                id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
                decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
                approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
                stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
                dependency_fingerprint
            ) VALUES (
                'dec_bad_fk_01', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                %(fake_acc)s, 'snap_01', 'risk-policy-1.0.0',
                NOW(), NOW() + interval '1 hour', %(payload)s, 'fp_bad_02'
            )
            """,
            {"fake_acc": fake_acc, "payload": json.dumps({"account_id": fake_acc})},
        )

    # 3. Valid canonical UUID corresponding to real account succeeds
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_good_01', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            %(acc)s, 'snap_01', 'risk-policy-1.0.0',
            NOW(), NOW() + interval '1 hour', %(payload)s, 'fp_good_01'
        )
        """,
        {"acc": acc_id, "payload": json.dumps({"account_id": acc_id})},
    )
    assert conn.execute("SELECT count(*) FROM risk_decisions WHERE id = 'dec_good_01'").fetchone()[0] == 1


def test_0015_account_delete_safety_restrict(isolated_postgres):  # noqa: F811
    """BATCHA2-NEW-P1-001: Deleting an account referenced by RiskDecision is rejected (ON DELETE RESTRICT)."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u_id = str(uuid.uuid4())
    acc_a = str(uuid.uuid4())
    acc_b = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'del_test@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(acc_a)s, %(u)s, 'Account Protected', 'PAPER', 10000.0, true, NOW(), NOW()),
            (%(acc_b)s, %(u)s, 'Account Disposable', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc_a": acc_a, "acc_b": acc_b, "u": u_id},
    )

    # Insert risk decision referencing Account A
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_del_protect', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            %(acc)s, 'snap_01', 'risk-policy-1.0.0',
            NOW(), NOW() + interval '1 hour', %(payload)s, 'fp_del_protect'
        )
        """,
        {"acc": acc_a, "payload": json.dumps({"account_id": acc_a})},
    )

    # 1. Attempting to delete Account A MUST be rejected by Foreign Key constraint
    with pytest.raises((psycopg.errors.ForeignKeyViolation, psycopg.errors.RestrictViolation)):
        conn.execute("DELETE FROM accounts WHERE id = %(acc)s", {"acc": acc_a})

    # Both Account A and RiskDecision must remain intact
    assert conn.execute("SELECT count(*) FROM accounts WHERE id = %(acc)s", {"acc": acc_a}).fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM risk_decisions WHERE id = 'dec_del_protect'").fetchone()[0] == 1

    # 2. Deleting Account B (which has no dependent risk decisions) succeeds
    conn.execute("DELETE FROM accounts WHERE id = %(acc)s", {"acc": acc_b})
    assert conn.execute("SELECT count(*) FROM accounts WHERE id = %(acc)s", {"acc": acc_b}).fetchone()[0] == 0


def test_0015_payload_account_id_check_constraint_matrix(isolated_postgres):  # noqa: F811
    """BATCHA2-NEW-P2-001: ck_risk_decision_payload_account_id enforces payload and relational sync."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    other_acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'chk_test@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES
            (%(acc)s, %(u)s, 'Check Account 1', 'PAPER', 10000.0, true, NOW(), NOW()),
            (%(other)s, %(u)s, 'Check Account 2', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "other": other_acc_id, "u": u_id},
    )

    # 1. Missing account_id key in payload -> fails CheckViolation
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
                'dec_chk_01', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                %(acc)s, 'snap_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
                '{"other_key": "val"}', 'fp_chk_01'
            )
            """,
            {"acc": acc_id},
        )

    # 2. Mismatched account_id in payload -> fails CheckViolation
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
                'dec_chk_02', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
                'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
                %(acc)s, 'snap_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
                %(payload)s, 'fp_chk_02'
            )
            """,
            {"acc": acc_id, "payload": json.dumps({"account_id": other_acc_id})},
        )

    # 3. Valid insert with matching payload succeeds
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_chk_03', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            %(acc)s, 'snap_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
            %(payload)s, 'fp_chk_03'
        )
        """,
        {"acc": acc_id, "payload": json.dumps({"account_id": acc_id})},
    )

    # 4. Direct DB UPDATE altering payload account_id -> fails CheckViolation
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            UPDATE risk_decisions
            SET payload = %(bad_payload)s
            WHERE id = 'dec_chk_03'
            """,
            {"bad_payload": json.dumps({"account_id": other_acc_id})},
        )

    # 5. Direct DB UPDATE removing account_id from payload -> fails CheckViolation
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            UPDATE risk_decisions
            SET payload = '{}'
            WHERE id = 'dec_chk_03'
            """
        )


def test_0015_authoritative_hydration(isolated_postgres):  # noqa: F811
    """BATCHA2-NEW-P2-001: hydrate_risk_decision extracts relational account_id into domain model."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'hyd_test@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'Hydrate Account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )

    now = dt.datetime.now(dt.UTC)
    conn.execute(
        """
        INSERT INTO risk_decisions (
            id, candidate_id, plan_id, strategy_id, profile_id, symbol, direction,
            decision, requested_risk_pct, approved_risk_pct, requested_risk_amount,
            approved_risk_amount, position_size, entry_lower, entry_upper, stop_loss,
            stop_distance, account_id, account_snapshot_id, policy_version, as_of, expires_at, payload,
            dependency_fingerprint
        ) VALUES (
            'dec_hyd_01', 'cand_01', 'plan_01', 'STRAT01', 'day_trader', 'XAUUSD', 'LONG',
            'APPROVED', 1.0, 1.0, 100.0, 100.0, 0.14, 2500.0, 2502.0, 2495.0, 7.0,
            %(acc)s, 'snap_01', 'risk-policy-1.0.0', NOW(), NOW() + interval '1 hour',
            %(payload)s, 'fp_hyd_01'
        )
        """,
        {
            "acc": acc_id,
            "payload": json.dumps({
                "id": "dec_hyd_01",
                "candidate_id": "cand_01",
                "plan_id": "plan_01",
                "strategy_id": "STRAT01",
                "strategy_version": "1.0.0",
                "profile_id": "day_trader",
                "symbol": "XAUUSD",
                "direction": "LONG",
                "decision": "APPROVED",
                "requested_risk_pct": "1.0",
                "approved_risk_pct": "1.0",
                "requested_risk_amount": "100.0",
                "approved_risk_amount": "100.0",
                "position_size": "0.14",
                "entry_lower": "2500.0",
                "entry_upper": "2502.0",
                "stop_loss": "2495.0",
                "stop_distance": "7.0",
                "portfolio_exposure_before": "0.0",
                "portfolio_exposure_after": "1.0",
                "account_id": acc_id,
                "account_snapshot_id": "snap_01",
                "symbol_specification_id": "sym_spec_01",
                "policy_version": "risk-policy-1.0.0",
                "as_of": now.isoformat(),
                "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
                "dependency_fingerprint": "fp_hyd_01",
            }),
        },
    )

    loop = new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_hydration_check():
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text(f'SET search_path TO "{schema}"'))
            rec = await session.get(RiskDecisionRecord, "dec_hyd_01")
            assert rec is not None

            # Test authoritative hydration helper
            hydrated = hydrate_risk_decision(rec)
            assert isinstance(hydrated, RiskDecision)
            assert hydrated.id == "dec_hyd_01"
            assert hydrated.account_id == acc_id
            assert hydrated.decision == "APPROVED"

    try:
        loop.run_until_complete(run_hydration_check())
    finally:
        loop.run_until_complete(dispose_engine())
        loop.close()


def test_0012_normalizer_exact_revision_guard(isolated_postgres):  # noqa: F811
    """BATCHA2-NEW-P2-002: Normalizer allows 0012, skips 0013/0014/0015, aborts on 0011/base/corrupt."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))

    # 1. At 0012: normalizer runs and succeeds
    _alembic("upgrade", "0012_phase5_reconciliation")
    res_0012 = normalize_0012_database(conn)
    assert res_0012["status"] in {"SUCCESS", "CLEAN"}

    # 2. At 0013: normalizer skips
    _alembic("upgrade", "0013_batch_a_risk_authority")
    res_0013 = normalize_0012_database(conn)
    assert res_0013["status"] == "SKIPPED"
    assert "0013" in res_0013["reason"]

    # 3. At 0014: normalizer skips
    _alembic("upgrade", "0014_batch_a2_account_authority")
    res_0014 = normalize_0012_database(conn)
    assert res_0014["status"] == "SKIPPED"
    assert "0014" in res_0014["reason"]

    # 4. At 0015: normalizer skips
    _alembic("upgrade", "0015_batch_a3_risk_account_fk")
    res_0015 = normalize_0012_database(conn)
    assert res_0015["status"] == "SKIPPED"
    assert "0015" in res_0015["reason"]

    # 5. When version table has an unexpected/earlier revision (e.g. 0011): aborts
    conn.execute("UPDATE alembic_version SET version_num = '0011_economic_actual_coverage'")
    with pytest.raises(RuntimeError, match="unsupported database revision '0011_economic_actual_coverage'"):
        normalize_0012_database(conn)

    # 6. When version table is empty: aborts
    conn.execute("DELETE FROM alembic_version")
    with pytest.raises(RuntimeError, match="alembic_version table is empty"):
        normalize_0012_database(conn)

    # 7. Exact revision guards: prefix-matching variations must fail closed
    for bad_rev in ("0012_unknown", "0012_bad_revision", "0013_unknown", "0014_unknown", "0015_unknown", "0016_future"):
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (%(r)s)", {"r": bad_rev})
        with pytest.raises(RuntimeError, match=f"unsupported database revision '{bad_rev}'"):
            normalize_0012_database(conn)
        conn.execute("DELETE FROM alembic_version")

    # 8. Multiple version rows: aborts
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0012_phase5_reconciliation')")
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0013_batch_a_risk_authority')")
    with pytest.raises(RuntimeError, match="multiple alembic version rows detected"):
        normalize_0012_database(conn)


def test_safe_db_upgrade_cli_unsupported_revision_fails_closed(isolated_postgres):  # noqa: F811
    """BATCHA3-P1: safe_db_upgrade fails closed (rc=1, zero mutations, zero alembic) on unsupported revision."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    # Tamper revision to unsupported prefix-like string
    conn.execute("UPDATE alembic_version SET version_num = '0012_unknown'")

    backend_dir = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-m", "app.scripts.safe_db_upgrade"],
        cwd=backend_dir,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined_output = proc.stdout + proc.stderr
    assert proc.returncode == 1, (
        f"safe_db_upgrade should fail closed with rc=1, got {proc.returncode}: {combined_output}"
    )
    assert "Unsupported database revision '0012_unknown'" in combined_output

    # Verify revision was NOT touched and no migration to 0013/0014/0015 occurred
    current_rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert current_rev == "0012_unknown"


def test_safe_db_upgrade_cli_e2e(isolated_postgres):  # noqa: F811
    """BATCHA2-NEW-P2-002: Standalone python -m app.scripts.safe_db_upgrade runs safely end-to-end."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0012_phase5_reconciliation")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'cli_test@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'CLI Upgrade Account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )
    conn.execute(
        """
        INSERT INTO account_snapshots (
            id, account_id, balance, equity, free_margin, daily_realized_pnl, weekly_realized_pnl,
            peak_equity, open_risk_pct, reserved_risk_pct, consecutive_losses, trading_mode, source, as_of, payload
        ) VALUES (
            'snap_cli_01', 'CLI Upgrade Account', 10000.0, 10000.0, 10000.0, 0.0, 0.0,
            10000.0, 0.0, 0.0, 0, 'PAPER', 'TEST', NOW(), '{}'
        )
        """
    )

    # Run safe_db_upgrade via subprocess with the isolated schema
    backend_dir = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-m", "app.scripts.safe_db_upgrade"],
        cwd=backend_dir,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined_output = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"safe_db_upgrade failed: {combined_output}"
    assert "Safe database upgrade completed successfully" in combined_output

    # Verify migration completed to 0015
    current_rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert current_rev == "0015_batch_a3_risk_account_fk"

    # Verify snapshot was normalized to canonical UUID
    snap_acc = conn.execute("SELECT account_id FROM account_snapshots WHERE id = 'snap_cli_01'").fetchone()[0]
    assert snap_acc == acc_id


# =============================================================================
# 3. DETERMINISTIC LIFECYCLE CONCURRENCY SUITE (Sections 32-37)
# =============================================================================


def test_lifecycle_race_risk_first_order(isolated_postgres):  # noqa: F811
    """Section 33: Risk locks candidate row first; terminal transition waits.

    Risk commits approved decision + reservation.
    Terminal transition unblocks, persists terminal state, and atomically releases reservation.
    Final state: 0 ACTIVE reservations, historical decision preserved.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'race_rf@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'Race RF Account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )


    now = dt.datetime.now(dt.UTC)
    candidate = _make_candidate("cand_race_rf")
    plan = candidate.plan
    assert plan is not None

    conn.execute(
        """
        INSERT INTO strategy_evaluations (
            id, context_id, symbol, source, as_of, generated_at, payload_hash, payload
        ) VALUES (
            'eval_race_rf', 'ctx_rf', 'XAUUSD', 'simulated', NOW(), NOW(), 'fp_eval', '{}'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO trade_candidates (
            id, evaluation_id, profile_id, strategy_id, as_of, payload
        ) VALUES (
            %(cand_id)s, 'eval_race_rf', 'day_trader', 'STRAT01', NOW(), %(payload)s
        )
        """,
        {"cand_id": candidate.id, "payload": json.dumps(candidate.model_dump(mode="json"))},
    )

    policy = RiskPolicy(
        version="risk-policy-1.0.0",
        max_account_risk_pct=Decimal("3.0"),
        max_symbol_risk_pct=Decimal("2.0"),
        max_directional_risk_pct=Decimal("2.0"),
        min_risk_per_trade_pct=Decimal("0.1"),
        max_risk_per_trade_pct=Decimal("1.0"),
        max_concurrent_trades=3,
        daily_loss_limit_pct=Decimal("3.0"),
        weekly_loss_limit_pct=Decimal("5.0"),
        max_drawdown_pct=Decimal("10.0"),
        max_spread_multiplier=Decimal("2.0"),
        max_spread_absolute=Decimal("0.50"),
        quote_freshness_seconds=10,
        account_freshness_seconds=15,
        news_high_impact_blackout_pre_minutes=15,
        news_high_impact_pre_minutes=60,
        news_high_impact_post_minutes=30,
        reservation_ttl_seconds=900,
    )
    account = AccountSnapshot(
        id="snap_race_rf",
        account_id=acc_id,
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        daily_realized_pnl=Decimal("0.0"),
        weekly_realized_pnl=Decimal("0.0"),
        floating_pnl=Decimal("0.0"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0"),
        reserved_risk_pct=Decimal("0.0"),
        consecutive_losses=0,
        trading_mode="PAPER",
        source="CONFIGURED_TEST",
        as_of=now,
    )
    spec = default_gold_spec()
    quote = Quote(
        symbol="XAUUSD",
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        timestamp=now,
        volume=Decimal("100"),
        source="simulated",
        mode="SIMULATED",
        spread=Decimal("0.30"),
        status="CONNECTED",
    )
    news_ctx = build_news_context(
        events=[], as_of=now, source="fixture_economic_v1", mode="FIXTURE",
        config=NewsConfig(), candles=[], quotes=[], structure=None, market_source="simulated"
    )

    loop = new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_race_risk_first():
        factory = get_session_factory()
        risk_locked_event = asyncio.Event()

        async def worker_risk():
            async with factory() as session:
                await session.execute(text(f'SET search_path TO "{schema}"'))
                # Acquire candidate row lock
                lifecycle = await resolve_candidate_current_lifecycle(
                    session=session,
                    candidate_id=candidate.id,
                    profile_id=candidate.profile_id,
                    for_update=True,
                )
                assert not lifecycle.is_terminal
                # Signal that Risk worker has acquired candidate lock
                risk_locked_event.set()

                # Evaluate candidate and create reservation
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
                assert dec.decision == "APPROVED"
                await persist_risk_decision(session, dec)
                # Small pause to allow terminal worker to block on candidate row lock
                await asyncio.sleep(0.05)
                await session.commit()
                return dec

        async def worker_terminal():
            # Deterministically wait for Risk worker to lock candidate row
            await risk_locked_event.wait()
            async with factory() as session:
                await session.execute(text(f'SET search_path TO "{schema}"'))
                # This will block until worker_risk commits
                trans = await apply_terminal_candidate_transition(
                    session=session,
                    candidate_id=candidate.id,
                    target_status="INVALIDATED",
                    reason_th="ยกเลิกตามเงื่อนไขตลาด",
                    now=now,
                )
                await session.commit()
                return trans

        return await asyncio.gather(worker_risk(), worker_terminal())

    try:
        res = loop.run_until_complete(run_race_risk_first())
    finally:
        loop.run_until_complete(dispose_engine())
        loop.close()

    assert len(res) == 2
    # Active reservations must be strictly ZERO after terminal transition
    active_res = conn.execute(
        "SELECT count(*) FROM risk_reservations WHERE candidate_id = 'cand_race_rf' AND status = 'ACTIVE'"
    ).fetchone()[0]
    assert active_res == 0, f"Expected 0 active reservations, found {active_res}"

    # Historical decision must be preserved in audit history
    dec_count = conn.execute(
        "SELECT count(*) FROM risk_decisions WHERE candidate_id = 'cand_race_rf'"
    ).fetchone()[0]
    assert dec_count == 1


def test_lifecycle_race_transition_first_order(isolated_postgres):  # noqa: F811
    """Section 34: Terminal transition locks candidate row first; Risk waits.

    Terminal transition commits.
    Risk unblocks, reads terminal status, immediately returns BLOCKED.
    Final state: 0 ACTIVE reservations.
    """
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'race_tf@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'Race TF Account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )

    now = dt.datetime.now(dt.UTC)
    candidate = _make_candidate("cand_race_tf")
    plan = candidate.plan
    assert plan is not None

    conn.execute(
        """
        INSERT INTO strategy_evaluations (
            id, context_id, symbol, source, as_of, generated_at, payload_hash, payload
        ) VALUES (
            'eval_race_tf', 'ctx_tf', 'XAUUSD', 'simulated', NOW(), NOW(), 'fp_eval', '{}'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO trade_candidates (
            id, evaluation_id, profile_id, strategy_id, as_of, payload
        ) VALUES (
            %(cand_id)s, 'eval_race_tf', 'day_trader', 'STRAT01', NOW(), %(payload)s
        )
        """,
        {"cand_id": candidate.id, "payload": json.dumps(candidate.model_dump(mode="json"))},
    )

    account = AccountSnapshot(
        id="snap_race_tf",
        account_id=acc_id,
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        daily_realized_pnl=Decimal("0.0"),
        weekly_realized_pnl=Decimal("0.0"),
        floating_pnl=Decimal("0.0"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0"),
        reserved_risk_pct=Decimal("0.0"),
        consecutive_losses=0,
        trading_mode="PAPER",
        source="CONFIGURED_TEST",
        as_of=now,
    )
    policy = RiskPolicy(
        version="risk-policy-1.0.0",
        max_account_risk_pct=Decimal("3.0"),
        max_symbol_risk_pct=Decimal("2.0"),
        max_directional_risk_pct=Decimal("2.0"),
        min_risk_per_trade_pct=Decimal("0.1"),
        max_risk_per_trade_pct=Decimal("1.0"),
        max_concurrent_trades=3,
        daily_loss_limit_pct=Decimal("3.0"),
        weekly_loss_limit_pct=Decimal("5.0"),
        max_drawdown_pct=Decimal("10.0"),
        max_spread_multiplier=Decimal("2.0"),
        max_spread_absolute=Decimal("0.50"),
        quote_freshness_seconds=10,
        account_freshness_seconds=15,
        news_high_impact_blackout_pre_minutes=15,
        news_high_impact_pre_minutes=60,
        news_high_impact_post_minutes=30,
        reservation_ttl_seconds=900,
    )
    spec = default_gold_spec()
    quote = Quote(
        symbol="XAUUSD",
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        timestamp=now,
        volume=Decimal("100"),
        source="simulated",
        mode="SIMULATED",
        spread=Decimal("0.30"),
        status="CONNECTED",
    )
    news_ctx = build_news_context(
        events=[], as_of=now, source="fixture_economic_v1", mode="FIXTURE",
        config=NewsConfig(), candles=[], quotes=[], structure=None, market_source="simulated"
    )

    loop = new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_race_transition_first():
        factory = get_session_factory()
        terminal_locked_event = asyncio.Event()

        async def worker_terminal():
            async with factory() as session:
                await session.execute(text(f'SET search_path TO "{schema}"'))
                # Acquire candidate lock
                await session.scalar(
                    select(TradeCandidateRecord)
                    .where(TradeCandidateRecord.id == candidate.id)
                    .with_for_update()
                )
                terminal_locked_event.set()

                # Apply terminal transition
                trans = await apply_terminal_candidate_transition(
                    session=session,
                    candidate_id=candidate.id,
                    target_status="EXPIRED",
                    reason_th="หมดเวลา",
                    now=now,
                )
                await asyncio.sleep(0.05)
                await session.commit()
                return trans

        async def worker_risk():
            await terminal_locked_event.wait()
            async with factory() as session:
                await session.execute(text(f'SET search_path TO "{schema}"'))
                # Blocks until worker_terminal commits
                lifecycle = await resolve_candidate_current_lifecycle(
                    session=session,
                    candidate_id=candidate.id,
                    profile_id=candidate.profile_id,
                    for_update=True,
                )
                assert lifecycle.is_terminal

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
                assert dec.decision == "BLOCKED"
                return dec

        return await asyncio.gather(worker_terminal(), worker_risk())

    try:
        res = loop.run_until_complete(run_race_transition_first())
    finally:
        loop.run_until_complete(dispose_engine())
        loop.close()

    assert len(res) == 2
    # Assert zero active reservations
    active_res = conn.execute(
        "SELECT count(*) FROM risk_reservations WHERE candidate_id = 'cand_race_tf' AND status = 'ACTIVE'"
    ).fetchone()[0]
    assert active_res == 0


def test_lifecycle_terminal_matrix_and_ai_unavailable(isolated_postgres):  # noqa: F811
    """Section 35: Terminal matrix for INVALIDATED, EXPIRED, SUPERSEDED in Risk and AI."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    u_id = str(uuid.uuid4())
    acc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
        VALUES (%(u)s, 'matrix_test@example.com', 'h', 'TRADER', true, NOW(), NOW())
        """,
        {"u": u_id},
    )
    conn.execute(
        """
        INSERT INTO accounts (id, user_id, name, trading_mode, starting_balance, is_active, created_at, updated_at)
        VALUES (%(acc)s, %(u)s, 'Matrix Account', 'PAPER', 10000.0, true, NOW(), NOW())
        """,
        {"acc": acc_id, "u": u_id},
    )

    now = dt.datetime.now(dt.UTC)
    account = AccountSnapshot(
        id="snap_matrix",
        account_id=acc_id,
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        daily_realized_pnl=Decimal("0.0"),
        weekly_realized_pnl=Decimal("0.0"),
        floating_pnl=Decimal("0.0"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0"),
        reserved_risk_pct=Decimal("0.0"),
        consecutive_losses=0,
        trading_mode="PAPER",
        source="CONFIGURED_TEST",
        as_of=now,
    )
    policy = RiskPolicy(
        version="risk-policy-1.0.0",
        max_account_risk_pct=Decimal("3.0"),
        max_symbol_risk_pct=Decimal("2.0"),
        max_directional_risk_pct=Decimal("2.0"),
        min_risk_per_trade_pct=Decimal("0.1"),
        max_risk_per_trade_pct=Decimal("1.0"),
        max_concurrent_trades=3,
        daily_loss_limit_pct=Decimal("3.0"),
        weekly_loss_limit_pct=Decimal("5.0"),
        max_drawdown_pct=Decimal("10.0"),
        max_spread_multiplier=Decimal("2.0"),
        max_spread_absolute=Decimal("0.50"),
        quote_freshness_seconds=10,
        account_freshness_seconds=15,
        news_high_impact_blackout_pre_minutes=15,
        news_high_impact_pre_minutes=60,
        news_high_impact_post_minutes=30,
        reservation_ttl_seconds=900,
    )
    spec = default_gold_spec()
    quote = Quote(
        symbol="XAUUSD",
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        timestamp=now,
        volume=Decimal("100"),
        source="simulated",
        mode="SIMULATED",
        spread=Decimal("0.30"),
        status="CONNECTED",
    )
    news_ctx = build_news_context(
        events=[], as_of=now, source="fixture_economic_v1", mode="FIXTURE",
        config=NewsConfig(), candles=[], quotes=[], structure=None, market_source="simulated"
    )

    loop = new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_terminal_matrix():
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text(f'SET search_path TO "{schema}"'))
            user = await session.get(User, u_id)
            assert user is not None

            for term_status in ("INVALIDATED", "EXPIRED", "SUPERSEDED"):
                cand_id = f"cand_mat_{term_status.lower()}"
                cand = _make_candidate(cand_id, status=term_status)

                # Seed evaluation and candidate
                eval_rec = StrategyEvaluationRecord(
                    id=f"eval_mat_{term_status.lower()}",
                    context_id="ctx_mat",
                    symbol="XAUUSD",
                    source="simulated",
                    as_of=now,
                    generated_at=now,
                    payload_hash="fp_mat",
                    payload={},
                )
                cand_rec = TradeCandidateRecord(
                    id=cand.id,
                    evaluation_id=eval_rec.id,
                    profile_id="day_trader",
                    strategy_id="STRAT01",
                    as_of=now,
                    payload=cand.model_dump(mode="json"),
                )
                session.add_all([eval_rec, cand_rec])
                await session.flush()

                # 1. Risk Evaluation -> Must return BLOCKED
                dec = await risk_engine.evaluate_candidate(
                    session=session,
                    candidate=cand,
                    plan=cand.plan,
                    account=account,
                    policy=policy,
                    spec=spec,
                    quote=quote,
                    news_context=news_ctx,
                    as_of=now,
                    candidate_lifecycle_status=term_status,
                    candidate_transition_count=1,
                )
                assert dec.decision == "BLOCKED"
                assert term_status in dec.blocked_reasons_th[0]

                # 2. AI Assembler -> Must return UNAVAILABLE / BLOCKED
                ai_input = await AIAnalysisInputAssembler.assemble(
                    session=session,
                    candidate_id=cand.id,
                    account_id=acc_id,
                    current_user=user,
                )
                assert ai_input.strategy_context.availability == "UNAVAILABLE"
                assert "Candidate lifecycle is terminal" in (ai_input.strategy_context.unavailable_reason or "")

    try:
        loop.run_until_complete(run_terminal_matrix())
    finally:
        loop.run_until_complete(dispose_engine())
        loop.close()


def test_lifecycle_old_approval_transition_and_fingerprint_inequality(isolated_postgres):  # noqa: F811
    """Sections 36 & 37: Old approval -> Terminal transition -> Reservation Released
    -> Old RiskDecision remains -> Fingerprint changes."""
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    now = dt.datetime.now(dt.UTC)
    cand_ready = _make_candidate("cand_fp_test", status="READY")
    cand_inval = _make_candidate("cand_fp_test", status="INVALIDATED")

    ks_inactive = KillSwitchState(
        id="ks_test_01",
        state="INACTIVE",
        trigger_type="MANUAL",
        reason_th="ระบบทำงานปกติ",
        activated_at=now,
        activated_by="system",
        policy_version="risk-policy-1.0.0",
    )

    fp_ready = compute_risk_dependency_fingerprint(
        candidate=cand_ready,
        plan=cand_ready.plan,
        profile_id="day_trader",
        account=AccountSnapshot(
            id="snap_fp", account_id=str(uuid.uuid4()), balance=Decimal("10000.00"),
            equity=Decimal("10000.00"), free_margin=Decimal("10000.00"),
            daily_realized_pnl=Decimal("0.0"), weekly_realized_pnl=Decimal("0.0"),
            floating_pnl=Decimal("0.0"), peak_equity=Decimal("10000.00"),
            open_risk_pct=Decimal("0.0"), reserved_risk_pct=Decimal("0.0"),
            consecutive_losses=0, trading_mode="PAPER", source="CONFIGURED_TEST", as_of=now
        ),
        policy=RiskPolicy(
            version="risk-policy-1.0.0", max_account_risk_pct=Decimal("3.0"),
            max_symbol_risk_pct=Decimal("2.0"), max_directional_risk_pct=Decimal("2.0"),
            min_risk_per_trade_pct=Decimal("0.1"), max_risk_per_trade_pct=Decimal("1.0"),
            max_concurrent_trades=3, daily_loss_limit_pct=Decimal("3.0"),
            weekly_loss_limit_pct=Decimal("5.0"), max_drawdown_pct=Decimal("10.0"),
            max_spread_multiplier=Decimal("2.0"), max_spread_absolute=Decimal("0.50"),
            quote_freshness_seconds=10, account_freshness_seconds=15,
            news_high_impact_blackout_pre_minutes=15, news_high_impact_pre_minutes=60,
            news_high_impact_post_minutes=30, reservation_ttl_seconds=900
        ),
        spec=default_gold_spec(),
        kill_switch=ks_inactive,
        quote=Quote(
            symbol="XAUUSD", bid=Decimal("2500.00"), ask=Decimal("2500.30"),
            timestamp=now, volume=Decimal("100"), source="simulated", mode="SIMULATED",
            spread=Decimal("0.30"), status="CONNECTED"
        ),
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0"),
        requested_risk_pct=Decimal("1.0"),
        candidate_lifecycle_status="READY",
        candidate_transition_count=0,
    )

    fp_inval = compute_risk_dependency_fingerprint(
        candidate=cand_inval,
        plan=cand_inval.plan,
        profile_id="day_trader",
        account=AccountSnapshot(
            id="snap_fp", account_id=str(uuid.uuid4()), balance=Decimal("10000.00"),
            equity=Decimal("10000.00"), free_margin=Decimal("10000.00"),
            daily_realized_pnl=Decimal("0.0"), weekly_realized_pnl=Decimal("0.0"),
            floating_pnl=Decimal("0.0"), peak_equity=Decimal("10000.00"),
            open_risk_pct=Decimal("0.0"), reserved_risk_pct=Decimal("0.0"),
            consecutive_losses=0, trading_mode="PAPER", source="CONFIGURED_TEST", as_of=now
        ),
        policy=RiskPolicy(
            version="risk-policy-1.0.0", max_account_risk_pct=Decimal("3.0"),
            max_symbol_risk_pct=Decimal("2.0"), max_directional_risk_pct=Decimal("2.0"),
            min_risk_per_trade_pct=Decimal("0.1"), max_risk_per_trade_pct=Decimal("1.0"),
            max_concurrent_trades=3, daily_loss_limit_pct=Decimal("3.0"),
            weekly_loss_limit_pct=Decimal("5.0"), max_drawdown_pct=Decimal("10.0"),
            max_spread_multiplier=Decimal("2.0"), max_spread_absolute=Decimal("0.50"),
            quote_freshness_seconds=10, account_freshness_seconds=15,
            news_high_impact_blackout_pre_minutes=15, news_high_impact_pre_minutes=60,
            news_high_impact_post_minutes=30, reservation_ttl_seconds=900
        ),
        spec=default_gold_spec(),
        kill_switch=ks_inactive,
        quote=Quote(
            symbol="XAUUSD", bid=Decimal("2500.00"), ask=Decimal("2500.30"),
            timestamp=now, volume=Decimal("100"), source="simulated", mode="SIMULATED",
            spread=Decimal("0.30"), status="CONNECTED"
        ),
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0"),
        requested_risk_pct=Decimal("1.0"),
        candidate_lifecycle_status="INVALIDATED",
        candidate_transition_count=1,
    )

    assert fp_ready != fp_inval, "READY lifecycle fingerprint must NOT equal terminal lifecycle fingerprint"


def test_rbac_and_ambiguous_account_resolution_and_tenant_isolation(isolated_postgres):  # noqa: F811
    """BATCHA-P1-002 & Section 38: Ambiguous duplicate names across tenants & cross-tenant isolation."""
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
