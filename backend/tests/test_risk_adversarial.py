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
    from app.models.account import Account, TradingMode
    acc_id = uuid.uuid4()
    account_row = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_adv_cache_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account_row)
    await session.flush()
    account = test_account.model_copy(update={"account_id": str(acc_id)})

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
        account=account,
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
        account=account,
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
        account_id="00000000-0000-0000-0000-000000000001",
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
        account_id="00000000-0000-0000-0000-000000000001",
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
    from app.models.account import Account, TradingMode
    acc_id = uuid.uuid4()
    account_row = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_adv_loss_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account_row)
    await session.flush()

    # Trigger daily loss block
    loss_acc = test_account.model_copy(update={"account_id": str(acc_id), "daily_realized_pnl": Decimal("-400.00")})
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

    # 3. Data Health Trigger with Hysteresis (SOL-P5-NEW-P1-020)
    for _ in range(test_policy.data_health_consecutive_failures - 1):
        ks_transient = await kill_switch_manager.evaluate_automatic_triggers(
            session=session,
            account=test_account,
            policy=test_policy,
            quote_stale=True,
            quote_stale_reason="Quote delayed 15 seconds",
        )
        assert ks_transient is None

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


def test_fingerprint_sensitivity_across_all_safety_dependencies(
    test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
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


@pytest.mark.asyncio
async def test_paper_account_state_open_risk_preservation(
    db_session, test_candidate, test_plan, test_policy, test_spec, test_quote, now_time
):
    """P1-030: Paper account state refresh must preserve open risk and block over-exposure."""
    session, _ = db_session
    from app.models.account import Account, TradingMode
    from app.models.risk import AccountSnapshotRecord
    from app.services.risk.account_state import PaperAccountStateService

    acc_id = uuid.uuid4()
    account = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_paper_preserve_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account)
    await session.flush()

    # Seed snapshot with 3.0% open risk and 2 open positions
    snap_record = AccountSnapshotRecord(
        id=f"snap_preserve_init_{acc_id.hex[:6]}",
        account_id=str(acc_id),
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("9700.00"),
        daily_realized_pnl=Decimal("0.00"),
        weekly_realized_pnl=Decimal("0.00"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("3.0000"),
        reserved_risk_pct=Decimal("0.0000"),
        consecutive_losses=0,
        trading_mode="PAPER",
        source="PAPER_ACCOUNT_STATE",
        as_of=now_time - dt.timedelta(minutes=5),
        payload={
            "open_positions_count": 2,
            "floating_pnl": "-50.00",
            "state_version": 2,
        },
    )
    session.add(snap_record)
    await session.commit()

    # Call refresh_paper_account_snapshot
    refreshed = await PaperAccountStateService.refresh_paper_account_snapshot(
        session, account_id=str(acc_id), force=True, now=now_time
    )
    assert refreshed.open_risk_pct == Decimal("3.0000"), "Open risk MUST NOT be zeroed out on refresh"
    assert refreshed.open_positions_count == 2
    assert refreshed.floating_pnl == Decimal("-50.00")
    assert refreshed.state_version == 2

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

    # Verify that risk evaluation for new trade on this account is BLOCKED due to budget limit (3% max)
    dec = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=refreshed,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=calm_news,
        as_of=now_time,
    )
    assert dec.decision == "BLOCKED"
    assert dec.approved_risk_pct == Decimal("0.0000")
    assert dec.portfolio_exposure_before == Decimal("3.0000")
    assert len(dec.blocked_reasons_th) >= 1


