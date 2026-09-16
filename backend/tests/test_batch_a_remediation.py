"""Post-Freeze Remediation — Correction Batch A Test Suite.

Verifies:
- AUD-P1-001: Terminal candidate lifecycle (INVALIDATED, EXPIRED, SUPERSEDED) enforcement in Risk and AI.
- AUD-P1-002: RBAC enforcement on POST /risk/evaluate (VIEWER rejected with 403, zero writes).
- AUD-P1-003: Tenant/account isolation on GET /risk/decisions and GET /risk/decisions/{id}.
- AUD-P1-004: Name vs UUID alias canonical account resolution and state deduplication.
"""

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Account, Role
from app.models.account import TradingMode
from app.models.risk import RiskDecisionRecord, RiskReservationRecord
from app.models.strategy import (
    CandidateTransitionRecord,
    StrategyEvaluationRecord,
    TradeCandidateRecord,
)
from app.services.ai.assembler import AIAnalysisInputAssembler
from app.services.risk.account_resolver import resolve_canonical_account
from app.services.risk.account_state import PaperAccountStateRecord, PaperAccountStateService
from app.services.strategy.domain import (
    Evidence,
    SetupCandidate,
    Target,
    TradePlanSuggestion,
    Transition,
)
from app.services.strategy.lifecycle import resolve_candidate_current_lifecycle
from app.services.users import create_user


def _make_candidate(cand_id: str, profile_id: str = "day_trader", status: str = "READY") -> SetupCandidate:
    now = dt.datetime.now(dt.UTC)
    plan = TradePlanSuggestion(
        id=f"plan_{cand_id}",
        candidate_id=cand_id,
        symbol="XAUUSD",
        direction="LONG",
        entry_type="LIMIT_ZONE",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        entry_source_id="h1_fvg",
        stop_loss=Decimal("2495.00"),
        stop_source_id="h1_swing_low",
        invalidation_th="หลุดแนวรับ",
        targets=(
            Target(name="TP1", price=Decimal("2510.00"), source_id="h4_high", rr=Decimal("1.5")),
            Target(name="TP2", price=Decimal("2520.00"), source_id="d1_high", rr=Decimal("3.0")),
        ),
        score=90,
        evidence=(Evidence(code="EV1", description_th="Confirmation"),),
        warnings_th=(),
        news_state="CALM",
        status="SUGGESTION_ONLY",
        as_of=now,
        context_id="ctx_001",
        expires_at=now + dt.timedelta(hours=2),
    )
    return SetupCandidate(
        id=cand_id,
        profile_id=profile_id,
        strategy_id="STRAT02",
        strategy_version="strategy-1.2.1",
        symbol="XAUUSD",
        direction="LONG",
        status=status,
        score=90,
        detected_at=now,
        confirmed_at=now,
        expires_at=now + dt.timedelta(hours=2),
        context_id="ctx_001",
        upstream_ids=("ctx_001",),
        evidence=(Evidence(code="EV1", description_th="Confirmation"),),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="หลุดแนวรับ",
        plan=plan,
    )


# =========================================================================
# AUD-P1-001: Terminal Candidate Lifecycle Enforcement
# =========================================================================


@pytest.mark.asyncio
async def test_aud_p1_001_lifecycle_projection_with_transitions(db_session):
    session, _ = db_session
    now = dt.datetime.now(dt.UTC)
    cand = _make_candidate("cand_trans_01", status="READY")

    # Persist candidate record
    rec = TradeCandidateRecord(
        id=cand.id,
        evaluation_id="eval_01",
        profile_id=cand.profile_id,
        strategy_id=cand.strategy_id,
        as_of=now,
        payload=cand.model_dump(mode="json"),
    )
    session.add(rec)
    await session.commit()

    # Pre-transition: active
    lifecycle_before = await resolve_candidate_current_lifecycle(session, cand.id)
    assert lifecycle_before.current_status == "READY"
    assert lifecycle_before.is_terminal is False
    assert lifecycle_before.transition_count == 0

    # Add transition to INVALIDATED
    trans = Transition(
        id="trans_01",
        candidate_id=cand.id,
        context_id="ctx_002",
        from_status="READY",
        to_status="INVALIDATED",
        as_of=now + dt.timedelta(minutes=10),
        reason_th="ราคาปิดผ่านจุดตัดขาดทุน",
    )
    trans_rec = CandidateTransitionRecord(
        id=trans.id,
        candidate_id=cand.id,
        as_of=trans.as_of,
        payload=trans.model_dump(mode="json"),
    )
    session.add(trans_rec)
    await session.commit()

    # Post-transition: terminal
    lifecycle_after = await resolve_candidate_current_lifecycle(session, cand.id)
    assert lifecycle_after.current_status == "INVALIDATED"
    assert lifecycle_after.is_terminal is True
    assert lifecycle_after.transition_count == 1
    assert "จุดตัดขาดทุน" in lifecycle_after.reason_th


