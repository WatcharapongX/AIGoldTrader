"""Authoritative Phase 2–5 assembly and FastAPI roundtrip probes."""

import asyncio
import copy
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

import app.api.ai as ai_api
from app.core.config import get_settings
from app.models.account import Account
from app.models.risk import AccountSnapshotRecord, RiskDecisionRecord, RiskReservationRecord
from app.models.strategy import StrategyEvaluationRecord, TradeCandidateRecord
from app.services.ai.assembler import AIAnalysisInputAssembler
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import FixtureAIProvider
from app.services.analysis.domain import (
    ALGORITHM_VERSION,
    AnalysisSnapshot,
    DealingRange,
    History,
    LiquidityLevel,
    StructureEvent,
    SwingPoint,
    Zone,
)
from app.services.market_data.domain import Quote, Timeframe
from app.services.market_data.service import MarketService
from app.services.news.domain import NewsStrategyContext, StructureContext
from app.services.strategy.domain import (
    Evidence,
    Frame,
    SetupCandidate,
    StrategyMarketContext,
    Target,
    TradePlanSuggestion,
    compute_trade_plan_fingerprint,
)


def phase3_snapshot(now: dt.datetime, suffix: str) -> AnalysisSnapshot:
    earlier = now - dt.timedelta(minutes=15)
    swing = SwingPoint(
        id=f"swing-{suffix}",
        scope="INTERNAL",
        kind="LOW",
        label="HL",
        price=Decimal("2495.00"),
        swing_time=earlier,
        confirmed_at=now,
    )
    event = StructureEvent(
        id=f"bos-{suffix}",
        scope="INTERNAL",
        kind="BOS",
        direction="BULLISH",
        price=Decimal("2500.00"),
        swing_id=swing.id,
        swing_time=swing.swing_time,
        occurred_at=earlier,
        confirmed_at=now,
        displacement=True,
    )
    liquidity = LiquidityLevel(
        id=f"liq-{suffix}",
        kind="SSL",
        side="LOW",
        price=Decimal("2494.00"),
        created_at=earlier,
        confirmed_at=now,
        source_ids=[swing.id],
    )
    zone = Zone(
        id=f"zone-{suffix}",
        kind="FVG",
        direction="BULLISH",
        lower_bound=Decimal("2498.00"),
        upper_bound=Decimal("2499.00"),
        occurred_at=earlier,
        confirmed_at=now,
        status="OPEN",
        source_event_id=event.id,
    )
    dealing_range = DealingRange(
        lower_bound=Decimal("2490.00"),
        equilibrium=Decimal("2500.00"),
        upper_bound=Decimal("2510.00"),
        origin_time=earlier,
        confirmed_at=now,
        direction="BULLISH",
        swing_ids=[swing.id],
        location="DISCOUNT",
        retracement_62=Decimal("2497.60"),
        retracement_79=Decimal("2494.20"),
    )
    return AnalysisSnapshot(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        source="simulated",
        algorithm_version=ALGORITHM_VERSION,
        config_id=f"analysis-config-{suffix}",
        input_id=f"phase3-input-{suffix}",
        window_start=earlier,
        history=History(requested=300, returned=300, closed=300, status="COMPLETE"),
        as_of=now,
        modules={},
        internal_state="BULLISH",
        external_state="BULLISH",
        swings=[swing],
        events=[event],
        liquidity=[liquidity],
        zones=[zone],
        dealing_range=dealing_range,
        indicators={},
        sessions=[],
        current_sessions=["LONDON"],
        regime="TRENDING_UP",
        confluence_counts={"BULLISH": 3},
    )


