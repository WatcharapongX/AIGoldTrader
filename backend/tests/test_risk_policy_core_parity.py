"""D2B1 characterization of the live oracle and pure/live semantic parity."""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.services.risk.engine as risk_engine_module
from app.models.risk import KillSwitchRecord, RiskReservationRecord
from app.services.market_data.domain import Quote
from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as build_news_context
from app.services.news.provider import fixture_release
from app.services.risk.domain import AccountSnapshot, RiskPolicy, default_gold_spec
from app.services.risk.engine import risk_engine
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.live_adapter import portfolio_snapshot_from_live
from app.services.risk.policy_core import evaluate_pure_risk, is_pure_cooldown_active
from app.services.risk.policy_domain import (
    DataHealthInputState,
    KillSwitchInputState,
    NewsAvailability,
    PortfolioExposureSnapshot,
    PureDataHealthInput,
    PureKillSwitchInput,
    PureNewsEvent,
    PureNewsState,
    PureQuoteState,
    PureRiskEvaluationInput,
    QuoteAvailability,
    ReservationIntegrityState,
)
from app.services.risk.portfolio import is_cooldown_active, portfolio_manager
from app.services.strategy.domain import Evidence, SetupCandidate, Target, TradePlanSuggestion


@pytest.fixture
def parity_case():
    as_of = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.UTC)
    plan = TradePlanSuggestion(
        id="plan_parity_001",
        candidate_id="cand_parity_001",
        symbol="XAUUSD",
        direction="LONG",
        entry_type="LIMIT_ZONE",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        entry_source_id="h1_fvg",
        stop_loss=Decimal("2495.00"),
        stop_source_id="h1_low",
        invalidation_th="หลุดแนวรับ",
        targets=(
            Target(name="TP1", price=Decimal("2510.00"), source_id="h4", rr=Decimal("1.5")),
            Target(name="TP2", price=Decimal("2520.00"), source_id="d1", rr=Decimal("3.0")),
        ),
        score=85,
        evidence=(Evidence(code="EV1", description_th="ยืนยันโครงสร้าง"),),
        warnings_th=(),
        news_state="CALM",
        status="SUGGESTION_ONLY",
        as_of=as_of,
        context_id="ctx_parity_001",
        expires_at=as_of + dt.timedelta(hours=2),
    )
    candidate = SetupCandidate(
        id="cand_parity_001",
        profile_id="day_trader",
        strategy_id="STRAT02",
        strategy_version="strategy-1.2.1",
        symbol="XAUUSD",
        direction="LONG",
        status="READY",
        score=85,
        detected_at=as_of - dt.timedelta(minutes=10),
        confirmed_at=as_of,
        expires_at=as_of + dt.timedelta(hours=2),
        context_id="ctx_parity_001",
        upstream_ids=("ctx_parity_001",),
        evidence=(Evidence(code="EV1", description_th="ยืนยันโครงสร้าง"),),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="หลุดแนวรับ",
        plan=plan,
    )
    account = AccountSnapshot(
        id="snap_parity_001",
        account_id="acc_parity_001",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        daily_realized_pnl=Decimal("0"),
        weekly_realized_pnl=Decimal("0"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0"),
        reserved_risk_pct=Decimal("0"),
        source="CONFIGURED_TEST",
        as_of=as_of,
    )
    policy = RiskPolicy()
    spec = default_gold_spec(source="simulated", observed_at=as_of)
    quote = Quote(
        symbol="XAUUSD",
        timestamp=as_of,
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        volume=Decimal("100"),
        source="simulated",
        mode="SIMULATED",
        status="CONNECTED",
    )
    calm_news = build_news_context(
        events=[],
        as_of=as_of,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    return as_of, candidate, plan, account, policy, spec, quote, calm_news


def _pure_news(news_context) -> PureNewsState:
    if news_context is None or news_context.calendar_state != "AVAILABLE":
        return PureNewsState(availability=NewsAvailability.UNAVAILABLE)
    events = tuple(
        PureNewsEvent(
            event_id=event.id,
            event_name=event.event_name,
            currency=event.currency,
            impact=event.impact,
            scheduled_at=event.scheduled_at,
            available_at=event.available_at,
            provider=event.source,
            source=event.source,
            revision_id=str(event.revision_version),
            revision_version=event.revision_version,
        )
        for event in news_context.events
    )
    return PureNewsState(
        availability=NewsAvailability.AVAILABLE,
        events=events,
        provider=news_context.source,
        source=news_context.source,
    )


def _pure_input(
    *,
    as_of,
    candidate,
    plan,
    account,
    policy,
    spec,
    quote,
    news_context,
    caller=None,
    lifecycle_status=None,
    reserved=Decimal("0"),
    symbol_risk=Decimal("0"),
    directional_risk=Decimal("0"),
    reservation_count=0,
    integrity=ReservationIntegrityState.OK,
    data_health=DataHealthInputState.HEALTHY,
    kill_switch=KillSwitchInputState.INACTIVE,
    kill_switch_reason="",
):
    pure_quote = (
        PureQuoteState(availability=QuoteAvailability.UNAVAILABLE)
        if quote is None
        else PureQuoteState(
            availability=QuoteAvailability.AVAILABLE,
            timestamp=quote.timestamp,
            bid=quote.bid,
            ask=quote.ask,
            spread=quote.spread,
            source=quote.source,
            mode=quote.mode,
            status=quote.status,
        )
    )
    return PureRiskEvaluationInput(
        as_of=as_of,
        candidate=candidate,
        trade_plan=plan,
        account=account,
        policy=policy,
        symbol_specification=spec,
        quote=pure_quote,
        news=_pure_news(news_context),
        kill_switch=PureKillSwitchInput(state=kill_switch, reason_th=kill_switch_reason),
        data_health=PureDataHealthInput(state=data_health),
        candidate_lifecycle_status=lifecycle_status or candidate.status,
        candidate_transition_count=0,
        caller_requested_risk_pct=caller,
        portfolio=PortfolioExposureSnapshot(
            symbol=candidate.symbol,
            direction=plan.direction,
            open_risk_pct=account.open_risk_pct,
            reserved_risk_pct=reserved,
            symbol_risk_pct=symbol_risk,
            directional_risk_pct=directional_risk,
            active_reservation_count=reservation_count,
            open_position_count=account.open_positions_count,
            reservation_integrity=integrity,
        ),
    )


def _assert_semantic_parity(live, pure):
    assert pure.decision == live.decision
    assert pure.approved_risk_pct == live.approved_risk_pct
    assert pure.approved_risk_amount == live.approved_risk_amount
    assert pure.position_size == live.position_size
    assert pure.stop_distance == live.stop_distance
    assert pure.portfolio_exposure_before == live.portfolio_exposure_before
    assert pure.portfolio_exposure_after == live.portfolio_exposure_after
    assert pure.reasons_th == live.reasons_th
    assert pure.warnings_th == live.warnings_th
    assert pure.blocked_reasons_th == live.blocked_reasons_th
    assert pure.market_provenance == live.market_provenance
    assert pure.news_provenance == live.news_provenance


@pytest.mark.asyncio
@pytest.mark.parametrize("caller", [None, Decimal("0"), Decimal("0.5"), Decimal("1"), Decimal("2")])
async def test_live_pure_approved_and_per_trade_reduction_parity(db_session, parity_case, caller):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        requested_risk_pct=caller,
        as_of=as_of,
    )
    pure = evaluate_pure_risk(
        _pure_input(
            as_of=as_of,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=quote,
            news_context=news,
            caller=caller,
        )
    )
    _assert_semantic_parity(live, pure)


@pytest.mark.asyncio
async def test_live_pure_news_reduction_and_blackout_parity(db_session, parity_case):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, _ = parity_case
    for offset in (10, 3):
        news = build_news_context(
            events=fixture_release(as_of + dt.timedelta(minutes=offset), "mixed"),
            as_of=as_of,
            source="fixture_economic_v1",
            mode="FIXTURE",
            config=NewsConfig(),
            candles=[],
            quotes=[],
            structure=None,
            market_source="simulated",
        )
        live = await risk_engine.evaluate_candidate(
            session=session,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=quote,
            news_context=news,
            as_of=as_of,
        )
        pure = evaluate_pure_risk(
            _pure_input(
                as_of=as_of,
                candidate=candidate,
                plan=plan,
                account=account,
                policy=policy,
                spec=spec,
                quote=quote,
                news_context=news,
            )
        )
        _assert_semantic_parity(live, pure)


@pytest.mark.asyncio
@pytest.mark.parametrize("block_case", ["account_stale", "kill_switch", "capacity", "sizing"])
async def test_d2b1_iv_p3_001_blocked_pre_news_warning_projection_parity(
    db_session,
    parity_case,
    block_case,
):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, _ = parity_case
    news = build_news_context(
        events=fixture_release(as_of + dt.timedelta(minutes=10), "mixed"),
        as_of=as_of,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    reserved = Decimal("0")
    reservation_count = 0
    if block_case == "account_stale":
        account = account.model_copy(update={"as_of": as_of - dt.timedelta(seconds=61)})
    elif block_case == "kill_switch":
        session.add(
            KillSwitchRecord(
                id="ks_pre_news_block",
                state="ACTIVE",
                trigger_type="MANUAL",
                reason_th="ทดสอบการปิดกั้นระหว่างช่วงก่อนข่าว",
                activated_at=as_of,
                activated_by="d2b1_remediation_test",
                policy_version=policy.version,
                payload={"source": "d2b1_remediation_test"},
            )
        )
        await session.flush()
    elif block_case == "capacity":
        await _add_reservation(
            session,
            as_of=as_of,
            account_id=account.account_id,
            suffix="pre_news_capacity",
            risk=Decimal("2.95"),
            symbol="EURUSD",
            direction="SHORT",
        )
        reserved = Decimal("2.95")
        reservation_count = 1
    else:
        plan = TradePlanSuggestion(
            **{
                **plan.model_dump(mode="python"),
                "entry_upper": Decimal("2500"),
                "stop_loss": Decimal("2300"),
            }
        )
        candidate = candidate.model_copy(update={"plan": plan})

    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        as_of=as_of,
    )
    kill_state = await kill_switch_manager.get_state(session)
    pure = evaluate_pure_risk(
        _pure_input(
            as_of=as_of,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=quote,
            news_context=news,
            reserved=reserved,
            reservation_count=reservation_count,
            kill_switch=KillSwitchInputState(kill_state.state),
            kill_switch_reason=kill_state.reason_th if kill_state.state == "ACTIVE" else "",
        )
    )
    _assert_semantic_parity(live, pure)
    assert pure.decision == "BLOCKED"
    assert pure.normalized_requested_risk_pct == Decimal("1.0")
    assert pure.target_risk_pct == Decimal("0.50")
    assert pure.approved_risk_pct == Decimal("0")
    assert pure.warning_codes == ()
    assert pure.warnings_th == ()


@pytest.mark.asyncio
async def test_live_pure_portfolio_reduction_parity(db_session, parity_case):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    session.add(
        RiskReservationRecord(
            id="res_other",
            decision_id="dec_other",
            account_id=account.account_id,
            candidate_id="cand_other",
            profile_id="swing",
            symbol="EURUSD",
            direction="SHORT",
            risk_pct=Decimal("2.5"),
            risk_amount=Decimal("250"),
            position_size=Decimal("0.5"),
            status="ACTIVE",
            reserved_at=as_of,
            reserved_until=as_of + dt.timedelta(minutes=10),
        )
    )
    await session.flush()
    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        as_of=as_of,
    )
    pure = evaluate_pure_risk(
        _pure_input(
            as_of=as_of,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=quote,
            news_context=news,
            reserved=Decimal("2.5"),
            reservation_count=1,
        )
    )
    _assert_semantic_parity(live, pure)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["quote_unavailable", "account_stale", "news_unavailable", "terminal"])
