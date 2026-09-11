"""Phase 5 Risk Engine unit and integration tests.

Verifies:
- All fail-closed gates (Kill switch, stale data, limits)
- News risk separation: Strategy output unchanged, Risk decision independently responds to news
- Multi-trader portfolio risk and directional tracking
- Deterministic Thai explanations
"""

import datetime as dt
from decimal import Decimal

import pytest

from app.services.market_data.domain import Quote
from app.services.risk.domain import (
    AccountSnapshot,
    RiskPolicy,
    default_gold_spec,
)
from app.services.risk.engine import risk_engine
from app.services.risk.kill_switch import kill_switch_manager
from app.services.strategy.domain import (
    Evidence,
    SetupCandidate,
    Target,
    TradePlanSuggestion,
)


@pytest.fixture
def base_time():
    return dt.datetime(2026, 9, 10, 12, 0, 0, tzinfo=dt.UTC)


@pytest.fixture
def spec(base_time):
    return default_gold_spec(source="simulated", observed_at=base_time)


@pytest.fixture
def policy():
    return RiskPolicy()


@pytest.fixture
def account(base_time):
    return AccountSnapshot(
        id="snap_test_001",
        account_id="acc_test_001",
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
        as_of=base_time,
    )


@pytest.fixture
def quote(base_time):
    return Quote(
        symbol="XAUUSD",
        timestamp=base_time,
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        volume=Decimal("100"),
        source="simulated",
        mode="SIMULATED",
        status="CONNECTED",
    )


@pytest.fixture
def plan(base_time):
    return TradePlanSuggestion(
        id="plan_test_001",
        candidate_id="cand_test_001",
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
        as_of=base_time,
        context_id="ctx_001",
        expires_at=base_time + dt.timedelta(hours=2),
    )


@pytest.fixture
def candidate(base_time, plan):
    return SetupCandidate(
        id="cand_test_001",
        profile_id="day_trader",
        strategy_id="STRAT02",
        strategy_version="strategy-1.2.1",
        symbol="XAUUSD",
        direction="LONG",
        status="READY",
        score=85,
        detected_at=base_time - dt.timedelta(minutes=10),
        confirmed_at=base_time,
        expires_at=base_time + dt.timedelta(hours=2),
        context_id="ctx_001",
        upstream_ids=("ctx_001",),
        evidence=(Evidence(code="EV1", description_th="SMC Confirmation"),),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="หลุดแนวรับ 2495.00",
        plan=plan,
    )


@pytest.fixture
def news_context(base_time):
    from app.services.news.domain import NewsConfig
    from app.services.news.engine import build_context as build_news_context

    return build_news_context(
        events=[],
        as_of=base_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )


@pytest.mark.asyncio
async def test_normal_approved_decision(db_session, candidate, plan, account, policy, spec, quote, news_context, base_time):
    session, _ = db_session
    decision = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news_context,
        as_of=base_time,
    )
    assert decision.decision == "APPROVED"
    assert decision.approved_risk_pct == Decimal("1.0000")
    assert decision.position_size > Decimal("0")
    assert decision.direction == "LONG"
    assert decision.execution_blocked == "NO_EXECUTION_ANALYSIS_ONLY"
    assert len(decision.blocked_reasons_th) == 0
    assert any("อนุมัติแผนเทรดตามปกติ" in r for r in decision.reasons_th)


@pytest.mark.asyncio
async def test_kill_switch_blocks_approval(db_session, candidate, plan, account, policy, spec, quote, base_time):
    session, _ = db_session
    # Activate kill switch
    await kill_switch_manager.activate(
        session=session,
        trigger_type="MANUAL",
        reason_th="การซ่อมบำรุงระบบฉุกเฉิน",
        activated_by="test_admin",
    )
    decision = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        as_of=base_time,
    )
    assert decision.decision == "BLOCKED"
    assert decision.approved_risk_pct == Decimal("0.0000")
    assert decision.position_size == Decimal("0.0000")
    assert any("Kill Switch ทำงาน" in r for r in decision.blocked_reasons_th)


@pytest.mark.asyncio
async def test_stale_quote_fails_closed(db_session, candidate, plan, account, policy, spec, quote, base_time):
    session, _ = db_session
    # Quote is 10 seconds old, exceeding 5s freshness policy
    stale_quote = quote.model_copy(update={"timestamp": base_time - dt.timedelta(seconds=10)})
    decision = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=stale_quote,
        as_of=base_time,
    )
    assert decision.decision == "BLOCKED"
    assert any("ราคาตลาดล้าสมัย" in r for r in decision.blocked_reasons_th)


