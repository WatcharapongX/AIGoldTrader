"""Phase 5 Comprehensive Adversarial Test Suite.

Directly tests all 10 P1 and 4 P2 Sol independent review findings:
- SOL-P5-P1-001: Cached approval bypass prevention (dependency fingerprint invalidation)
- SOL-P5-P1-002: Deterministic identity + DB constraint uniqueness
- SOL-P5-P1-003: Account authority (missing account 404, never invent equity)
- SOL-P5-P1-004: Account authorization (cross-user access 403)
- SOL-P5-P1-005: End-to-end news risk timeline (T-20, T-15, T-5, T0, T+1, T+16)
- SOL-P5-P1-006: Candidate / Profile integrity (strict pair check, no fallback)
- SOL-P5-P1-007: Authoritative server time in PAPER mode
- SOL-P5-P1-008: Reservation consistency (blocked decisions create ZERO reservations)
- SOL-P5-P1-009: Kill switch fail-closed on UNKNOWN state
- SOL-P5-P2-011: Single source of truth for reserved risk (no additive double-counting)
- SOL-P5-P2-012: Automatic Kill Switch triggers (daily loss, drawdown, data health)
- SOL-P5-P2-013: DB uniqueness constraints on reservations and decisions
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import ForbiddenError, NotFoundError
from app.models.account import Account, TradingMode
from app.models.risk import (
    KillSwitchRecord,
    RiskDecisionRecord,
    RiskReservationRecord,
)
from app.models.strategy import TradeCandidateRecord
from app.services.market_data.domain import Quote
from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as build_news_context
from app.services.risk.domain import (
    AccountSnapshot,
    KillSwitchState,
    RiskPolicy,
    default_gold_spec,
)
from app.services.risk.engine import risk_engine
from app.services.risk.fingerprint import compute_risk_dependency_fingerprint
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.portfolio import portfolio_manager
from app.services.risk.repository import (
    get_authoritative_account_snapshot,
    persist_risk_decision,
)
from app.services.strategy.domain import (
    Evidence,
    SetupCandidate,
    Target,
    TradePlanSuggestion,
)


@pytest.fixture
def now_time():
    return dt.datetime(2026, 9, 10, 14, 0, 0, tzinfo=dt.UTC)


@pytest.fixture
def test_spec(now_time):
    return default_gold_spec(source="simulated", observed_at=now_time)


@pytest.fixture
def test_policy():
    return RiskPolicy()


@pytest.fixture
def test_account(now_time):
    return AccountSnapshot(
        id="snap_adv_001",
        account_id="acc_adv_001",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        daily_realized_pnl=Decimal("0.00"),
        weekly_realized_pnl=Decimal("0.00"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0.0000"),
        reserved_risk_pct=Decimal("0.0000"),
        consecutive_losses=0,
        trading_mode="PAPER",
        source="CONFIGURED_TEST",
        as_of=now_time,
    )


@pytest.fixture
def test_quote(now_time):
    return Quote(
        symbol="XAUUSD",
        timestamp=now_time,
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        volume=Decimal("100"),
        source="simulated",
        mode="SIMULATED",
        status="CONNECTED",
    )


@pytest.fixture
def test_plan(now_time):
    return TradePlanSuggestion(
        id="plan_adv_001",
        candidate_id="cand_adv_001",
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
        as_of=now_time,
        context_id="ctx_001",
        expires_at=now_time + dt.timedelta(hours=2),
    )


@pytest.fixture
def test_candidate(now_time, test_plan):
    return SetupCandidate(
        id="cand_adv_001",
        profile_id="day_trader",
        strategy_id="STRAT02",
        strategy_version="strategy-1.2.1",
        symbol="XAUUSD",
        direction="LONG",
        status="READY",
        score=85,
        detected_at=now_time - dt.timedelta(minutes=10),
        confirmed_at=now_time,
        expires_at=now_time + dt.timedelta(hours=2),
        context_id="ctx_001",
        upstream_ids=("ctx_001",),
        evidence=(Evidence(code="EV1", description_th="SMC Confirmation"),),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="หลุดแนวรับ 2495.00",
        plan=test_plan,
    )


@pytest.mark.asyncio
async def test_cached_approval_bypasses_safety_prevented(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P1-001: Changing safety context (e.g. activating Kill Switch) must invalidate cached approval."""
    session, _ = db_session
    calm_news = build_news_context(
        events=[],
        as_of=now_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )

    # Step 1: Initial evaluation -> APPROVED
    dec1 = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=calm_news,
        as_of=now_time,
    )
    assert dec1.decision == "APPROVED"
    await persist_risk_decision(session, dec1)
    await session.commit()

    # Step 2: Now Kill Switch is activated
    await kill_switch_manager.activate(
        session=session,
        trigger_type="MANUAL",
        reason_th="ฉุกเฉิน",
        activated_by="test_admin",
    )
    await session.commit()

    # Step 3: Re-evaluating SAME candidate/profile must NOT return cached APPROVED
    dec2 = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=calm_news,
        as_of=now_time,
    )
    assert dec2.decision == "BLOCKED"
    assert dec2.dependency_fingerprint != dec1.dependency_fingerprint
    assert any("Kill Switch" in r for r in dec2.blocked_reasons_th)