async def test_live_pure_blocked_matrix_parity(db_session, parity_case, case):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    lifecycle = candidate.status
    data_health = DataHealthInputState.HEALTHY
    if case == "quote_unavailable":
        quote = None
        data_health = DataHealthInputState.DEGRADED
    elif case == "account_stale":
        account = account.model_copy(update={"as_of": as_of - dt.timedelta(seconds=61)})
    elif case == "news_unavailable":
        news = None
    else:
        lifecycle = "INVALIDATED"

    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        as_of=as_of,
        candidate_lifecycle_status=lifecycle,
    )
    pure = evaluate_pure_risk(
        _pure_input(
            as_of=as_of,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=quote,
            news_context=news,
            lifecycle_status=lifecycle,
            data_health=data_health,
        )
    )
    _assert_semantic_parity(live, pure)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "quote_stale",
        "spread_high",
        "equity_zero",
        "daily_loss",
        "weekly_loss",
        "drawdown",
        "cooldown",
        "spec_stale",
        "candidate_expired",
        "candidate_superseded",
        "plan_expired",
        "post_news_spread",
    ],
)
async def test_live_pure_extended_gate_parity(db_session, parity_case, case):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    lifecycle = candidate.status
    data_health = DataHealthInputState.HEALTHY
    if case == "quote_stale":
        quote = quote.model_copy(update={"timestamp": as_of - dt.timedelta(seconds=6)})
        data_health = DataHealthInputState.DEGRADED
    elif case == "spread_high":
        quote = quote.model_copy(update={"ask": Decimal("2501.51"), "spread": Decimal("1.51")})
        data_health = DataHealthInputState.DEGRADED
    elif case == "equity_zero":
        account = account.model_copy(update={"equity": Decimal("0")})
    elif case == "daily_loss":
        account = account.model_copy(update={"daily_realized_pnl": Decimal("-300")})
    elif case == "weekly_loss":
        account = account.model_copy(update={"weekly_realized_pnl": Decimal("-600")})
    elif case == "drawdown":
        account = account.model_copy(update={"equity": Decimal("9000"), "peak_equity": Decimal("10000")})
    elif case == "cooldown":
        account = account.model_copy(
            update={
                "consecutive_losses": 3,
                "last_loss_at": as_of,
                "cooldown_until": as_of + dt.timedelta(minutes=60),
            }
        )
    elif case == "spec_stale":
        spec = spec.model_copy(update={"observed_at": as_of - dt.timedelta(seconds=86401)})
    elif case == "candidate_expired":
        lifecycle = "EXPIRED"
    elif case == "candidate_superseded":
        lifecycle = "SUPERSEDED"
    elif case == "post_news_spread":
        quote = quote.model_copy(update={"ask": Decimal("2501.21"), "spread": Decimal("1.21")})
        news = build_news_context(
            events=fixture_release(as_of - dt.timedelta(minutes=1), "mixed"),
            as_of=as_of,
            source="fixture_economic_v1",
            mode="FIXTURE",
            config=NewsConfig(),
            candles=[],
            quotes=[],
            structure=None,
            market_source="simulated",
        )
    elif case == "plan_expired":
        plan = TradePlanSuggestion(
            **{
                **plan.model_dump(mode="python"),
                "as_of": as_of - dt.timedelta(hours=2),
                "expires_at": as_of,
            }
        )
        candidate = candidate.model_copy(update={"plan": plan})

    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        as_of=as_of,
        candidate_lifecycle_status=lifecycle,
    )
    kill_state = await kill_switch_manager.get_state(session)
    pure_input = _pure_input(
        as_of=as_of,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        lifecycle_status=lifecycle,
        data_health=data_health,
        kill_switch=KillSwitchInputState(kill_state.state),
        kill_switch_reason=kill_state.reason_th if kill_state.state == "ACTIVE" else "",
    )
    pure = evaluate_pure_risk(pure_input)
    _assert_semantic_parity(live, pure)