def news_context(now: dt.datetime, suffix: str) -> NewsStrategyContext:
    return NewsStrategyContext(
        symbol="XAUUSD",
        as_of=now,
        market_as_of=now,
        config_id=f"news-config-{suffix}",
        fingerprint=f"news-fingerprint-{suffix}",
        source="fixture_news",
        source_mode="FIXTURE",
        calendar_state="AVAILABLE",
        view="none",
        events=[],
        xauusd_relevance={},
        upcoming_events=[],
        active_group=None,
        active_event_id=None,
        news_regime="NORMAL",
        macro_bias="USD_NEUTRAL",
        macro_strength="UNKNOWN",
        multiple_event_risk=False,
        reaction_windows=[],
        reaction_state="NO_EVENT",
        spread_state="SPREAD_NORMAL",
        baseline_spread=Decimal("0.30"),
        current_spread=Decimal("0.30"),
        spread_ratio=Decimal("1.0"),
        volatility_state="NORMAL",
        structure_confirmation=StructureContext(
            status="ALIGNED",
            upstream_input_id=f"phase3-input-{suffix}",
            upstream_config_id=f"analysis-config-{suffix}",
            upstream_algorithm_version=ALGORITHM_VERSION,
            upstream_as_of=now,
            upstream_window_start=now - dt.timedelta(minutes=15),
            references={"bos": f"bos-{suffix}"},
        ),
        trade_policy_state="INFORMATIONAL",
        strategy_eligibility={"STRAT01": "ALLOWED"},
        reason_codes=[],
        market_source="simulated",
        release_status="NO_EVENT",
        data_quality="COMPLETE",
    )


def setup_candidate(now: dt.datetime, suffix: str) -> SetupCandidate:
    candidate_id = f"candidate-{suffix}"
    evidence = Evidence(
        code="BOS_CONFIRMATION",
        description_th="ยืนยันโครงสร้าง BOS",
        source_ids=(f"bos-{suffix}",),
        confirmed_at=now,
        weight=20,
    )
    plan = TradePlanSuggestion(
        id=f"plan-{suffix}",
        candidate_id=candidate_id,
        symbol="XAUUSD",
        direction="LONG",
        entry_type="LIMIT_ZONE",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2501.00"),
        entry_source_id=f"zone-{suffix}",
        stop_loss=Decimal("2495.00"),
        stop_source_id=f"swing-{suffix}",
        invalidation_th="หลุดแนวรับ 2495",
        targets=(
            Target(name="TP1", price=Decimal("2510.00"), source_id="target-1", rr=Decimal("1.5")),
            Target(name="TP2", price=Decimal("2520.00"), source_id="target-2", rr=Decimal("3.0")),
        ),
        score=88,
        evidence=(evidence,),
        warnings_th=(),
        news_state="NORMAL",
        as_of=now,
        context_id=f"strategy-context-{suffix}",
        expires_at=now + dt.timedelta(hours=2),
    )
    return SetupCandidate(
        id=candidate_id,
        profile_id="day_trader",
        strategy_id="STRAT01",
        symbol="XAUUSD",
        direction="LONG",
        status="READY",
        score=88,
        detected_at=now,
        confirmed_at=now,
        expires_at=now + dt.timedelta(hours=2),
        context_id=f"strategy-context-{suffix}",
        upstream_ids=(f"phase3-input-{suffix}",),
        evidence=(evidence,),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="หลุดแนวรับ 2495",
        plan=plan,
    )