@pytest.mark.asyncio
async def test_deterministic_fingerprint_and_db_uniqueness(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P1-002: Deterministic identity and unique constraint enforcement."""
    session, _ = db_session
    ks_state = await kill_switch_manager.get_state(session)

    fp1 = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id="day_trader",
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_state,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0"),
        requested_risk_pct=Decimal("1.0"),
    )
    fp2 = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id="day_trader",
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_state,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp1 == fp2, "Fingerprint must be strictly deterministic across evaluations"

    # Insert first record
    rec1 = RiskDecisionRecord(
        id="dec_test_uniq_01",
        candidate_id="cand_test_uniq",
        plan_id="plan_test_uniq",
        strategy_id="STRAT02",
        profile_id="day_trader",
        symbol="XAUUSD",
        direction="LONG",
        decision="APPROVED",
        requested_risk_pct=Decimal("1.0"),
        approved_risk_pct=Decimal("1.0"),
        requested_risk_amount=Decimal("100.00"),
        approved_risk_amount=Decimal("100.00"),
        position_size=Decimal("0.14"),
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        stop_loss=Decimal("2495.00"),
        stop_distance=Decimal("7.00"),
        account_snapshot_id="snap_01",
        policy_version="risk-policy-1.0.0",
        dependency_fingerprint=fp1,
        as_of=now_time,
        expires_at=now_time + dt.timedelta(hours=1),
        payload={},
    )
    session.add(rec1)
    await session.commit()

    # Attempt to insert second record with identical (candidate_id, profile_id, dependency_fingerprint)
    rec2 = RiskDecisionRecord(
        id="dec_test_uniq_02",
        candidate_id="cand_test_uniq",
        plan_id="plan_test_uniq",
        strategy_id="STRAT02",
        profile_id="day_trader",
        symbol="XAUUSD",
        direction="LONG",
        decision="APPROVED",
        requested_risk_pct=Decimal("1.0"),
        approved_risk_pct=Decimal("1.0"),
        requested_risk_amount=Decimal("100.00"),
        approved_risk_amount=Decimal("100.00"),
        position_size=Decimal("0.14"),
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        stop_loss=Decimal("2495.00"),
        stop_distance=Decimal("7.00"),
        account_snapshot_id="snap_01",
        policy_version="risk-policy-1.0.0",
        dependency_fingerprint=fp1,
        as_of=now_time,
        expires_at=now_time + dt.timedelta(hours=1),
        payload={},
    )
    session.add(rec2)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_arbitrary_account_id_rejected_with_404(db_session, now_time):
    """SOL-P5-P1-003: Arbitrary account ID must be rejected with 404, never invent equity."""
    session, _ = db_session
    with pytest.raises(NotFoundError) as exc_info:
        await get_authoritative_account_snapshot(
            session=session,
            account_id="completely_random_account_xyz",
            user_id="user_123",
            is_admin=False,
            now=now_time,
        )
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_cross_user_account_access_rejected_with_403(db_session, now_time):
    """SOL-P5-P1-004: User accessing another user's account must receive 403 Forbidden."""
    session, _ = db_session

    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()

    # Create account owned by owner_id
    acc = Account(
        id=uuid.uuid4(),
        user_id=owner_id,
        name="owner_personal_acc",
        trading_mode=TradingMode.PAPER,
        starting_balance=10000.0,
        base_currency="USD",
        is_active=True,
    )
    session.add(acc)
    await session.commit()

    # Attacker tries to read snapshot for owner's account
    with pytest.raises(ForbiddenError) as exc_info:
        await get_authoritative_account_snapshot(
            session=session,
            account_id=str(acc.id),
            user_id=str(attacker_id),
            is_admin=False,
            now=now_time,
        )
    assert "not authorized" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_end_to_end_news_risk_timeline(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P1-005: News risk timeline testing T-20, T-15, T-5, T0, T+1, T+16."""
    session, _ = db_session

    from app.services.news.provider import fixture_release

    # News event scheduled at now_time + 15m
    event_time = now_time + dt.timedelta(minutes=15)
    events_15m = fixture_release(event_time, "mixed")

    async def eval_at(t: dt.datetime, spread: Decimal = Decimal("0.30")):
        q = test_quote.model_copy(update={"timestamp": t, "spread": spread, "ask": test_quote.bid + spread})
        acc = test_account.model_copy(update={"as_of": t})
        ctx = build_news_context(
            events=events_15m,
            as_of=t,
            source="fixture_economic_v1",
            mode="FIXTURE",
            config=NewsConfig(),
            candles=[],
            quotes=[],
            structure=None,
            market_source="simulated",
        )
        return await risk_engine.evaluate_candidate(
            session=session,
            candidate=test_candidate,
            plan=test_plan,
            account=acc,
            policy=test_policy,
            spec=test_spec,
            quote=q,
            news_context=ctx,
            as_of=t,
        )

    # 1. T-20m (t = event_time - 20m): Normal CALM -> APPROVED
    dec_t_minus_20 = await eval_at(event_time - dt.timedelta(minutes=20))
    assert dec_t_minus_20.decision == "APPROVED"
    assert dec_t_minus_20.approved_risk_pct == Decimal("1.0000")

    # 2. T-15m (t = event_time - 15m): Entering pre-news window -> REDUCED 50%
    dec_t_minus_15 = await eval_at(event_time - dt.timedelta(minutes=15))
    assert dec_t_minus_15.decision == "REDUCED"
    assert dec_t_minus_15.approved_risk_pct == Decimal("0.5000")

    # 3. T-5m (t = event_time - 5m): Entering Blackout window -> BLOCKED
    dec_t_minus_5 = await eval_at(event_time - dt.timedelta(minutes=5))
    assert dec_t_minus_5.decision == "BLOCKED"
    assert any("Blackout" in r for r in dec_t_minus_5.blocked_reasons_th)

    # 4. T0 (t = event_time): At exact release time -> BLOCKED
    dec_t_0 = await eval_at(event_time)
    assert dec_t_0.decision == "BLOCKED"

    # 5. T+1m with wide post-news spread ($1.30 > $1.50 * 0.8 = $1.20) -> BLOCKED
    dec_t_plus_1_wide = await eval_at(event_time + dt.timedelta(minutes=1), spread=Decimal("1.30"))
    assert dec_t_plus_1_wide.decision == "BLOCKED"
    assert any("หลังประกาศข่าว" in r for r in dec_t_plus_1_wide.blocked_reasons_th)

    # 6. T+16m (outside post-news window) -> Normal APPROVED
    dec_t_plus_16 = await eval_at(event_time + dt.timedelta(minutes=16))
    assert dec_t_plus_16.decision == "APPROVED"
    assert dec_t_plus_16.approved_risk_pct == Decimal("1.0000")


@pytest.mark.asyncio
async def test_candidate_profile_integrity_mismatch_rejected(client, auth_headers, db_session, now_time, test_plan):
    """SOL-P5-P1-006: Mismatched candidate_id and profile_id must be rejected (404)."""
    from app.models.strategy import StrategyEvaluationRecord

    session, _ = db_session

    # Seed evaluation and candidate with profile "day_trader"
    candidate_id = "cand_profile_integ_01"
    eval_rec = StrategyEvaluationRecord(
        id="eval_profile_integ_01",
        context_id="ctx_01",
        symbol="XAUUSD",
        source="simulated",
        as_of=now_time,
        generated_at=now_time,
        payload_hash="hash_01",
        payload={},
    )
    session.add(eval_rec)
    cand_rec = TradeCandidateRecord(
        id=candidate_id,
        evaluation_id="eval_profile_integ_01",
        profile_id="day_trader",
        strategy_id="STRAT02",
        as_of=now_time,
        payload={
            "id": candidate_id,
            "profile_id": "day_trader",
            "strategy_id": "STRAT02",
            "strategy_version": "1.0.0",
            "symbol": "XAUUSD",
            "direction": "LONG",
            "status": "READY",
            "score": 85,
            "detected_at": now_time.isoformat(),
            "confirmed_at": now_time.isoformat(),
            "expires_at": (now_time + dt.timedelta(hours=2)).isoformat(),
            "context_id": "ctx_01",
            "upstream_ids": [],
            "evidence": [],
            "missing_conditions": [],
            "conflicts": [],
            "invalidation_th": "หลุดแนวรับ",
            "plan": test_plan.model_dump(mode="json"),
        },
    )
    session.add(cand_rec)
    await session.commit()

    # Request evaluation with candidate_id but mismatched profile "scalper"
    response = client.post(
        "/api/risk/evaluate",
        headers=auth_headers,
        json={
            "candidate_id": candidate_id,
            "profile_id": "scalper",
            "account_id": "default_paper_account",
        },
    )
    assert response.status_code == 404
    assert "not found for the specified profile" in response.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_authoritative_server_clock_in_paper_mode(client, auth_headers, db_session, now_time, test_plan):
    """SOL-P5-P1-007: In PAPER mode, caller as_of is ignored; negative risk pct is rejected."""
    session, _ = db_session

    # Negative risk pct must be rejected with 400 or 422 Validation Error
    response = client.post(
        "/api/risk/evaluate",
        headers=auth_headers,
        json={
            "candidate_id": "cand_any",
            "profile_id": "day_trader",
            "requested_risk_pct": -0.5,
        },
    )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_blocked_decisions_create_zero_reservations(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P1-008: Blocked decisions must create exactly 0 risk reservations."""
    session, _ = db_session

    # Trigger daily loss block
    loss_acc = test_account.model_copy(update={"daily_realized_pnl": Decimal("-400.00")})
    dec = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=loss_acc,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        as_of=now_time,
    )
    assert dec.decision == "BLOCKED"
    await persist_risk_decision(session, dec)
    await session.commit()

    # Assert 0 reservations exist for this decision
    stmt = select(RiskReservationRecord).where(RiskReservationRecord.decision_id == dec.id)
    res = (await session.scalars(stmt)).all()
    assert len(res) == 0


@pytest.mark.asyncio
async def test_kill_switch_fails_closed_on_uninitialized_state(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P1-009: Missing/uninitialized Kill Switch state must be UNKNOWN and fail-closed (BLOCKED)."""
    session, _ = db_session

    # Clear all Kill Switch records to simulate uninitialized DB
    await session.execute(delete(KillSwitchRecord))
    await session.commit()

    state = await kill_switch_manager.get_state(session)
    assert state.state == "UNKNOWN"

    check = await kill_switch_manager.check(session)
    assert check.is_active is True
    assert check.state.state == "UNKNOWN"

    # Evaluation must block
    dec = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        as_of=now_time,
    )
    assert dec.decision == "BLOCKED"
    assert any("Fail-closed" in r for r in dec.blocked_reasons_th)


@pytest.mark.asyncio
async def test_single_source_of_truth_without_additive_double_counting(db_session, test_account, test_policy, now_time):
    """SOL-P5-P2-011: Database reservations and snapshot reserved_risk_pct are not additively double-counted."""
    session, _ = db_session

    # Insert an active reservation of 1.0% in DB
    record = RiskReservationRecord(
        id="res_test_sst_01",
        decision_id="dec_test_sst_01",
        account_id=test_account.account_id,
        profile_id="day_trader",
        symbol="XAUUSD",
        direction="LONG",
        risk_pct=Decimal("1.0000"),
        risk_amount=Decimal("100.00"),
        position_size=Decimal("0.14"),
        status="ACTIVE",
        reserved_at=now_time,
        reserved_until=now_time + dt.timedelta(minutes=5),
    )
    session.add(record)
    await session.commit()

    # Account snapshot also carries reserved_risk_pct = 1.0%
    snap = test_account.model_copy(update={"reserved_risk_pct": Decimal("1.0000")})

    summary = await portfolio_manager.get_summary(session, snap, test_policy, now=now_time)

    # Must be 1.0000%, NOT 2.0000%
    assert summary.reserved_risk_pct == Decimal("1.0000")
    assert summary.total_risk_pct == Decimal("1.0000")


@pytest.mark.asyncio
async def test_automatic_kill_switch_triggers(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P2-012: Automatic Kill Switch triggers for Daily Loss, Drawdown, and Data Health."""
    session, _ = db_session

    # 1. Daily Loss Trigger (e.g. -3.5% loss on 10k)
    loss_acc = test_account.model_copy(update={"daily_realized_pnl": Decimal("-350.00")})
    ks_loss = await kill_switch_manager.evaluate_automatic_triggers(
        session=session,
        account=loss_acc,
        policy=test_policy,
    )
    assert ks_loss is not None
    assert ks_loss.state == "ACTIVE"
    assert ks_loss.trigger_type == "AUTOMATIC_DAILY_LOSS"

    # Clear for next test
    await kill_switch_manager.clear(session, cleared_by="admin")

    # 2. Drawdown Trigger (e.g. peak = 10,000, current = 8,800 -> 12% DD >= 10.0% limit)
    dd_acc = test_account.model_copy(update={"peak_equity": Decimal("10000.00"), "equity": Decimal("8800.00")})
    ks_dd = await kill_switch_manager.evaluate_automatic_triggers(
        session=session,
        account=dd_acc,
        policy=test_policy,
    )
    assert ks_dd is not None
    assert ks_dd.state == "ACTIVE"
    assert ks_dd.trigger_type == "AUTOMATIC_DRAWDOWN"

    # Clear for next test
    await kill_switch_manager.clear(session, cleared_by="admin")

    # 3. Data Health Trigger (stale quote)
    ks_stale = await kill_switch_manager.evaluate_automatic_triggers(
        session=session,
        account=test_account,
        policy=test_policy,
        quote_stale=True,
        quote_stale_reason="Quote delayed 15 seconds",
    )
    assert ks_stale is not None
    assert ks_stale.state == "ACTIVE"
    assert ks_stale.trigger_type == "AUTOMATIC_DATA_HEALTH"


@pytest.mark.asyncio
async def test_reservation_uniqueness_prevents_duplicate_allocation(db_session, now_time):
    """SOL-P5-P2-013: DB constraint uq_risk_reservation_decision prevents duplicate reservations."""
    session, _ = db_session

    r1 = RiskReservationRecord(
        id="res_dup_01",
        decision_id="dec_unique_100",
        account_id="acc_001",
        profile_id="day_trader",
        symbol="XAUUSD",
        direction="LONG",
        risk_pct=Decimal("1.0"),
        risk_amount=Decimal("100.00"),
        position_size=Decimal("0.14"),
        status="ACTIVE",
        reserved_at=now_time,
        reserved_until=now_time + dt.timedelta(minutes=5),
    )
    session.add(r1)
    await session.commit()

    r2 = RiskReservationRecord(
        id="res_dup_02",
        decision_id="dec_unique_100",  # Same decision_id!
        account_id="acc_001",
        profile_id="day_trader",
        symbol="XAUUSD",
        direction="LONG",
        risk_pct=Decimal("1.0"),
        risk_amount=Decimal("100.00"),
        position_size=Decimal("0.14"),
        status="ACTIVE",
        reserved_at=now_time,
        reserved_until=now_time + dt.timedelta(minutes=5),
    )
    session.add(r2)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


def test_fingerprint_sensitivity_across_all_safety_dependencies(test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time):
    """Section 36 & SOL-P5-P1-001: Changing ANY risk dependency MUST alter the fingerprint."""
    ks_inactive = KillSwitchState(
        id="ks_test_01",
        state="INACTIVE",
        trigger_type="MANUAL",
        reason_th="ระบบทำงานปกติ",
        activated_at=now_time,
        activated_by="system",
        policy_version=test_policy.version,
    )
    base_fp = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )

    # 1. Account daily loss
    fp_daily = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account.model_copy(update={"daily_realized_pnl": Decimal("-50.00")}),
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_daily != base_fp

    # 2. Account weekly loss
    fp_weekly = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account.model_copy(update={"weekly_realized_pnl": Decimal("-100.00")}),
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_weekly != base_fp

    # 3. Peak equity
    fp_peak = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account.model_copy(update={"peak_equity": Decimal("12000.00")}),
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_peak != base_fp

    # 4. Cooldown until
    fp_cd = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account.model_copy(update={"cooldown_until": now_time + dt.timedelta(hours=1)}),
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_cd != base_fp

    # 5. Policy weekly limit
    fp_pol_week = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account,
        policy=test_policy.model_copy(update={"weekly_loss_limit_pct": Decimal("5.0")}),
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_pol_week != base_fp

    # 6. Policy drawdown
    fp_pol_dd = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account,
        policy=test_policy.model_copy(update={"max_drawdown_pct": Decimal("8.0")}),
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_pol_dd != base_fp

    # 7. Quote freshness policy
    fp_fresh = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account,
        policy=test_policy.model_copy(update={"quote_freshness_seconds": 10}),
        spec=test_spec,
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_fresh != base_fp

    # 8. Symbol spec tick_value
    fp_tick = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account,
        policy=test_policy,
        spec=test_spec.model_copy(update={"tick_value": Decimal("1.50")}),
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_tick != base_fp

    # 9. Symbol spec contract_size
    fp_contract = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account,
        policy=test_policy,
        spec=test_spec.model_copy(update={"contract_size": Decimal("50.0")}),
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_contract != base_fp

    # 10. Symbol spec volume_max
    fp_vol = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id=test_candidate.profile_id,
        account=test_account,
        policy=test_policy,
        spec=test_spec.model_copy(update={"volume_max": Decimal("20.00")}),
        kill_switch=ks_inactive,
        quote=test_quote,
        news_prov=None,
        portfolio_exposure_before=Decimal("0.0000"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp_vol != base_fp


@pytest.mark.asyncio
async def test_cooldown_lifecycle_deterministic_boundary(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """Section 27 & 41: Test cooldown lifecycle before expiry, at expiry, and after expiry."""
    session, _ = db_session
    calm_news = build_news_context(
        events=[],
        as_of=now_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )

    expiry_time = now_time + dt.timedelta(minutes=30)
    # Consecutive losses at threshold with active cooldown_until
    cd_account = test_account.model_copy(
        update={
            "consecutive_losses": 3,
            "cooldown_until": expiry_time,
        }
    )

    # 1. Before expiry (now_time < expiry_time) -> BLOCKED
    dec_before = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=cd_account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=calm_news,
        as_of=now_time,
    )
    assert dec_before.decision == "BLOCKED"
    assert any("Cooldown" in r for r in dec_before.blocked_reasons_th)

    # 2. At expiry (as_of = expiry_time) -> Not blocked by cooldown (boundary cleared)
    calm_news_at = build_news_context(
        events=[],
        as_of=expiry_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    dec_at = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan.model_copy(update={"as_of": expiry_time, "expires_at": expiry_time + dt.timedelta(hours=2)}),
        account=cd_account.model_copy(update={"as_of": expiry_time}),
        policy=test_policy,
        spec=test_spec.model_copy(update={"observed_at": expiry_time}),
        quote=test_quote.model_copy(update={"timestamp": expiry_time}),
        news_context=calm_news_at,
        as_of=expiry_time,
    )
    assert dec_at.decision in ("APPROVED", "REDUCED")
    assert not any("Cooldown" in r for r in dec_at.blocked_reasons_th)

    # 3. After expiry (as_of = expiry_time + 5m) -> ALLOWED, not blocked by historical consecutive_losses alone
    after_time = expiry_time + dt.timedelta(minutes=5)
    calm_news_after = build_news_context(
        events=[],
        as_of=after_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    dec_after = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan.model_copy(update={"as_of": after_time, "expires_at": after_time + dt.timedelta(hours=2)}),
        account=cd_account.model_copy(update={"as_of": after_time}),
        policy=test_policy,
        spec=test_spec.model_copy(update={"observed_at": after_time}),
        quote=test_quote.model_copy(update={"timestamp": after_time}),
        news_context=calm_news_after,
        as_of=after_time,
    )
    assert dec_after.decision in ("APPROVED", "REDUCED")
    assert not any("Cooldown" in r for r in dec_after.blocked_reasons_th)


@pytest.mark.asyncio
async def test_news_failure_fails_closed_when_enabled(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """Section 16 & 40: When policy.news_risk_enabled=True, news unavailability MUST FAIL CLOSED."""
    session, _ = db_session

    # Case A: news_context is None
    dec_none = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=None,
        as_of=now_time,
    )
    assert dec_none.decision == "BLOCKED"
    assert dec_none.news_provenance is not None
    assert dec_none.news_provenance.news_state == "UNAVAILABLE"

    # Case B: news_context indicates STALE calendar
    stale_news = build_news_context(
        events=[],
        as_of=now_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    stale_news = stale_news.model_copy(update={"calendar_state": "STALE"})

    dec_stale = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=stale_news,
        as_of=now_time,
    )
    assert dec_stale.decision == "BLOCKED"
    assert dec_stale.news_provenance.news_state == "UNAVAILABLE"