async def _add_reservation(session, *, as_of, account_id, suffix, risk, symbol, direction):
    session.add(
        RiskReservationRecord(
            id=f"res_{suffix}",
            decision_id=f"dec_{suffix}",
            account_id=account_id,
            candidate_id=f"cand_{suffix}",
            profile_id="profile_other",
            symbol=symbol,
            direction=direction,
            risk_pct=risk,
            risk_amount=(risk * Decimal("100")).quantize(Decimal("0.01")),
            position_size=Decimal("0.01"),
            status="ACTIVE",
            reserved_at=as_of,
            reserved_until=as_of + dt.timedelta(minutes=10),
        )
    )
    await session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["account", "symbol", "direction", "concurrent", "open_risk", "sizing"],
)
async def test_live_pure_portfolio_and_sizing_block_parity(db_session, parity_case, case):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    reserved = Decimal("0")
    symbol_risk = Decimal("0")
    directional_risk = Decimal("0")
    count = 0
    if case == "account":
        await _add_reservation(
            session,
            as_of=as_of,
            account_id=account.account_id,
            suffix="account",
            risk=Decimal("2.95"),
            symbol="EURUSD",
            direction="SHORT",
        )
        reserved, count = Decimal("2.95"), 1
    elif case == "symbol":
        await _add_reservation(
            session,
            as_of=as_of,
            account_id=account.account_id,
            suffix="symbol",
            risk=Decimal("1.95"),
            symbol="XAUUSD",
            direction="SHORT",
        )
        reserved, symbol_risk, count = Decimal("1.95"), Decimal("1.95"), 1
    elif case == "direction":
        await _add_reservation(
            session,
            as_of=as_of,
            account_id=account.account_id,
            suffix="direction",
            risk=Decimal("1.95"),
            symbol="EURUSD",
            direction="LONG",
        )
        reserved, directional_risk, count = Decimal("1.95"), Decimal("1.95"), 1
    elif case == "concurrent":
        for index in range(3):
            await _add_reservation(
                session,
                as_of=as_of,
                account_id=account.account_id,
                suffix=f"concurrent_{index}",
                risk=Decimal("0.1"),
                symbol="EURUSD",
                direction="SHORT",
            )
        reserved, count = Decimal("0.3"), 3
    elif case == "open_risk":
        account = account.model_copy(update={"open_risk_pct": Decimal("0.5")})
    elif case == "sizing":
        plan = plan.model_copy(update={"entry_upper": Decimal("2500"), "stop_loss": Decimal("2300")})
        candidate = candidate.model_copy(update={"plan": plan})

    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        as_of=as_of,
    )
    pure_input = _pure_input(
        as_of=as_of,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        reserved=reserved,
        symbol_risk=symbol_risk,
        directional_risk=directional_risk,
        reservation_count=count,
    )
    pure = evaluate_pure_risk(pure_input)
    _assert_semantic_parity(live, pure)