async def seed_authoritative_chain(session, account_id: str, now: dt.datetime, suffix: str):
    snapshot = phase3_snapshot(now, suffix)
    news = news_context(now, suffix)
    frame = Frame(
        timeframe=Timeframe.M15,
        input_id=snapshot.input_id,
        config_id=snapshot.config_id,
        algorithm_version=snapshot.algorithm_version,
        window_start=snapshot.window_start,
        as_of=now,
        bars=300,
        requested=300,
        candles_json="[]",
        analysis_json=snapshot.model_dump_json(),
        indicators=(),
        patterns=(),
    )
    market_context = StrategyMarketContext(
        id=f"strategy-context-{suffix}",
        symbol="XAUUSD",
        source="simulated",
        mode="ACTUAL",
        as_of=now,
        config_id=f"strategy-config-{suffix}",
        strategy_config_json="{}",
        analysis_config_json="{}",
        tick_size=Decimal("0.01"),
        frames=(frame,),
        key_levels=(),
        sessions=(),
        current_session="LONDON",
        market_context_id=f"market-context-{suffix}",
        news_json=news.model_dump_json(),
        news_fingerprint=news.fingerprint,
    )
    candidate = setup_candidate(now, suffix)
    evaluation = StrategyEvaluationRecord(
        id=f"evaluation-{suffix}",
        context_id=market_context.id,
        symbol="XAUUSD",
        source="simulated",
        as_of=now,
        generated_at=now,
        payload_hash=f"evaluation-hash-{suffix}",
        payload={"context": market_context.model_dump(mode="json")},
    )
    candidate_record = TradeCandidateRecord(
        id=candidate.id,
        evaluation_id=evaluation.id,
        profile_id=candidate.profile_id,
        strategy_id=candidate.strategy_id,
        as_of=now,
        payload=candidate.model_dump(mode="json"),
    )
    account_snapshot = AccountSnapshotRecord(
        id=f"account-snapshot-{suffix}",
        account_id=account_id,
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        peak_equity=Decimal("10000.00"),
        as_of=now,
        payload={"trade_plan_fingerprint": compute_trade_plan_fingerprint(candidate, candidate.plan)},
    )
    decision = RiskDecisionRecord(
        id=f"decision-{suffix}",
        candidate_id=candidate.id,
        plan_id=candidate.plan.id,
        strategy_id=candidate.strategy_id,
        profile_id=candidate.profile_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        decision="APPROVED",
        requested_risk_pct=Decimal("1.0000"),
        approved_risk_pct=Decimal("1.0000"),
        requested_risk_amount=Decimal("100.00"),
        approved_risk_amount=Decimal("100.00"),
        position_size=Decimal("0.1400"),
        entry_lower=candidate.plan.entry_lower,
        entry_upper=candidate.plan.entry_upper,
        stop_loss=candidate.plan.stop_loss,
        stop_distance=Decimal("5.00"),
        account_id=account_id,
        account_snapshot_id=account_snapshot.id,
        policy_version="risk-policy-1.0.0",
        dependency_fingerprint=f"risk-dependency-{suffix}",
        as_of=now,
        expires_at=now + dt.timedelta(minutes=15),
        payload={
            "account_id": account_id,
            "trade_plan_fingerprint": compute_trade_plan_fingerprint(candidate, candidate.plan),
        },
    )
    reservation = RiskReservationRecord(
        id=f"reservation-{suffix}",
        decision_id=decision.id,
        account_id=account_id,
        candidate_id=candidate.id,
        profile_id=candidate.profile_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        risk_pct=decision.approved_risk_pct,
        risk_amount=decision.approved_risk_amount,
        position_size=decision.position_size,
        status="ACTIVE",
        reserved_at=now,
        reserved_until=now + dt.timedelta(minutes=15),
    )
    session.add_all([evaluation, candidate_record, account_snapshot, decision, reservation])
    await session.commit()
    return snapshot, news, candidate, decision, reservation


class RecordingOrchestrator:
    def __init__(self):
        self.inputs = []
        self.provider = FixtureAIProvider()
        self.actual = AIOrchestrator()

    async def analyze(self, ai_input):
        self.inputs.append(ai_input)
        return await self.actual.analyze(ai_input)