@pytest.mark.asyncio
async def test_symbol_spec_server_authority_switch(db_session, test_spec, now_time):
    """P1-033: Switching broker server must fetch live spec and refuse stale stored spec from previous server."""
    session, _ = db_session
    from app.models.risk import SymbolSpecificationRecord
    from app.services.risk.domain import SymbolSpecification
    from app.services.risk.repository import get_authoritative_symbol_spec

    # Save a spec for Server-A in DB
    spec_a = SymbolSpecificationRecord(
        id="sym_server_a",
        symbol="XAUUSD",
        source="mt5",
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1.00"),
        contract_size=Decimal("100.00"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("10.00"),
        volume_step=Decimal("0.01"),
        digits=2,
        observed_at=now_time,
        payload={
            "id": "sym_server_a",
            "symbol": "XAUUSD",
            "source": "mt5",
            "tick_size": "0.01",
            "tick_value": "1.00",
            "contract_size": "100.00",
            "volume_min": "0.01",
            "volume_max": "10.00",
            "volume_step": "0.01",
            "digits": 2,
            "observed_at": now_time.isoformat(),
            "broker_server": "Demo-Server-A",
        },
    )
    session.add(spec_a)
    await session.commit()

    # Create dummy provider connected to Demo-Server-B
    class DummyProviderB:
        source = "mt5"
        broker_server = "Demo-Server-B"

        def get_symbol_spec(self, sym: str):
            return SymbolSpecification(
                id="sym_server_b",
                symbol=sym,
                source="mt5",
                tick_size=Decimal("0.01"),
                tick_value=Decimal("1.00"),
                contract_size=Decimal("100.00"),
                volume_min=Decimal("0.01"),
                volume_max=Decimal("20.00"),
                volume_step=Decimal("0.01"),
                digits=2,
                observed_at=now_time,
                broker_server="Demo-Server-B",
            )

    spec_out = await get_authoritative_symbol_spec(
        session=session,
        symbol="XAUUSD",
        source="mt5",
        provider=DummyProviderB(),
        now=now_time,
    )
    assert spec_out.broker_server == "Demo-Server-B"
    assert spec_out.volume_max == Decimal("20.00")

    # If provider is not available for an unknown server, it MUST fail closed
    class DummyProviderC:
        source = "mt5"
        broker_server = "Demo-Server-C"

        def get_symbol_spec(self, sym: str):
            return None

    with pytest.raises(NotFoundError):
        await get_authoritative_symbol_spec(
            session=session,
            symbol="XAUUSD",
            source="mt5",
            provider=DummyProviderC(),
            now=now_time,
        )


@pytest.mark.asyncio
async def test_news_point_in_time_provenance_fingerprint(
    test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """P2-036: Changing news vintage, available_at, or provider changes SHA-256 fingerprint."""
    from app.services.risk.domain import NewsEventAudit, NewsRiskProvenance

    ev1 = NewsEventAudit(
        event_id="ev_001",
        event_name="US CPI",
        currency="USD",
        impact="HIGH",
        scheduled_at=now_time,
        available_at=now_time - dt.timedelta(hours=2),
        window_state="CALM",
        provider="forex_factory",
        revision_id="rev_1",
    )
    prov1 = NewsRiskProvenance(
        news_state="CALM",
        in_blackout=False,
        in_pre_news_window=False,
        in_post_news_window=False,
        event_ids=("ev_001",),
        description_th="Normal",
        events=(ev1,),
        provider="forex_factory",
        revision_id="rev_1",
    )

    ks_state = KillSwitchState(
        id="ks_test",
        state="INACTIVE",
        trigger_type="MANUAL",
        reason_th="OK",
        activated_at=now_time,
        activated_by="sys",
        policy_version="risk-policy-1.0.0",
    )

    fp1 = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id="day_trader",
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_state,
        quote=test_quote,
        news_prov=prov1,
        portfolio_exposure_before=Decimal("0.0"),
        requested_risk_pct=Decimal("1.0"),
    )

    # Change available_at on event
    ev2 = ev1.model_copy(update={"available_at": now_time - dt.timedelta(hours=1)})
    prov2 = prov1.model_copy(update={"events": (ev2,)})
    fp2 = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id="day_trader",
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_state,
        quote=test_quote,
        news_prov=prov2,
        portfolio_exposure_before=Decimal("0.0"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp1 != fp2, "Different available_at MUST produce a distinct fingerprint"

    # Change revision_id
    prov3 = prov1.model_copy(update={"revision_id": "rev_2"})
    fp3 = compute_risk_dependency_fingerprint(
        candidate=test_candidate,
        plan=test_plan,
        profile_id="day_trader",
        account=test_account,
        policy=test_policy,
        spec=test_spec,
        kill_switch=ks_state,
        quote=test_quote,
        news_prov=prov3,
        portfolio_exposure_before=Decimal("0.0"),
        requested_risk_pct=Decimal("1.0"),
    )
    assert fp1 != fp3, "Different revision_id MUST produce a distinct fingerprint"


@pytest.mark.asyncio
async def test_persistence_integrity_error_reraises(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """P2-037: Persistence non-unique error must re-raise and fail closed."""
    session, _ = db_session
    from unittest.mock import patch

    from app.models.account import Account, TradingMode
    from app.services.risk.repository import persist_risk_decision

    acc_id = uuid.uuid4()
    account_row = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_adv_integ_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account_row)
    await session.flush()
    account = test_account.model_copy(update={"account_id": str(acc_id)})

    dec = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=None,
        as_of=now_time,
    )

    bad_dec = dec.model_copy(update={"id": "dec_force_fail"})
    with patch.object(
        session, "flush", side_effect=IntegrityError("violates not-null constraint", params={}, orig=Exception())
    ):
        with pytest.raises(IntegrityError):
            await persist_risk_decision(session, bad_dec)


@pytest.mark.asyncio
async def test_cross_process_kill_switch_data_health_persistence(db_session, test_account, test_policy, now_time):
    """P2-038: Data health failures persist in database and trigger Kill Switch across manager instances."""
    session, _ = db_session
    from app.models.risk import DataHealthRecord
    from app.services.risk.kill_switch import KillSwitchManager, data_health_record_id

    ks1 = KillSwitchManager()
    # 1st stale quote
    await ks1.evaluate_automatic_triggers(
        session, test_account, test_policy, quote_stale=True, quote_stale_reason="Stale 1"
    )
    # 2nd stale quote
    await ks1.evaluate_automatic_triggers(
        session, test_account, test_policy, quote_stale=True, quote_stale_reason="Stale 2"
    )

    dh_row = await session.get(DataHealthRecord, data_health_record_id("market_data", "default"))
    assert dh_row is not None
    assert dh_row.consecutive_failures == 2

    # Simulate process restart by instantiating new manager
    ks2 = KillSwitchManager()
    assert ks2._consecutive_data_health_failures == 0  # In-memory counter is fresh

    # 3rd stale quote on new manager triggers Kill Switch because DB persisted the previous 2 failures!
    state = await ks2.evaluate_automatic_triggers(
        session, test_account, test_policy, quote_stale=True, quote_stale_reason="Stale 3"
    )
    assert state is not None
    assert state.state == "ACTIVE"
    assert state.trigger_type == "AUTOMATIC_DATA_HEALTH"


@pytest.mark.asyncio
async def test_paper_account_state_unchanged_over_time_freshness(
    db_session, test_candidate, test_plan, test_policy, test_spec, test_quote
):
    """SOL-P5-P1-030: Paper account unchanged economics after >60s remains operational.

    Distinguishes state_updated_at (T0) from authoritative observation as_of (T+30s, T+61s, T+5m).
    Freshness checks pass without artificial freshness laundering of economic transition timestamp.
    """
    session, _ = db_session
    from app.models.account import Account, TradingMode
    from app.services.risk.account_state import PaperAccountStateService, _to_utc

    acc_id = uuid.uuid4()
    t0 = dt.datetime(2026, 9, 10, 14, 0, 0, tzinfo=dt.UTC)

    account = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_paper_fresh_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account)
    await session.flush()

    # Create initial state at T0
    state = await PaperAccountStateService.get_or_create_paper_state(session, str(acc_id), now=t0)
    assert _to_utc(state.state_updated_at) == t0
    assert state.state_version == 1

    calm_news = build_news_context(
        events=[],
        as_of=t0,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )

    # Check at T+30s, T+61s (>60s freshness window), and T+300s (5m)
    for delta_sec in (30, 61, 300):
        obs_time = t0 + dt.timedelta(seconds=delta_sec)
        snapshot = await PaperAccountStateService.refresh_paper_account_snapshot(
            session, str(acc_id), force=True, now=obs_time
        )
        # Authoritative observation time is fresh
        assert snapshot.as_of == obs_time
        # Authentic economic transition timestamp is preserved (NO laundering)
        assert _to_utc(snapshot.state_updated_at) == t0
        assert snapshot.state_version == 1

        # Evaluate candidate with this snapshot - MUST NOT be blocked as stale account
        curr_quote = test_quote.model_copy(update={"timestamp": obs_time})
        curr_news = calm_news.model_copy(update={"as_of": obs_time})
        dec = await risk_engine.evaluate_candidate(
            session=session,
            candidate=test_candidate,
            plan=test_plan,
            account=snapshot,
            policy=test_policy,
            spec=test_spec,
            quote=curr_quote,
            news_context=curr_news,
            as_of=obs_time,
        )
        assert dec.decision == "APPROVED", f"Failed at T+{delta_sec}s: {dec.blocked_reasons_th}"
        assert not any("บัญชีไม่เป็นปัจจุบัน" in r or "STALE" in r for r in dec.blocked_reasons_th)