@pytest.mark.asyncio
async def test_duplicate_reservation_anomaly_live_pure_parity(db_session, parity_case, monkeypatch):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    duplicate_rows = [
        SimpleNamespace(
            id=f"res_dup_{index}",
            candidate_id="cand_duplicate",
            risk_pct=Decimal("0.1"),
            symbol="XAUUSD",
            direction="LONG",
        )
        for index in range(2)
    ]

    async def fake_active_reservations(*args, **kwargs):
        return duplicate_rows

    monkeypatch.setattr(portfolio_manager, "get_active_reservations", fake_active_reservations)
    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        as_of=as_of,
    )
    pure = evaluate_pure_risk(
        _pure_input(
            as_of=as_of,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=quote,
            news_context=news,
            reserved=Decimal("0.2"),
            symbol_risk=Decimal("0.2"),
            directional_risk=Decimal("0.2"),
            reservation_count=2,
            integrity=ReservationIntegrityState.OK,
        ).model_copy(
            update={
                "portfolio": PortfolioExposureSnapshot(
                    symbol="XAUUSD",
                    direction="LONG",
                    open_risk_pct=Decimal("0"),
                    reserved_risk_pct=Decimal("0.2"),
                    symbol_risk_pct=Decimal("0.2"),
                    directional_risk_pct=Decimal("0.2"),
                    active_reservation_count=2,
                    open_position_count=0,
                    reservation_integrity=ReservationIntegrityState.DUPLICATE_ACTIVE_RESERVATION,
                    duplicate_candidate_id="cand_duplicate",
                )
            }
        )
    )
    _assert_semantic_parity(live, pure)