@pytest.mark.asyncio
async def test_actual_fastapi_authoritative_roundtrip_and_stable_fingerprint(
    client,
    auth_headers,
    db_session,
    monkeypatch,
) -> None:
    session, factory = db_session
    account = await session.scalar(select(Account).where(Account.name == "default_paper_account"))
    assert account is not None
    now = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    snapshot, news, candidate, decision, reservation = await seed_authoritative_chain(
        session,
        str(account.id),
        now,
        "api",
    )

    real_market = MarketService(factory, get_settings())
    real_market.quote = Quote(
        symbol="XAUUSD",
        timestamp=now,
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        volume=Decimal("1"),
        source="simulated",
        mode="SIMULATED",
        spread=Decimal("0.30"),
        status="CONNECTED",
    )

    async def keep_injected_quote() -> None:
        return None

    monkeypatch.setattr(real_market, "start", keep_injected_quote)
    client.app.state.market = real_market
    recorder = RecordingOrchestrator()
    monkeypatch.setattr(ai_api, "ai_orchestrator", recorder)

    body = {"candidate_id": candidate.id, "account_id": str(account.id)}
    first = client.post("/api/ai-analysis/evaluate", headers=auth_headers, json=body)
    await asyncio.sleep(0.1)
    second = client.post("/api/ai-analysis/evaluate", headers=auth_headers, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "READY"
    assert len(recorder.inputs) == 2

    assembled = recorder.inputs[0]
    assert assembled.quote_context.model_dump(mode="json") == {
        "availability": "AVAILABLE",
        "symbol": "XAUUSD",
        "bid": "2500.00",
        "ask": "2500.30",
        "spread": "0.30",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "is_stale": False,
        "source": "simulated",
        "unavailable_reason": "",
    }
    assert assembled.structure_context.context_id == snapshot.input_id
    assert assembled.structure_context.algorithm_version == snapshot.algorithm_version
    assert assembled.structure_context.events[0].confirmed_at == snapshot.events[0].confirmed_at
    assert assembled.news_context.source == news.source
    assert assembled.news_context.context_fingerprint == news.fingerprint
    assert assembled.strategy_context.candidate_id == candidate.id
    assert assembled.strategy_context.direction == candidate.direction
    assert assembled.trade_plan_context.plan_id == candidate.plan.id
    assert assembled.risk_context.decision_id == decision.id
    assert assembled.risk_context.account_id == str(account.id)
    assert assembled.risk_context.reservation_id == reservation.id
    assert assembled.risk_context.reservation_status == "ACTIVE"
    assert assembled.kill_switch_context.state == "INACTIVE"
    assert assembled.provenance.market_source == "simulated"
    assert assembled.provenance.news_provider == news.source
    assert assembled.input_fingerprint == recorder.inputs[1].input_fingerprint
    assert assembled.analysis_requested_at != recorder.inputs[1].analysis_requested_at


@pytest.mark.asyncio
async def test_account_bound_query_selects_older_correct_decision_before_limit(
    db_session,
    admin_user,
) -> None:
    session, _ = db_session
    account_a = await session.scalar(select(Account).where(Account.name == "default_paper_account"))
    assert account_a is not None
    account_b = Account(
        name="round2_account_b",
        user_id=admin_user.id,
        trading_mode="PAPER",
        starting_balance=10000.0,
        base_currency="USD",
        is_active=True,
    )
    session.add(account_b)
    await session.commit()

    now = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    _, _, candidate, decision_a, _ = await seed_authoritative_chain(session, str(account_a.id), now, "account")
    snapshot_b = AccountSnapshotRecord(
        id="account-snapshot-newer-b",
        account_id=str(account_b.id),
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        peak_equity=Decimal("10000.00"),
        as_of=now + dt.timedelta(milliseconds=500),
        payload={},
    )
    decision_b = RiskDecisionRecord(
        id="decision-newer-b",
        candidate_id=candidate.id,
        plan_id=candidate.plan.id,
        strategy_id=candidate.strategy_id,
        profile_id=candidate.profile_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        decision="APPROVED",
        requested_risk_pct=Decimal("0.5000"),
        approved_risk_pct=Decimal("0.5000"),
        requested_risk_amount=Decimal("50.00"),
        approved_risk_amount=Decimal("50.00"),
        position_size=Decimal("0.0700"),
        entry_lower=candidate.plan.entry_lower,
        entry_upper=candidate.plan.entry_upper,
        stop_loss=candidate.plan.stop_loss,
        stop_distance=Decimal("5.00"),
        account_id=str(account_b.id),
        account_snapshot_id=snapshot_b.id,
        policy_version="risk-policy-1.0.0",
        dependency_fingerprint="risk-dependency-newer-b",
        as_of=now + dt.timedelta(milliseconds=500),
        expires_at=now + dt.timedelta(minutes=15),
        payload={"account_id": str(account_b.id)},
    )
    reservation_b = RiskReservationRecord(
        id="reservation-newer-b",
        decision_id=decision_b.id,
        account_id=str(account_b.id),
        candidate_id=candidate.id,
        profile_id=candidate.profile_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        risk_pct=decision_b.approved_risk_pct,
        risk_amount=decision_b.approved_risk_amount,
        position_size=decision_b.position_size,
        status="ACTIVE",
        reserved_at=now,
        reserved_until=now + dt.timedelta(minutes=15),
    )
    session.add_all([snapshot_b, decision_b, reservation_b])
    await session.commit()

    assembled_a = await AIAnalysisInputAssembler.assemble(
        session,
        candidate_id=candidate.id,
        account_id=str(account_a.id),
        current_user=admin_user,
    )
    assembled_b = await AIAnalysisInputAssembler.assemble(
        session,
        candidate_id=candidate.id,
        account_id=str(account_b.id),
        current_user=admin_user,
    )
    assert assembled_a.risk_context.decision_id == decision_a.id
    assert assembled_a.risk_context.approved_risk_amount == Decimal("100.00")
    assert assembled_b.risk_context.decision_id == decision_b.id
    assert assembled_b.risk_context.approved_risk_amount == Decimal("50.00")
    no_market_provider = FixtureAIProvider()
    no_market_result = await AIOrchestrator(provider=no_market_provider.to_descriptor()).analyze(assembled_a)
    assert assembled_a.quote_context.availability == "UNAVAILABLE"
    assert no_market_result.status == "BLOCKED_BY_UPSTREAM"
    assert no_market_provider.call_history == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("account_id", "wrong-account"),
        ("candidate_id", "wrong-candidate"),
        ("profile_id", "wrong-profile"),
        ("symbol", "EURUSD"),
        ("direction", "SHORT"),
        ("risk_pct", Decimal("0.9999")),
        ("risk_amount", Decimal("99.99")),
        ("position_size", Decimal("0.1300")),
    ],
)
async def test_every_reservation_semantic_mismatch_blocks_provider(
    db_session,
    admin_user,
    field: str,
    bad_value,
) -> None:
    session, _ = db_session
    account = await session.scalar(select(Account).where(Account.name == "default_paper_account"))
    assert account is not None
    now = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    _, _, candidate, _, reservation = await seed_authoritative_chain(
        session,
        str(account.id),
        now,
        f"mismatch-{field}",
    )
    setattr(reservation, field, bad_value)
    await session.commit()

    assembled = await AIAnalysisInputAssembler.assemble(
        session,
        candidate_id=candidate.id,
        account_id=str(account.id),
        current_user=admin_user,
    )
    provider = FixtureAIProvider()
    result = await AIOrchestrator(provider=provider.to_descriptor()).analyze(assembled)
    assert assembled.risk_context.reservation_status == "MISMATCHED"
    assert result.status == "BLOCKED_BY_UPSTREAM"
    assert provider.call_history == []