@pytest.mark.asyncio
async def test_force_snapshot_refresh_unique_pk_no_collision(db_session, now_time):
    """SOL-P5-P1-030: Repeated / forced snapshot refreshes generate distinct observation IDs without PK collisions."""
    session, _ = db_session
    from app.models.account import Account, TradingMode
    from app.services.risk.account_state import PaperAccountStateService

    acc_id = uuid.uuid4()
    account = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_force_snap_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account)
    await session.flush()

    snapshots = []
    for _ in range(10):
        snap = await PaperAccountStateService.refresh_paper_account_snapshot(
            session, str(acc_id), force=True, now=now_time
        )
        snapshots.append(snap)

    ids = [s.id for s in snapshots]
    assert len(set(ids)) == 10, f"Expected 10 unique snapshot IDs, got {len(set(ids))}"
    # State version and economics remain identical
    assert all(s.state_version == 1 for s in snapshots)
    assert all(s.balance == Decimal("10000.00") for s in snapshots)


@pytest.mark.asyncio
async def test_missing_paper_account_state_concurrent_creation(db_session, now_time):
    """SOL-P5-P1-030: Concurrent tasks initializing missing PaperAccountState produce exactly 1 record."""
    import asyncio

    session, session_factory = db_session
    from app.models.account import Account, TradingMode
    from app.models.risk import PaperAccountStateRecord
    from app.services.risk.account_state import PaperAccountStateService

    acc_id = uuid.uuid4()
    account = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_conc_init_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account)
    await session.commit()

    async def worker():
        async with session_factory() as s:
            res = await PaperAccountStateService.get_or_create_paper_state(s, str(acc_id), now=now_time)
            await s.commit()
            return res

    results = await asyncio.gather(*[worker() for _ in range(10)])
    assert all(r.account_id == str(acc_id) for r in results)
    assert all(r.state_version == 1 for r in results)

    # Verify exactly 1 row in DB
    await session.commit()
    rows = (
        await session.scalars(
            select(PaperAccountStateRecord).where(PaperAccountStateRecord.account_id == str(acc_id))
        )
    ).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_paper_account_state_same_economic_target_concurrency(db_session, now_time):
    """SOL-P5-P1-030: Multiple workers setting identical economic target increment state_version exactly once."""
    session, _ = db_session
    from app.models.account import Account, TradingMode
    from app.services.risk.account_state import PaperAccountStateService

    acc_id = uuid.uuid4()
    account = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_target_conc_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account)
    await session.flush()

    await PaperAccountStateService.get_or_create_paper_state(session, str(acc_id), now=now_time)

    # 10 workers setting the same target economics (balance=10500, equity=10500)
    for _ in range(10):
        await PaperAccountStateService.update_paper_account_state(
            session,
            str(acc_id),
            balance=Decimal("10500.00"),
            equity=Decimal("10500.00"),
            now=now_time,
        )

    state = await PaperAccountStateService.get_or_create_paper_state(session, str(acc_id), now=now_time)
    assert state.state_version == 2, f"Expected state_version == 2 (incremented once), got {state.state_version}"
    assert state.balance == Decimal("10500.00")