@pytest.mark.asyncio
async def test_negative_risk_live_characterization_and_safe_pure_representation(db_session, parity_case):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    live_first = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        requested_risk_pct=Decimal("-0.1"),
        as_of=as_of,
    )
    live_second = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        requested_risk_pct=Decimal("-0.1"),
        as_of=as_of,
    )
    reservations = (
        await session.scalars(
            select(RiskReservationRecord).where(
                RiskReservationRecord.account_id == account.account_id,
                RiskReservationRecord.status == "ACTIVE",
            )
        )
    ).all()
    assert live_first == live_second
    assert live_first.decision == "BLOCKED"
    assert live_first.requested_risk_pct == policy.max_risk_per_trade_pct
    assert live_first.approved_risk_pct == Decimal("0")
    assert live_first.approved_risk_amount == Decimal("0")
    assert live_first.position_size == Decimal("0")
    assert live_first.reasons_th == (
        "ไม่สามารถจัดสรรขนาดสัญญาให้สอดคล้องกับงบความเสี่ยงที่ได้รับการอนุมัติ",
    )
    assert live_first.blocked_reasons_th == ("วงเงินความเสี่ยงหรือยอดเงินในบัญชีต้องมากกว่า 0",)
    assert reservations == []
    assert session.in_transaction()

    pure = evaluate_pure_risk(
        _pure_input(
            as_of=as_of,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=quote,
            news_context=news,
            caller=Decimal("-0.1"),
        )
    )
    assert pure.caller_requested_risk_pct == Decimal("-0.1")
    assert pure.normalized_requested_risk_pct == Decimal("-0.1")
    assert pure.target_risk_pct == Decimal("-0.1")
    assert pure.approved_risk_pct == Decimal("0")
    _assert_semantic_parity(live_first, pure)