@pytest.mark.asyncio
async def test_spread_exceeds_policy_blocks(db_session, candidate, plan, account, policy, spec, quote, base_time):
    session, _ = db_session
    # Spread is $2.00, exceeding $1.50 policy
    wide_quote = quote.model_copy(
        update={
            "ask": Decimal("2502.00"),
            "spread": Decimal("2.00"),
        }
    )
    decision = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=wide_quote,
        as_of=base_time,
    )
    assert decision.decision == "BLOCKED"
    assert any("ค่าสเปรด" in r and "สูงกว่าเพดาน" in r for r in decision.blocked_reasons_th)


@pytest.mark.asyncio
async def test_daily_loss_limit_blocks(db_session, candidate, plan, account, policy, spec, quote, base_time):
    session, _ = db_session
    # Daily loss = -$350 on $10,000 equity (3.5% loss >= 3.0% limit)
    loss_account = account.model_copy(update={"daily_realized_pnl": Decimal("-350.00")})
    decision = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=loss_account,
        policy=policy,
        spec=spec,
        quote=quote,
        as_of=base_time,
    )
    assert decision.decision == "BLOCKED"
    assert any("ขาดทุนสะสมรายวัน" in r for r in decision.blocked_reasons_th)


@pytest.mark.asyncio
async def test_news_risk_separation_blackout_and_reduction(
    db_session, candidate, plan, account, policy, spec, quote, base_time
):
    session, _ = db_session

    from app.services.news.domain import NewsConfig
    from app.services.news.engine import build_context as build_news_context
    from app.services.news.provider import fixture_release

    # 1. High-impact news event 3 minutes away (within 5m blackout window) -> BLOCKED
    events_3m = fixture_release(base_time + dt.timedelta(minutes=3), "mixed")
    news_ctx_3m = build_news_context(
        events=events_3m,
        as_of=base_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    decision_blackout = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news_ctx_3m,
        as_of=base_time,
    )
    assert decision_blackout.decision == "BLOCKED"
    assert any("Blackout" in r for r in decision_blackout.blocked_reasons_th)

    # 2. High-impact news event 10 minutes away (outside 5m blackout, inside 15m pre-news) -> REDUCED 50%
    events_10m = fixture_release(base_time + dt.timedelta(minutes=10), "mixed")
    news_ctx_10m = build_news_context(
        events=events_10m,
        as_of=base_time,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    decision_reduced = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news_ctx_10m,
        as_of=base_time,
    )
    assert decision_reduced.decision == "REDUCED"
    assert decision_reduced.approved_risk_pct == Decimal("0.5000")  # 1.0% * 0.5 = 0.5%
    assert any("ลดความเสี่ยง" in r for r in decision_reduced.reasons_th + decision_reduced.warnings_th)


@pytest.mark.asyncio
async def test_portfolio_risk_capacity_exceeded(db_session, candidate, plan, account, policy, spec, quote, news_context, base_time):
    session, _ = db_session

    from app.models.risk import RiskReservationRecord

    # Account already has 2.5% reserved risk in DB; max_account_risk_pct = 3.0%
    # Next trade requests 1.0%. Available is 0.5% >= min_risk (0.1%) -> REDUCED to 0.5%!
    r1 = RiskReservationRecord(
        id="res_test_capacity_001",
        decision_id="dec_test_capacity_001",
        account_id=account.account_id,
        profile_id="day_trader",
        symbol="EURUSD",
        direction="SHORT",
        risk_pct=Decimal("2.5000"),
        risk_amount=Decimal("250.00"),
        position_size=Decimal("0.50"),
        status="ACTIVE",
        reserved_at=base_time,
        reserved_until=base_time + dt.timedelta(minutes=10),
    )
    session.add(r1)
    await session.flush()

    decision = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news_context,
        as_of=base_time,
    )
    assert decision.decision == "REDUCED"
    assert decision.approved_risk_pct == Decimal("0.5000")

    # Account already at 2.95% reserved risk (only 0.05% available, < min 0.1%) -> BLOCKED!
    r1.risk_pct = Decimal("2.9500")
    r1.risk_amount = Decimal("295.00")
    await session.flush()

    cand_next = candidate.model_copy(update={"id": "cand_test_002"})
    plan_next = plan.model_copy(update={"id": "plan_test_002", "candidate_id": "cand_test_002"})
    decision_blocked = await risk_engine.evaluate_candidate(
        session=session,
        candidate=cand_next,
        plan=plan_next,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news_context,
        as_of=base_time,
    )
    assert decision_blocked.decision == "BLOCKED"
    assert any("เต็มเพดานสูงสุด" in r or "ไม่เพียงพอ" in r for r in decision_blocked.blocked_reasons_th)