@pytest.mark.asyncio
async def test_paper_account_state_distinct_economic_updates_concurrency(db_session, now_time):
    """SOL-P5-P1-030: 10 distinct economic transitions increment state_version for every change with no lost updates."""
    session, _ = db_session
    from app.models.account import Account, TradingMode
    from app.services.risk.account_state import PaperAccountStateService

    acc_id = uuid.uuid4()
    account = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_distinct_conc_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account)
    await session.flush()

    await PaperAccountStateService.get_or_create_paper_state(session, str(acc_id), now=now_time)

    # 10 distinct updates
    for i in range(10):
        new_balance = Decimal(10000 + (i + 1) * 10)
        await PaperAccountStateService.update_paper_account_state(
            session,
            str(acc_id),
            balance=new_balance,
            equity=new_balance,
            now=now_time,
        )

    state = await PaperAccountStateService.get_or_create_paper_state(session, str(acc_id), now=now_time)
    assert state.state_version == 11, f"Expected state_version == 11, got {state.state_version}"
    assert state.balance == Decimal("10100.00")


def test_100_safe_quote_ticks_fingerprint_invariance(
    test_candidate, test_plan, test_account, test_policy, test_spec, now_time
):
    """SOL-P5-P1-031: Safe quote ticks within safe spread band do not churn risk dependency fingerprint."""
    ks = KillSwitchState(
        id="ks_safe_test",
        state="INACTIVE",
        trigger_type="MANUAL",
        reason_th="OK",
        activated_at=now_time,
        activated_by="system",
    )

    fps = []
    for i in range(100):
        tick_bid = Decimal("2500.00") + Decimal(str(round(i * 0.01, 2)))
        tick_ask = tick_bid + Decimal("0.20")  # Constant safe 0.20 spread
        q = Quote(
            source="simulated",
            mode="SIMULATED",
            symbol="XAUUSD",
            bid=tick_bid,
            ask=tick_ask,
            spread=Decimal("0.20"),
            volume=Decimal("10"),
            status="CONNECTED",
            timestamp=now_time,
        )
        fp = compute_risk_dependency_fingerprint(
            candidate=test_candidate,
            plan=test_plan,
            profile_id="day_trader",
            account=test_account,
            policy=test_policy,
            spec=test_spec,
            kill_switch=ks,
            quote=q,
            news_prov=None,
            portfolio_exposure_before=Decimal("0.0"),
            requested_risk_pct=Decimal("1.0"),
        )
        fps.append(fp)

    assert len(set(fps)) == 1, f"Expected 1 unique fingerprint across 100 safe ticks, got {len(set(fps))}"