@pytest.mark.parametrize(
    "account_updates",
    [
        {"cooldown_until": dt.datetime(2026, 9, 10, 12, 1, tzinfo=dt.UTC)},
        {
            "consecutive_losses": 3,
            "last_loss_at": dt.datetime(2026, 9, 10, 11, 30, tzinfo=dt.UTC),
        },
        {
            "consecutive_losses": 3,
            "last_loss_at": dt.datetime(2026, 9, 10, 10, 0, tzinfo=dt.UTC),
            "cooldown_until": dt.datetime(2026, 9, 10, 11, 0, tzinfo=dt.UTC),
        },
    ],
)
def test_pure_cooldown_matches_existing_function(parity_case, account_updates):
    as_of, _, _, account, policy, _, _, _ = parity_case
    account = account.model_copy(update=account_updates)
    assert is_pure_cooldown_active(account, policy, as_of) == is_cooldown_active(account, policy, as_of)


@pytest.mark.asyncio
async def test_d2b2_live_wrapper_delegates_and_consumes_pure_safety_facts(
    db_session,
    parity_case,
    monkeypatch,
):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    pure_calls = []
    trigger_facts = []
    reservation_lock_flags = []
    original_evaluate = risk_engine_module.evaluate_pure_risk
    original_triggers = kill_switch_manager.evaluate_automatic_triggers
    original_reservations = portfolio_manager.get_active_reservations

    def capture_evaluate(evaluation_input):
        result = original_evaluate(evaluation_input)
        pure_calls.append((evaluation_input, result))
        return result

    async def capture_triggers(*args, **kwargs):
        trigger_facts.append(kwargs.get("safety_trigger_facts"))
        return await original_triggers(*args, **kwargs)

    async def capture_reservations(*args, **kwargs):
        reservation_lock_flags.append(kwargs.get("for_update", False))
        return await original_reservations(*args, **kwargs)

    monkeypatch.setattr(risk_engine_module, "evaluate_pure_risk", capture_evaluate)
    monkeypatch.setattr(kill_switch_manager, "evaluate_automatic_triggers", capture_triggers)
    monkeypatch.setattr(portfolio_manager, "get_active_reservations", capture_reservations)

    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        as_of=as_of,
    )

    assert len(pure_calls) == 2
    assert pure_calls[0][0].kill_switch.state == KillSwitchInputState.UNKNOWN
    assert pure_calls[1][0].kill_switch.state == KillSwitchInputState.INACTIVE
    assert trigger_facts == [pure_calls[0][1].safety_trigger_facts]
    assert reservation_lock_flags == [True]
    _assert_semantic_parity(live, pure_calls[1][1])