_TRADE_PLAN_MUTATIONS = (
    "plan_id",
    "direction",
    "entry_lower",
    "entry_upper",
    "entry_source",
    "stop_loss",
    "stop_source",
    "invalidation",
    "tp1",
    "tp2",
    "target_rr",
    "target_order_identity",
    "score",
    "evidence",
    "warnings",
    "news_state",
    "context_id",
    "as_of",
    "expiry",
)


def mutate_trade_plan_payload(payload: dict, mutation: str, now: dt.datetime) -> dict:
    mutated = copy.deepcopy(payload)
    plan = mutated["plan"]
    if mutation == "plan_id":
        plan["id"] = "plan-reused-with-new-meaning"
    elif mutation == "direction":
        plan["direction"] = "SHORT"
        plan["stop_loss"] = "2502.00"
        plan["targets"][0]["price"] = "2490.00"
        plan["targets"][1]["price"] = "2480.00"
    elif mutation == "entry_lower":
        plan["entry_lower"] = "2499.50"
    elif mutation == "entry_upper":
        plan["entry_upper"] = "2501.50"
    elif mutation == "entry_source":
        plan["entry_source_id"] = "zone-revised"
    elif mutation == "stop_loss":
        plan["stop_loss"] = "2494.00"
    elif mutation == "stop_source":
        plan["stop_source_id"] = "swing-revised"
    elif mutation == "invalidation":
        plan["invalidation_th"] = "ยกเลิกเมื่อโครงสร้างใหม่เสีย"
    elif mutation == "tp1":
        plan["targets"][0]["price"] = "2511.00"
    elif mutation == "tp2":
        plan["targets"][1]["price"] = "2521.00"
    elif mutation == "target_rr":
        plan["targets"][0]["rr"] = "1.6"
    elif mutation == "target_order_identity":
        first, second = plan["targets"]
        first["name"], second["name"] = second["name"], first["name"]
        first["source_id"], second["source_id"] = second["source_id"], first["source_id"]
    elif mutation == "score":
        plan["score"] = 87
    elif mutation == "evidence":
        plan["evidence"][0]["description_th"] = "หลักฐานแผนถูกแก้ไข"
    elif mutation == "warnings":
        plan["warnings_th"] = ["คำเตือนใหม่"]
    elif mutation == "news_state":
        plan["news_state"] = "ELEVATED"
    elif mutation == "context_id":
        plan["context_id"] = "strategy-context-revised"
    elif mutation == "as_of":
        plan["as_of"] = (now - dt.timedelta(seconds=1)).isoformat()
    elif mutation == "expiry":
        plan["expires_at"] = (now + dt.timedelta(hours=3)).isoformat()
    else:  # pragma: no cover - the parameter matrix is exhaustive
        raise AssertionError(f"Unknown mutation: {mutation}")
    return mutated


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", _TRADE_PLAN_MUTATIONS)
async def test_any_trade_plan_mutation_invalidates_prior_risk_authority(
    client,
    auth_headers,
    db_session,
    monkeypatch,
    mutation: str,
) -> None:
    session, factory = db_session
    account = await session.scalar(select(Account).where(Account.name == "default_paper_account"))
    assert account is not None
    now = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    _, _, candidate, _, _ = await seed_authoritative_chain(
        session, str(account.id), now, f"plan-binding-{mutation}"
    )

    candidate_row = await session.get(TradeCandidateRecord, candidate.id)
    assert candidate_row is not None
    candidate_row.payload = mutate_trade_plan_payload(candidate_row.payload, mutation, now)
    await session.commit()

    market = MarketService(factory, get_settings())
    market.quote = Quote(
        symbol="XAUUSD", timestamp=dt.datetime.now(dt.UTC), bid=Decimal("2500.00"),
        ask=Decimal("2500.30"), volume=Decimal("1"), source="simulated",
        mode="SIMULATED", spread=Decimal("0.30"), status="CONNECTED",
    )

    async def keep_injected_quote() -> None:
        return None

    monkeypatch.setattr(market, "start", keep_injected_quote)
    client.app.state.market = market
    recorder = RecordingOrchestrator()
    monkeypatch.setattr(ai_api, "ai_orchestrator", recorder)
    response = client.post(
        "/api/ai-analysis/evaluate", headers=auth_headers,
        json={"candidate_id": candidate.id, "account_id": str(account.id)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "BLOCKED_BY_UPSTREAM"
    assert recorder.inputs[0].risk_context.reservation_status == "MISMATCHED"
    assert recorder.provider.call_history == []


@pytest.mark.asyncio
async def test_legacy_risk_decision_without_plan_fingerprint_fails_closed(
    client,
    auth_headers,
    db_session,
    monkeypatch,
) -> None:
    session, factory = db_session
    account = await session.scalar(select(Account).where(Account.name == "default_paper_account"))
    assert account is not None
    now = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    _, _, candidate, decision, _ = await seed_authoritative_chain(
        session, str(account.id), now, "legacy-missing-plan-binding"
    )
    decision.payload = {}
    await session.commit()

    market = MarketService(factory, get_settings())
    market.quote = Quote(
        symbol="XAUUSD", timestamp=dt.datetime.now(dt.UTC), bid=Decimal("2500.00"),
        ask=Decimal("2500.30"), volume=Decimal("1"), source="simulated",
        mode="SIMULATED", spread=Decimal("0.30"), status="CONNECTED",
    )

    async def keep_injected_quote() -> None:
        return None

    monkeypatch.setattr(market, "start", keep_injected_quote)
    client.app.state.market = market
    recorder = RecordingOrchestrator()
    monkeypatch.setattr(ai_api, "ai_orchestrator", recorder)
    response = client.post(
        "/api/ai-analysis/evaluate", headers=auth_headers,
        json={"candidate_id": candidate.id, "account_id": str(account.id)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "BLOCKED_BY_UPSTREAM"
    assert recorder.inputs[0].risk_context.reservation_status == "MISMATCHED"
    assert recorder.provider.call_history == []