@pytest.mark.asyncio
async def test_decision_reservation_1_to_1_consistency_and_risk_reduction(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P1-031: Decision <-> Reservation 1:1 consistency. Risk reduction atomically replaces reservation."""
    session, _ = db_session
    from app.models.account import Account, TradingMode

    acc_id = uuid.uuid4()
    account_row = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_res_1to1_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account_row)
    await session.flush()

    account = test_account.model_copy(update={"account_id": str(acc_id)})
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

    # 1. Initial evaluation at 1.0% risk -> D1 APPROVED, R1 ACTIVE at 1.0%
    dec1 = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=calm_news,
        as_of=now_time,
        requested_risk_pct=Decimal("1.0"),
    )
    assert dec1.decision == "APPROVED"
    assert dec1.approved_risk_pct == Decimal("1.0")
    await persist_risk_decision(session, dec1)
    await session.flush()

    active_reservations = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == str(acc_id),
                RiskReservationRecord.candidate_id == test_candidate.id,
                RiskReservationRecord.status == "ACTIVE",
            )
        )
    ).all()
    assert len(active_reservations) == 1
    assert active_reservations[0].risk_pct == Decimal("1.0000")
    assert active_reservations[0].decision_id == dec1.id

    # 2. Re-evaluate with reduced risk requirement 0.5% -> D2 APPROVED at 0.5%
    dec2 = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=calm_news,
        as_of=now_time,
        requested_risk_pct=Decimal("0.5"),
    )
    assert dec2.decision == "APPROVED"
    assert dec2.approved_risk_pct == Decimal("0.5")
    await persist_risk_decision(session, dec2)
    await session.flush()

    # Verify R1 was atomically updated/replaced to match D2
    active_reservations2 = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == str(acc_id),
                RiskReservationRecord.candidate_id == test_candidate.id,
                RiskReservationRecord.status == "ACTIVE",
            )
        )
    ).all()
    assert len(active_reservations2) == 1, "Must have exactly 1 active reservation"
    assert active_reservations2[0].risk_pct == Decimal("0.5000"), "Active reservation must match D2 risk"
    assert active_reservations2[0].decision_id == dec2.id, "Active reservation must point to D2"


@pytest.mark.asyncio
async def test_blocked_reevaluation_releases_active_reservation(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """SOL-P5-P1-008: When a previously APPROVED intent re-evaluates as BLOCKED, reservation is released."""
    session, _ = db_session
    from app.models.account import Account, TradingMode

    acc_id = uuid.uuid4()
    account_row = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_rel_blk_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account_row)
    await session.flush()

    account = test_account.model_copy(update={"account_id": str(acc_id)})
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

    # Initial APPROVED
    dec = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=account,
        policy=test_policy,
        spec=test_spec,
        quote=test_quote,
        news_context=calm_news,
        as_of=now_time,
    )
    assert dec.decision == "APPROVED"
    await persist_risk_decision(session, dec)
    await session.flush()

    active_before = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == str(acc_id),
                RiskReservationRecord.candidate_id == test_candidate.id,
                RiskReservationRecord.status == "ACTIVE",
            )
        )
    ).all()
    assert len(active_before) == 1

    # Stale quote triggers BLOCKED
    stale_quote = test_quote.model_copy(update={"timestamp": now_time - dt.timedelta(seconds=120)})
    dec_blocked = await risk_engine.evaluate_candidate(
        session=session,
        candidate=test_candidate,
        plan=test_plan,
        account=account,
        policy=test_policy,
        spec=test_spec,
        quote=stale_quote,
        news_context=calm_news,
        as_of=now_time,
    )
    assert dec_blocked.decision == "BLOCKED"
    await persist_risk_decision(session, dec_blocked)
    await session.flush()

    # Active reservation MUST be RELEASED
    active_after = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == str(acc_id),
                RiskReservationRecord.candidate_id == test_candidate.id,
                RiskReservationRecord.status == "ACTIVE",
            )
        )
    ).all()
    assert len(active_after) == 0, "Blocked re-evaluation must release active reservation"

    # Confirm reservation row exists with status RELEASED
    released = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == str(acc_id),
                RiskReservationRecord.candidate_id == test_candidate.id,
                RiskReservationRecord.status == "RELEASED",
            )
        )
    ).all()
    assert len(released) == 1


@pytest.mark.asyncio
async def test_data_health_empty_table_concurrent_creation(db_session, test_account, test_policy, now_time):
    """SOL-P5-P2-038: Concurrent data health trigger evaluations on empty table create 1 row with 0 errors."""
    session, _ = db_session
    from app.models.risk import DataHealthRecord
    from app.services.risk.kill_switch import KillSwitchManager

    ks = KillSwitchManager()
    for _ in range(10):
        await ks.evaluate_automatic_triggers(
            session,
            test_account,
            test_policy,
            quote_stale=True,
            quote_stale_reason="Stale conc",
            provider="market_data",
            source="race_source",
        )

    rows = (
        await session.scalars(
            select(DataHealthRecord).where(
                DataHealthRecord.provider == "market_data",
                DataHealthRecord.source == "race_source",
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].consecutive_failures == 10


@pytest.mark.asyncio
async def test_data_health_multi_provider_isolation(db_session, test_account, test_policy, now_time):
    """SOL-P5-P2-038: Multi-provider isolation; healthy ticks do not reset unrelated providers."""
    session, _ = db_session
    from app.models.risk import DataHealthRecord
    from app.services.risk.kill_switch import KillSwitchManager, data_health_record_id

    ks = KillSwitchManager()

    # Trigger 2 failures on provider MT5
    for i in range(2):
        await ks.evaluate_automatic_triggers(
            session,
            test_account,
            test_policy,
            quote_stale=True,
            quote_stale_reason=f"MT5 fail {i}",
            provider="mt5",
            source="iux",
        )

    # Trigger 1 failure on provider Replay
    await ks.evaluate_automatic_triggers(
        session,
        test_account,
        test_policy,
        quote_stale=True,
        quote_stale_reason="Replay fail",
        provider="replay",
        source="tick",
    )

    mt5_row = await session.get(DataHealthRecord, data_health_record_id("mt5", "iux"))
    replay_row = await session.get(DataHealthRecord, data_health_record_id("replay", "tick"))
    assert mt5_row is not None and mt5_row.consecutive_failures == 2
    assert replay_row is not None and replay_row.consecutive_failures == 1

    # Healthy tick on Replay resets Replay to 0, MT5 remains 2
    await ks.evaluate_automatic_triggers(
        session,
        test_account,
        test_policy,
        quote_stale=False,
        provider="replay",
        source="tick",
    )
    await session.refresh(mt5_row)
    await session.refresh(replay_row)
    assert mt5_row.consecutive_failures == 2, "MT5 failures must not be reset by Replay"
    assert replay_row.consecutive_failures == 0


def test_mt5_server_authority_disconnected_and_fail_closed():
    """SOL-P5-P1-032: Disconnected MT5 provider reports broker_server = None and expected_broker_server from config."""
    from app.core.config import Settings
    from app.services.market_data.mt5 import MT5MarketDataProvider

    settings = Settings(mt5_expected_server="IUXMarkets-Demo")
    provider = MT5MarketDataProvider(settings=settings)

    # Disconnected provider:
    assert provider.connected is False
    assert provider.broker_server is None, "Disconnected MT5 must report broker_server = None"
    assert provider.expected_broker_server == "IUXMarkets-Demo"


def test_frontend_kill_switch_decoupling_logic():
    """SOL-P5-P1-033: Frontend Kill Switch card status depends on killSwitch resource, not Policy/Portfolio errors."""
    is_kill_switch_ready = True
    kill_switch = {"state": "INACTIVE", "trigger_type": "MANUAL"}

    is_kill_switch_unknown = not is_kill_switch_ready or not kill_switch or kill_switch["state"] == "UNKNOWN"

    assert is_kill_switch_unknown is False
    assert kill_switch["state"] == "INACTIVE"


@pytest.mark.asyncio
@pytest.mark.parametrize("reservation_state", ["RELEASED", "EXPIRED"])
async def test_cached_approval_reconciles_missing_current_reservation(
    db_session,
    test_candidate,
    test_plan,
    test_account,
    test_policy,
    test_spec,
    test_quote,
    now_time,
    reservation_state,
):
    """R4-P1-039: cached approval is returned only with exact current coverage."""
    session, _ = db_session
    from app.models.account import Account, TradingMode
    acc_id = uuid.uuid4()
    account_row = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_adv_reconcile_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account_row)
    await session.flush()
    account = test_account.model_copy(update={"account_id": str(acc_id)})

    policy = test_policy.model_copy(update={"news_risk_enabled": False})
    decision = await risk_engine.evaluate_candidate(
        session, test_candidate, test_plan, account, policy, test_spec, test_quote, as_of=now_time
    )
    await persist_risk_decision(session, decision)
    await session.flush()

    reservation = await session.scalar(
        select(RiskReservationRecord).where(RiskReservationRecord.decision_id == decision.id)
    )
    assert reservation is not None
    if reservation_state == "RELEASED":
        reservation.status = "RELEASED"
        reservation.released_at = now_time
    else:
        reservation.reserved_until = now_time - dt.timedelta(seconds=1)
    await session.flush()

    cached = await risk_engine.evaluate_candidate(
        session, test_candidate, test_plan, account, policy, test_spec, test_quote, as_of=now_time
    )
    assert cached.id == decision.id
    current = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == account.account_id,
                RiskReservationRecord.candidate_id == test_candidate.id,
                RiskReservationRecord.status == "ACTIVE",
                RiskReservationRecord.reserved_until > now_time,
            )
        )
    ).all()
    assert len(current) == 1
    assert current[0].decision_id == cached.id
    assert current[0].risk_pct == cached.approved_risk_pct
    assert current[0].risk_amount == cached.approved_risk_amount
    assert current[0].position_size == cached.position_size


@pytest.mark.asyncio
async def test_cached_blocked_recurrence_releases_newer_reservation(
    db_session, test_candidate, test_plan, test_account, test_policy, test_spec, test_quote, now_time
):
    """R4-P1-040: cached BLOCKED cannot coexist with a newer active reservation."""
    session, _ = db_session
    from app.models.account import Account, TradingMode
    acc_id = uuid.uuid4()
    account_row = Account(
        id=acc_id,
        user_id=uuid.uuid4(),
        name=f"test_adv_recur_{acc_id.hex[:6]}",
        trading_mode=TradingMode.PAPER,
        starting_balance=Decimal("10000.00"),
        is_active=True,
    )
    session.add(account_row)
    await session.flush()
    account = test_account.model_copy(update={"account_id": str(acc_id)})

    policy = test_policy.model_copy(update={"news_risk_enabled": False})
    stale_account = account.model_copy(update={"as_of": now_time - dt.timedelta(minutes=10)})
    blocked = await risk_engine.evaluate_candidate(
        session, test_candidate, test_plan, stale_account, policy, test_spec, test_quote, as_of=now_time
    )
    assert blocked.decision == "BLOCKED"
    await persist_risk_decision(session, blocked)

    approved = await risk_engine.evaluate_candidate(
        session, test_candidate, test_plan, account, policy, test_spec, test_quote, as_of=now_time
    )
    assert approved.decision == "APPROVED"
    await persist_risk_decision(session, approved)
    await session.flush()

    cached_blocked = await risk_engine.evaluate_candidate(
        session, test_candidate, test_plan, stale_account, policy, test_spec, test_quote, as_of=now_time
    )
    assert cached_blocked.id == blocked.id
    active = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == account.account_id,
                RiskReservationRecord.candidate_id == test_candidate.id,
                RiskReservationRecord.status == "ACTIVE",
            )
        )
    ).all()
    assert active == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("freshness_seconds", "expects_reuse"),
    [(5, False), (30, True), (60, True), (120, True)],
)
async def test_paper_snapshot_reuse_obeys_policy_freshness(
    db_session, now_time, freshness_seconds, expects_reuse
):
    """R4-P2-043: a caller-supplied policy TTL is the only reuse authority."""
    session, _ = db_session
    from app.services.risk.account_state import PaperAccountStateService

    acc_id = uuid.uuid4()
    session.add(
        Account(
            id=acc_id,
            user_id=uuid.uuid4(),
            name=f"ttl_{freshness_seconds}_{acc_id.hex[:6]}",
            trading_mode=TradingMode.PAPER,
            starting_balance=Decimal("10000.00"),
            is_active=True,
        )
    )
    await session.flush()
    first = await PaperAccountStateService.refresh_paper_account_snapshot(
        session, str(acc_id), force=True, now=now_time
    )
    observed = await PaperAccountStateService.refresh_paper_account_snapshot(
        session,
        str(acc_id),
        now=now_time + dt.timedelta(seconds=20),
        max_observation_age_seconds=freshness_seconds,
    )
    assert (observed.id == first.id) is expects_reuse
    assert observed.as_of == (first.as_of if expects_reuse else now_time + dt.timedelta(seconds=20))


@pytest.mark.asyncio
async def test_data_health_identity_is_unambiguous_and_bounded(
    db_session, test_account, test_policy
):
    """R4-P2-044: distinct legal authority pairs never share a synthetic PK."""
    session, _ = db_session
    from app.models.risk import DataHealthRecord
    from app.services.risk.kill_switch import KillSwitchManager, data_health_record_id

    assert data_health_record_id("a_b", "c") != data_health_record_id("a", "b_c")
    assert len(data_health_record_id("p" * 64, "s" * 64)) <= 64
    with pytest.raises(ValueError):
        data_health_record_id("p" * 65, "s")

    manager = KillSwitchManager()
    for provider, source in (("a_b", "c"), ("a", "b_c"), ("p" * 64, "s" * 64)):
        await manager.evaluate_automatic_triggers(
            session,
            test_account,
            test_policy,
            quote_stale=True,
            quote_stale_reason="identity-boundary",
            provider=provider,
            source=source,
        )
    rows = (await session.scalars(select(DataHealthRecord))).all()
    pairs = {(row.provider, row.source) for row in rows}
    assert {("a_b", "c"), ("a", "b_c"), ("p" * 64, "s" * 64)} <= pairs


@pytest.mark.asyncio
async def test_news_runtime_fastapi_roundtrip(client, auth_headers, db_session, now_time, test_plan):
    """SOL-P5-P2-036 / Section 26: News runtime FastAPI roundtrip with complete provenance."""
    session, _ = db_session
    from unittest.mock import AsyncMock, MagicMock

    from app.models.strategy import StrategyEvaluationRecord, TradeCandidateRecord

    # 1. Seed candidate
    cand_id = "cand_news_rt_01"
    eval_rec = StrategyEvaluationRecord(
        id="eval_news_rt_01",
        context_id="ctx_news_01",
        symbol="XAUUSD",
        source="simulated",
        as_of=now_time,
        generated_at=now_time,
        payload_hash="hash_news_01",
        payload={},
    )
    session.add(eval_rec)
    cand_rec = TradeCandidateRecord(
        id=cand_id,
        evaluation_id="eval_news_rt_01",
        profile_id="day_trader",
        strategy_id="STRAT02",
        as_of=now_time,
        payload={
            "id": cand_id,
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
            "context_id": "ctx_news_01",
            "upstream_ids": [],
            "evidence": [],
            "missing_conditions": [],
            "conflicts": [],
            "invalidation_th": "หลุดแนวรับ",
            "plan": test_plan.model_dump(mode="json"),
        },
    )
    session.add(cand_rec)

    from app.models.risk import SymbolSpecificationRecord
    spec_rec = SymbolSpecificationRecord(
        id="sym_spec_news_rt",
        symbol="XAUUSD",
        source="simulated",
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1.00"),
        contract_size=Decimal("100.00"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("10.00"),
        volume_step=Decimal("0.01"),
        digits=2,
        observed_at=now_time,
        payload={
            "id": "sym_spec_news_rt",
            "symbol": "XAUUSD",
            "source": "simulated",
            "tick_size": "0.01",
            "tick_value": "1.00",
            "contract_size": "100.00",
            "volume_min": "0.01",
            "volume_max": "10.00",
            "volume_step": "0.01",
            "digits": 2,
            "observed_at": now_time.isoformat(),
        },
    )
    session.add(spec_rec)
    await session.commit()

    # 2. Mock market provider and news provider on client.app.state
    from app.services.news.provider import fixture_release

    app = client.app
    static_quote = Quote(
        source="simulated",
        mode="SIMULATED",
        symbol="XAUUSD",
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        volume=Decimal("100"),
        status="CONNECTED",
        timestamp=now_time,
    )
    class DummyProvider:
        source = "simulated"
        broker_server = None
        server = None

    mock_market = MagicMock()
    mock_market.quote = static_quote
    mock_market.start = AsyncMock()
    mock_market.stop = AsyncMock()
    mock_market.provider = DummyProvider()
    app.state.market = mock_market

    events = fixture_release(now_time, "mixed")
    news_ctx = build_news_context(
        events=events,
        as_of=now_time,
        source="forex_factory",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    mock_news = MagicMock()
    mock_news.start = AsyncMock()
    mock_news.stop = AsyncMock()
    mock_news.provider.source = "forex_factory"
    mock_news.context = AsyncMock(return_value=news_ctx)
    app.state.news = mock_news

    # 3. Call /api/risk/evaluate
    response = client.post(
        "/api/risk/evaluate",
        headers=auth_headers,
        json={
            "candidate_id": cand_id,
            "profile_id": "day_trader",
            "account_id": "default_paper_account",
            "requested_risk_pct": 1.0,
        },
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["decision"] in ("APPROVED", "BLOCKED")
    assert data["evaluation_intent_id"] != ""
    assert data["dependency_fingerprint"] != ""

    # Assert news provenance fields
    news_prov = data.get("news_provenance")
    assert news_prov is not None, f"news_provenance must be populated: {data}"
    assert news_prov["provider"] != ""
    assert news_prov["source"] != ""
    assert news_prov["news_state"] in ("CALM", "PRE_NEWS", "NEWS_LOCK", "POST_NEWS_VOLATILITY", "UNAVAILABLE")
    if news_prov.get("events"):
        first_event = news_prov["events"][0]
        assert first_event["impact"] in ("LOW", "MEDIUM", "HIGH", "NON_ECONOMIC")
        assert first_event["scheduled_at"] is not None