def test_d2b2_live_portfolio_adapter_exact_exclusion_and_duplicate_integrity(parity_case):
    _, candidate, plan, account, _, _, _, _ = parity_case
    same = SimpleNamespace(
        id="res_same",
        candidate_id=candidate.id,
        risk_pct=Decimal("0.4"),
        symbol=candidate.symbol,
        direction=plan.direction,
    )
    other = SimpleNamespace(
        id="res_other",
        candidate_id="cand_other",
        risk_pct=Decimal("1.2"),
        symbol="EURUSD",
        direction="SHORT",
    )
    snapshot, legacy_exposure, excluded_id = portfolio_snapshot_from_live(
        account,
        candidate,
        plan,
        [same, other],
    )
    assert excluded_id == same.id
    assert snapshot.reserved_risk_pct == Decimal("1.2")
    assert snapshot.active_reservation_count == 1
    assert snapshot.reservation_integrity == ReservationIntegrityState.OK
    assert legacy_exposure == Decimal("1.2")

    duplicate = SimpleNamespace(
        id="res_same_duplicate",
        candidate_id=candidate.id,
        risk_pct=Decimal("0.4"),
        symbol=candidate.symbol,
        direction=plan.direction,
    )
    snapshot, legacy_exposure, excluded_id = portfolio_snapshot_from_live(
        account,
        candidate,
        plan,
        [same, duplicate, other],
    )
    assert excluded_id is None
    assert snapshot.reserved_risk_pct == Decimal("2.0")
    assert snapshot.reservation_integrity == ReservationIntegrityState.DUPLICATE_ACTIVE_RESERVATION
    assert snapshot.duplicate_candidate_id == candidate.id
    assert legacy_exposure == Decimal("1.2")


@pytest.mark.asyncio
async def test_d2b2_blocked_public_projection_preserves_legacy_requested_risk(
    db_session,
    parity_case,
    monkeypatch,
):
    session, _ = db_session
    as_of, candidate, plan, account, policy, spec, quote, news = parity_case
    final_results = []
    original_evaluate = risk_engine_module.evaluate_pure_risk

    def capture_evaluate(evaluation_input):
        result = original_evaluate(evaluation_input)
        final_results.append(result)
        return result

    monkeypatch.setattr(risk_engine_module, "evaluate_pure_risk", capture_evaluate)
    live = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        requested_risk_pct=Decimal("-0.1"),
        as_of=as_of,
    )

    pure = final_results[-1]
    assert pure.decision == live.decision == "BLOCKED"
    assert pure.caller_requested_risk_pct == Decimal("-0.1")
    assert pure.target_risk_pct == Decimal("-0.1")
    assert live.requested_risk_pct == policy.max_risk_per_trade_pct
    assert live.requested_risk_amount == Decimal("100.00")
    public_payload = live.model_dump(mode="json")
    assert public_payload["approved_risk_pct"] == "0.0000"
    assert public_payload["approved_risk_amount"] == "0.00"
    assert public_payload["position_size"] == "0.0000"