def test_aud_p1_001_risk_evaluate_blocks_terminal_candidate(
    client: TestClient, auth_headers: dict[str, str], db_session
):
    session, _ = db_session
    now = dt.datetime.now(dt.UTC)
    cand = _make_candidate("cand_eval_term_01", status="READY")

    import asyncio

    async def _setup():
        rec = TradeCandidateRecord(
            id=cand.id,
            evaluation_id="eval_term_01",
            profile_id=cand.profile_id,
            strategy_id=cand.strategy_id,
            as_of=now,
            payload=cand.model_dump(mode="json"),
        )
        session.add(rec)
        await session.flush()

        # Add EXPIRED transition
        trans = Transition(
            id="trans_term_01",
            candidate_id=cand.id,
            context_id="ctx_01",
            from_status="READY",
            to_status="EXPIRED",
            as_of=now,
            reason_th="หมดอายุตามเวลา",
        )
        trans_rec = CandidateTransitionRecord(
            id=trans.id,
            candidate_id=cand.id,
            as_of=now,
            payload=trans.model_dump(mode="json"),
        )
        session.add(trans_rec)
        await session.flush()

    asyncio.run(_setup())

    # Call POST /api/risk/evaluate
    resp = client.post(
        "/api/risk/evaluate",
        headers=auth_headers,
        json={
            "candidate_id": cand.id,
            "profile_id": cand.profile_id,
            "account_id": "default_paper_account",
            "requested_risk_pct": 1.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # Must be BLOCKED with 0 reservation
    assert data["decision"] == "BLOCKED"
    assert data["approved_risk_pct"] == "0.0000"
    assert data["position_size"] == "0.0000"
    assert any("EXPIRED" in r for r in data["blocked_reasons_th"])

    # Verify zero active reservations created
    async def _verify_zero_reservations():
        stmt = select(RiskReservationRecord).where(RiskReservationRecord.candidate_id == cand.id)
        res = (await session.scalars(stmt)).all()
        assert len(res) == 0

    asyncio.run(_verify_zero_reservations())


@pytest.mark.asyncio
async def test_aud_p1_001_ai_assembler_rejects_terminal_candidate(db_session, admin_user):
    session, _ = db_session
    now = dt.datetime.now(dt.UTC)
    cand = _make_candidate("cand_ai_term_01", status="READY")

    # Persist evaluation and candidate record
    eval_rec = StrategyEvaluationRecord(
        id="eval_ai_01",
        context_id="ctx_001",
        symbol="XAUUSD",
        source="simulated",
        as_of=now,
        generated_at=now,
        payload_hash="hash01",
        payload={"context": {"symbol": "XAUUSD"}},
    )
    cand_rec = TradeCandidateRecord(
        id=cand.id,
        evaluation_id=eval_rec.id,
        profile_id=cand.profile_id,
        strategy_id=cand.strategy_id,
        as_of=now,
        payload=cand.model_dump(mode="json"),
    )
    trans = Transition(
        id="trans_ai_sup_01",
        candidate_id=cand.id,
        context_id="ctx_004",
        from_status="READY",
        to_status="SUPERSEDED",
        as_of=now + dt.timedelta(minutes=5),
        reason_th="มี revision ใหม่แทนที่",
    )
    trans_rec = CandidateTransitionRecord(
        id=trans.id,
        candidate_id=cand.id,
        as_of=trans.as_of,
        payload=trans.model_dump(mode="json"),
    )
    session.add(eval_rec)
    session.add(cand_rec)
    session.add(trans_rec)
    await session.commit()

    # Call AI input assembler
    result = await AIAnalysisInputAssembler.assemble(
        session=session,
        account_id="default_paper_account",
        candidate_id=cand.id,
        profile_id=cand.profile_id,
        current_user=admin_user,
    )
    assert result.strategy_context.availability == "UNAVAILABLE"
    assert "Candidate lifecycle is terminal (SUPERSEDED)" in result.strategy_context.unavailable_reason


# =========================================================================
# AUD-P1-002: RBAC Enforcement on POST /risk/evaluate
# =========================================================================


def test_aud_p1_002_viewer_role_forbidden_on_evaluate(client: TestClient, db_session):
    session, _ = db_session
    now = dt.datetime.now(dt.UTC)

    import asyncio
    async def _setup():
        viewer = await create_user(session, email="viewer@example.com", password="viewer-pass-123", role=Role.VIEWER)
        # Create an account owned by viewer
        acc = Account(
            name="viewer_paper_account",
            user_id=viewer.id,
            trading_mode=TradingMode.PAPER,
            starting_balance=10000.00,
            base_currency="USD",
            is_active=True,
        )
        cand = _make_candidate("cand_viewer_01")
        cand_rec = TradeCandidateRecord(
            id=cand.id,
            evaluation_id="eval_viewer_01",
            profile_id=cand.profile_id,
            strategy_id=cand.strategy_id,
            as_of=now,
            payload=cand.model_dump(mode="json"),
        )
        session.add(acc)
        session.add(cand_rec)
        await session.commit()

    asyncio.run(_setup())

    # Log in as viewer
    login_resp = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer-pass-123"})
    assert login_resp.status_code == 200
    viewer_token = login_resp.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Viewer attempts POST /risk/evaluate -> 403 Forbidden
    resp = client.post(
        "/api/risk/evaluate",
        headers=viewer_headers,
        json={
            "candidate_id": "cand_viewer_01",
            "profile_id": "day_trader",
            "account_id": "viewer_paper_account",
        },
    )
    assert resp.status_code == 403
    err_msg = resp.json().get("detail") or resp.json().get("error", {}).get("message", "")
    assert "VIEWER role cannot execute risk evaluation" in err_msg

    # Verify zero risk decisions and zero reservations created (zero state mutation)
    async def _verify_zero():
        dec_stmt = select(RiskDecisionRecord).where(RiskDecisionRecord.candidate_id == "cand_viewer_01")
        decisions = (await session.scalars(dec_stmt)).all()
        res_stmt = select(RiskReservationRecord).where(RiskReservationRecord.candidate_id == "cand_viewer_01")
        reservations = (await session.scalars(res_stmt)).all()
        assert len(decisions) == 0
        assert len(reservations) == 0

    asyncio.run(_verify_zero())


# =========================================================================
# AUD-P1-003: Tenant Isolation on Risk Decisions
# =========================================================================


def test_aud_p1_003_risk_decisions_tenant_isolation(client: TestClient, db_session, admin_user):
    session, _ = db_session
    now = dt.datetime.now(dt.UTC)

    user_a_acc_id = None
    user_b_acc_id = None
    dec_a_id = "dec_tenant_a_001"
    dec_b_id = "dec_tenant_b_001"

    import asyncio
    async def _setup():
        nonlocal user_a_acc_id, user_b_acc_id
        user_a = await create_user(session, email="tenant_a@example.com", password="pass-a-12345", role=Role.TRADER)
        user_b = await create_user(session, email="tenant_b@example.com", password="pass-b-12345", role=Role.TRADER)

        acc_a = Account(
            name="account_a",
            user_id=user_a.id,
            trading_mode=TradingMode.PAPER,
            starting_balance=10000.00,
            base_currency="USD",
            is_active=True,
        )
        acc_b = Account(
            name="account_b",
            user_id=user_b.id,
            trading_mode=TradingMode.PAPER,
            starting_balance=10000.00,
            base_currency="USD",
            is_active=True,
        )
        session.add(acc_a)
        session.add(acc_b)
        await session.flush()
        user_a_acc_id = str(acc_a.id)
        user_b_acc_id = str(acc_b.id)

        # Create decision for account A
        rec_a = RiskDecisionRecord(
            id=dec_a_id,
            candidate_id="cand_tenant_a",
            plan_id="plan_tenant_a",
            strategy_id="STRAT01",
            profile_id="day_trader",
            symbol="XAUUSD",
            direction="LONG",
            decision="APPROVED",
            requested_risk_pct=Decimal("1.0"),
            approved_risk_pct=Decimal("1.0"),
            requested_risk_amount=Decimal("100.0"),
            approved_risk_amount=Decimal("100.0"),
            position_size=Decimal("0.14"),
            entry_lower=Decimal("2500.0"),
            entry_upper=Decimal("2502.0"),
            stop_loss=Decimal("2495.0"),
            stop_distance=Decimal("7.0"),
            account_id=user_a_acc_id,
            account_snapshot_id="snap_a",
            policy_version="risk-policy-1.0.0",
            dependency_fingerprint="fp_tenant_a",
            as_of=now,
            expires_at=now + dt.timedelta(hours=1),
            payload={
                "id": dec_a_id,
                "account_id": user_a_acc_id,
                "candidate_id": "cand_tenant_a",
                "plan_id": "plan_tenant_a",
                "strategy_id": "STRAT01",
                "strategy_version": "1.0.0",
                "profile_id": "day_trader",
                "symbol": "XAUUSD",
                "direction": "LONG",
                "decision": "APPROVED",
                "requested_risk_pct": "1.0000",
                "approved_risk_pct": "1.0000",
                "requested_risk_amount": "100.00",
                "approved_risk_amount": "100.00",
                "position_size": "0.1400",
                "entry_lower": "2500.00000",
                "entry_upper": "2502.00000",
                "stop_loss": "2495.00000",
                "stop_distance": "7.00000",
                "portfolio_exposure_before": "0.0000",
                "portfolio_exposure_after": "1.0000",
                "account_snapshot_id": "snap_a",
                "symbol_specification_id": "sym_spec_01",
                "policy_version": "risk-policy-1.0.0",
                "as_of": now.isoformat(),
                "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
                "execution_blocked": "NO_EXECUTION_ANALYSIS_ONLY",
            },
        )
        # Create decision for account B
        rec_b = RiskDecisionRecord(
            id=dec_b_id,
            candidate_id="cand_tenant_b",
            plan_id="plan_tenant_b",
            strategy_id="STRAT01",
            profile_id="day_trader",
            symbol="XAUUSD",
            direction="LONG",
            decision="APPROVED",
            requested_risk_pct=Decimal("1.0"),
            approved_risk_pct=Decimal("1.0"),
            requested_risk_amount=Decimal("100.0"),
            approved_risk_amount=Decimal("100.0"),
            position_size=Decimal("0.14"),
            entry_lower=Decimal("2500.0"),
            entry_upper=Decimal("2502.0"),
            stop_loss=Decimal("2495.0"),
            stop_distance=Decimal("7.0"),
            account_id=user_b_acc_id,
            account_snapshot_id="snap_b",
            policy_version="risk-policy-1.0.0",
            dependency_fingerprint="fp_tenant_b",
            as_of=now,
            expires_at=now + dt.timedelta(hours=1),
            payload={
                "id": dec_b_id,
                "account_id": user_b_acc_id,
                "candidate_id": "cand_tenant_b",
                "plan_id": "plan_tenant_b",
                "strategy_id": "STRAT01",
                "strategy_version": "1.0.0",
                "profile_id": "day_trader",
                "symbol": "XAUUSD",
                "direction": "LONG",
                "decision": "APPROVED",
                "requested_risk_pct": "1.0000",
                "approved_risk_pct": "1.0000",
                "requested_risk_amount": "100.00",
                "approved_risk_amount": "100.00",
                "position_size": "0.1400",
                "entry_lower": "2500.00000",
                "entry_upper": "2502.00000",
                "stop_loss": "2495.00000",
                "stop_distance": "7.00000",
                "portfolio_exposure_before": "0.0000",
                "portfolio_exposure_after": "1.0000",
                "account_snapshot_id": "snap_b",
                "symbol_specification_id": "sym_spec_01",
                "policy_version": "risk-policy-1.0.0",
                "as_of": now.isoformat(),
                "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
                "execution_blocked": "NO_EXECUTION_ANALYSIS_ONLY",
            },
        )
        session.add(rec_a)
        session.add(rec_b)
        await session.commit()

    asyncio.run(_setup())

    # User A login
    login_a = client.post("/api/auth/login", json={"email": "tenant_a@example.com", "password": "pass-a-12345"})
    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

    # User B login
    login_b = client.post("/api/auth/login", json={"email": "tenant_b@example.com", "password": "pass-b-12345"})
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # Admin login
    login_admin = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    headers_admin = {"Authorization": f"Bearer {login_admin.json()['access_token']}"}

    # 1. User A lists decisions -> sees ONLY dec_a_id
    res_list_a = client.get("/api/risk/decisions", headers=headers_a)
    assert res_list_a.status_code == 200
    ids_a = [d["id"] for d in res_list_a.json()]
    assert dec_a_id in ids_a
    assert dec_b_id not in ids_a

    # 2. User B lists decisions -> sees ONLY dec_b_id
    res_list_b = client.get("/api/risk/decisions", headers=headers_b)
    assert res_list_b.status_code == 200
    ids_b = [d["id"] for d in res_list_b.json()]
    assert dec_b_id in ids_b
    assert dec_a_id not in ids_b

    # 3. Admin lists decisions -> sees BOTH
    res_list_admin = client.get("/api/risk/decisions", headers=headers_admin)
    assert res_list_admin.status_code == 200
    ids_admin = [d["id"] for d in res_list_admin.json()]
    assert dec_a_id in ids_admin
    assert dec_b_id in ids_admin

    # 4. User A fetches dec_a_id -> 200 OK
    assert client.get(f"/api/risk/decisions/{dec_a_id}", headers=headers_a).status_code == 200

    # 5. User A fetches dec_b_id -> 404 Not Found (safe non-disclosure)
    assert client.get(f"/api/risk/decisions/{dec_b_id}", headers=headers_a).status_code == 404

    # 6. User B fetches dec_b_id -> 200 OK
    assert client.get(f"/api/risk/decisions/{dec_b_id}", headers=headers_b).status_code == 200

    # 7. User B fetches dec_a_id -> 404 Not Found (safe non-disclosure)
    assert client.get(f"/api/risk/decisions/{dec_a_id}", headers=headers_b).status_code == 404


# =========================================================================
# AUD-P1-004: Canonical Account Resolution & State Deduplication
# =========================================================================


@pytest.mark.asyncio
async def test_aud_p1_004_canonical_account_resolver_and_state_dedup(db_session):
    session, _ = db_session
    now = dt.datetime.now(dt.UTC)

    owner = await create_user(session, email="owner_canon@example.com", password="owner-pass-123")
    acc = Account(
        name="alias_paper_account",
        user_id=owner.id,
        trading_mode=TradingMode.PAPER,
        starting_balance=10000.00,
        base_currency="USD",
        is_active=True,
    )
    session.add(acc)
    await session.commit()
    canonical_uuid_str = str(acc.id)

    # 1. Resolve by string name
    acc_row1, canon_id1 = await resolve_canonical_account(session, "alias_paper_account", user=owner)
    assert canon_id1 == canonical_uuid_str
    assert acc_row1.id == acc.id

    # 2. Resolve by UUID string
    acc_row2, canon_id2 = await resolve_canonical_account(session, canonical_uuid_str, user=owner)
    assert canon_id2 == canonical_uuid_str
    assert acc_row2.id == acc.id

    # 3. Initialize paper state using name alias
    state_via_name = await PaperAccountStateService.get_or_create_paper_state(session, "alias_paper_account", now)
    await session.commit()
    assert state_via_name.account_id == canonical_uuid_str

    # 4. Initialize paper state using UUID
    state_via_uuid = await PaperAccountStateService.get_or_create_paper_state(session, canonical_uuid_str, now)
    await session.commit()
    assert state_via_uuid.account_id == canonical_uuid_str

    # 5. Verify exactly ONE record exists in paper_account_states, keyed by canonical UUID
    all_states = (
        await session.scalars(
            select(PaperAccountStateRecord).where(
                (PaperAccountStateRecord.account_id == canonical_uuid_str)
                | (PaperAccountStateRecord.account_id == "alias_paper_account")
            )
        )
    ).all()
    assert len(all_states) == 1
    assert all_states[0].account_id == canonical_uuid_str


@pytest.mark.asyncio
async def test_aud_p1_004_cross_tenant_duplicate_account_names(db_session):
    session, _ = db_session

    user_1 = await create_user(session, email="dup_user1@example.com", password="pass-user-1")
    user_2 = await create_user(session, email="dup_user2@example.com", password="pass-user-2")

    acc_1 = Account(
        name="trading_account",
        user_id=user_1.id,
        trading_mode=TradingMode.PAPER,
        starting_balance=10000.00,
        base_currency="USD",
        is_active=True,
    )
    acc_2 = Account(
        name="trading_account",
        user_id=user_2.id,
        trading_mode=TradingMode.PAPER,
        starting_balance=10000.00,
        base_currency="USD",
        is_active=True,
    )
    session.add(acc_1)
    session.add(acc_2)
    await session.commit()

    # User 1 resolves "trading_account" -> gets User 1's account
    row1, canon1 = await resolve_canonical_account(session, "trading_account", user=user_1)
    assert canon1 == str(acc_1.id)

    # User 2 resolves "trading_account" -> gets User 2's account
    row2, canon2 = await resolve_canonical_account(session, "trading_account", user=user_2)
    assert canon2 == str(acc_2.id)

    # Assert completely isolated UUIDs
    assert canon1 != canon2
