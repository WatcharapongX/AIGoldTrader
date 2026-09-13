"""Independent reproductions for the Phase 6.1 round-two safety findings."""

import asyncio
import datetime as dt
import json
import time
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ValidationError as AppValidationError
from app.services.ai.agents import MacroNewsAnalyst, TradeThesisAgent
from app.services.ai.assembler import AIAnalysisInputAssembler, _provider_source
from app.services.ai.domain import (
    AIAnalysisInput,
    AIKillSwitchContext,
    AILiquidityEvidence,
    AIMarketQuoteContext,
    AIMarketStructureContext,
    AINewsContext,
    AINewsEventContext,
    AIProvenance,
    AIRiskDecisionContext,
    AIStrategyContext,
    AIStrategyEvidence,
    AIStructureEvent,
    AISwingEvidence,
    AITradePlanContext,
    AIZoneEvidence,
    compute_semantic_input_fingerprint,
)
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import AIProvider, FixtureAIProvider, ModelConfig, ProviderResult
from app.services.market_data.domain import Quote
from app.services.market_data.provider import ReplayProvider


def authoritative_input(*, direction: str = "LONG", strategy_id: str = "STRAT01") -> AIAnalysisInput:
    now = dt.datetime.now(dt.UTC)
    quote = AIMarketQuoteContext(
        symbol="XAUUSD",
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        timestamp=now,
        source="simulated",
    )
    structure = AIMarketStructureContext(
        symbol="XAUUSD",
        timeframe="M15",
        as_of=now,
        source="simulated",
        context_id="phase3-input-01",
        algorithm_version="structure-1.0.0",
        internal_state="BULLISH",
        external_state="BULLISH",
        regime="TRENDING_UP",
        current_sessions=("LONDON",),
    )
    news = AINewsContext(
        news_state="CALM",
        as_of=now,
        source="fixture_news",
        revision_version=1,
        context_fingerprint="news-vintage-01",
    )
    strategy = AIStrategyContext(
        candidate_id="candidate-01",
        strategy_id=strategy_id,
        strategy_version="strategy-1.0.0",
        profile_id="day_trader",
        symbol="XAUUSD",
        direction=direction,
        score=85,
        detected_at=now,
        confirmed_at=now,
        status="READY",
    )
    plan = AITradePlanContext(
        plan_id="plan-01",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2501.00"),
        stop_loss=Decimal("2495.00"),
        take_profit_1=Decimal("2510.00"),
        take_profit_2=Decimal("2520.00"),
        risk_reward_ratio=Decimal("2.0"),
        invalidation_th="หลุดแนวรับ",
        as_of=now,
        expires_at=now + dt.timedelta(hours=2),
    )
    risk = AIRiskDecisionContext(
        decision_id="decision-01",
        decision="APPROVED",
        account_id="account-01",
        profile_id="day_trader",
        requested_risk_pct=Decimal("1.0000"),
        approved_risk_pct=Decimal("1.0000"),
        requested_risk_amount=Decimal("100.00"),
        approved_risk_amount=Decimal("100.00"),
        position_size=Decimal("0.1400"),
        policy_version="risk-policy-1.0.0",
        as_of=now,
        expires_at=now + dt.timedelta(minutes=15),
        reservation_id="reservation-01",
        reservation_status="ACTIVE",
    )
    kill_switch = AIKillSwitchContext(
        record_id="kill-switch-01",
        state="INACTIVE",
        trigger_type="NONE",
        cleared_at=now - dt.timedelta(minutes=1),
    )
    provenance = AIProvenance(
        market_source="simulated",
        market_context_id="market-context-01",
        structure_context_id="phase3-input-01",
        news_provider="fixture_news",
        news_revision="1",
        strategy_candidate_id="candidate-01",
        strategy_evaluation_id="evaluation-01",
        trade_plan_id="plan-01",
        risk_decision_id="decision-01",
        risk_reservation_id="reservation-01",
        kill_switch_record_id="kill-switch-01",
        kill_switch_as_of=kill_switch.cleared_at,
    )
    input_fingerprint = compute_semantic_input_fingerprint(
        symbol="XAUUSD",
        account_id="account-01",
        profile_id="day_trader",
        as_of=now,
        quote_context=quote,
        structure_context=structure,
        news_context=news,
        strategy_context=strategy,
        trade_plan_context=plan,
        risk_context=risk,
        kill_switch_context=kill_switch,
        provenance=provenance,
    )
    return AIAnalysisInput(
        analysis_id="analysis-01",
        trace_id="trace-01",
        analysis_requested_at=now,
        as_of=now,
        symbol="XAUUSD",
        account_id="account-01",
        profile_id="day_trader",
        quote_context=quote,
        structure_context=structure,
        news_context=news,
        strategy_context=strategy,
        trade_plan_context=plan,
        risk_context=risk,
        kill_switch_context=kill_switch,
        provenance=provenance,
        input_versions=(("ai_version", "ai-1.0.0"),),
        input_fingerprint=input_fingerprint,
    )


def semantic_fingerprint(ai_input: AIAnalysisInput, **updates: object) -> str:
    contexts = {
        "quote_context": ai_input.quote_context,
        "structure_context": ai_input.structure_context,
        "news_context": ai_input.news_context,
        "strategy_context": ai_input.strategy_context,
        "trade_plan_context": ai_input.trade_plan_context,
        "risk_context": ai_input.risk_context,
        "kill_switch_context": ai_input.kill_switch_context,
        "provenance": ai_input.provenance,
    }
    contexts.update(updates)
    return compute_semantic_input_fingerprint(
        symbol=ai_input.symbol,
        account_id=ai_input.account_id,
        profile_id=ai_input.profile_id,
        as_of=ai_input.as_of,
        **contexts,  # type: ignore[arg-type]
    )


def test_authority_contracts_reject_plausible_defaults() -> None:
    now = dt.datetime.now(dt.UTC)
    with pytest.raises(PydanticValidationError):
        AIMarketQuoteContext(
            symbol="XAUUSD",
            bid=Decimal("0"),
            ask=Decimal("0"),
            spread=Decimal("0"),
            timestamp=now,
            source="context_snapshot",
        )
    with pytest.raises(PydanticValidationError):
        AIMarketStructureContext(
            symbol="XAUUSD",
            timeframe="M15",
            as_of=now,
            internal_state="UNKNOWN",
            external_state="UNKNOWN",
            regime="UNKNOWN",
        )
    with pytest.raises(PydanticValidationError):
        AINewsContext(news_state="CALM", as_of=now)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["quote", "structure"])
async def test_required_authority_missing_blocks_before_provider(missing: str) -> None:
    ai_input = authoritative_input()
    if missing == "quote":
        replacement = AIMarketQuoteContext(
            availability="UNAVAILABLE",
            symbol="XAUUSD",
            unavailable_reason="No observed quote",
        )
        ai_input = ai_input.model_copy(update={"quote_context": replacement})
    else:
        replacement = AIMarketStructureContext(
            availability="UNAVAILABLE",
            symbol="XAUUSD",
            unavailable_reason="No Phase 3 snapshot",
        )
        ai_input = ai_input.model_copy(update={"structure_context": replacement})

    provider = FixtureAIProvider()
    result = await AIOrchestrator(provider=provider).analyze(ai_input)
    assert result.status == "BLOCKED_BY_UPSTREAM"
    assert provider.call_history == []


@pytest.mark.asyncio
async def test_news_unavailable_is_optional_only_for_strat01_to_04() -> None:
    missing_news = AINewsContext(availability="UNAVAILABLE", unavailable_reason="calendar unavailable")

    optional_input = authoritative_input(strategy_id="STRAT01").model_copy(update={"news_context": missing_news})
    optional_provider = FixtureAIProvider()
    optional_result = await AIOrchestrator(provider=optional_provider).analyze(optional_input)
    assert optional_result.status == "PARTIAL"
    assert optional_result.agent_results["macro_news"].status == "UNAVAILABLE"
    assert "macro_news" not in {str(call["agent_id"]) for call in optional_provider.call_history}
    assert optional_input.strategy_context.direction == "LONG"

    required_input = authoritative_input(strategy_id="STRAT05").model_copy(update={"news_context": missing_news})
    required_provider = FixtureAIProvider()
    required_result = await AIOrchestrator(provider=required_provider).analyze(required_input)
    assert required_result.status == "BLOCKED_BY_UPSTREAM"
    assert required_provider.call_history == []


def test_real_replay_provider_object_source_adapter() -> None:
    now = dt.datetime.now(dt.UTC)
    provider = ReplayProvider()
    quote = Quote(
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
    assert _provider_source(provider, quote) == "simulated"
    assert quote.timestamp == now


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("swings", lambda future: (AISwingEvidence(swing_time=future),)),
        (
            "events",
            lambda future: (
                AIStructureEvent(kind="BOS", swing_time=future - dt.timedelta(seconds=1), confirmed_at=future),
            ),
        ),
        ("liquidity", lambda future: (AILiquidityEvidence(confirmed_at=future),)),
        ("zones", lambda future: (AIZoneEvidence(kind="FVG", confirmed_at=future),)),
    ],
)
def test_actual_phase3_temporal_fields_block_lookahead(field: str, replacement) -> None:
    ai_input = authoritative_input()
    future = ai_input.as_of + dt.timedelta(seconds=1)
    structure = ai_input.structure_context.model_copy(update={field: replacement(future)})
    with pytest.raises(ValueError, match="No-lookahead violation"):
        AIOrchestrator.validate_no_lookahead(ai_input.model_copy(update={"structure_context": structure}))


def test_news_revision_strategy_and_plan_temporal_fields_block_lookahead() -> None:
    ai_input = authoritative_input()
    future = ai_input.as_of + dt.timedelta(seconds=1)
    event = AINewsEventContext(
        id="news-01",
        title="CPI",
        currency="USD",
        impact="HIGH",
        scheduled_at=future,
        available_at=future,
        updated_at=future,
        revision_version=2,
    )
    news = ai_input.news_context.model_copy(update={"events": (event,), "event_ids": (event.id,)})
    with pytest.raises(ValueError, match="No-lookahead violation"):
        AIOrchestrator.validate_no_lookahead(ai_input.model_copy(update={"news_context": news}))

    evidence = AIStrategyEvidence(kind="EV1", confirmed_at=future)
    strategy = ai_input.strategy_context.model_copy(update={"evidence": (evidence,)})
    with pytest.raises(ValueError, match="No-lookahead violation"):
        AIOrchestrator.validate_no_lookahead(ai_input.model_copy(update={"strategy_context": strategy}))

    plan = ai_input.trade_plan_context.model_copy(update={"created_at": future})
    with pytest.raises(ValueError, match="No-lookahead violation"):
        AIOrchestrator.validate_no_lookahead(ai_input.model_copy(update={"trade_plan_context": plan}))


def test_news_vintage_relationships_and_malformed_timestamps_fail_closed() -> None:
    now = dt.datetime.now(dt.UTC)
    with pytest.raises(PydanticValidationError):
        AINewsEventContext(
            id="news-bad-time",
            title="CPI",
            currency="USD",
            impact="HIGH",
            scheduled_at=now,
            available_at=now,
            updated_at="not-a-timestamp",
        )
    with pytest.raises(PydanticValidationError, match="visible before"):
        AINewsEventContext(
            id="news-bad-vintage",
            title="CPI",
            currency="USD",
            impact="HIGH",
            scheduled_at=now,
            available_at=now,
            updated_at=now + dt.timedelta(seconds=1),
        )


@pytest.mark.parametrize(
    ("evidence_type", "field"),
    [
        (AISwingEvidence, "confirmed_at"),
        (AIStructureEvent, "confirmed_at"),
        (AILiquidityEvidence, "confirmed_at"),
        (AIZoneEvidence, "confirmed_at"),
        (AIStrategyEvidence, "confirmed_at"),
    ],
)
def test_malformed_actual_evidence_clocks_fail_typed_validation(evidence_type, field: str) -> None:
    with pytest.raises(PydanticValidationError):
        evidence_type.model_validate({"id": "malformed-clock", field: "not-a-timestamp"})


@pytest.mark.parametrize(
    "evidence_type",
    [AIStructureEvent, AILiquidityEvidence, AIZoneEvidence, AIStrategyEvidence],
)
def test_evidence_is_deeply_immutable_and_detached_from_source(evidence_type) -> None:
    now = dt.datetime.now(dt.UTC)
    source = {
        "id": "evidence-01",
        "kind": "BOS",
        "confirmed_at": now.isoformat(),
        "details": {"levels": ["2500.00"]},
    }
    if evidence_type is AIStructureEvent:
        source["swing_time"] = (now - dt.timedelta(minutes=1)).isoformat()
    evidence = evidence_type.model_validate(source)
    captured = evidence.data_json
    source["details"]["levels"].append("9999.00")
    assert evidence.data_json == captured
    assert "9999.00" not in evidence.data_json
    with pytest.raises(PydanticValidationError):
        evidence.kind = "MUTATED"


def test_fingerprint_ignores_request_clock_and_tracks_every_authority_dependency() -> None:
    ai_input = authoritative_input()
    baseline = semantic_fingerprint(ai_input)
    later_clock = compute_semantic_input_fingerprint(
        symbol=ai_input.symbol,
        account_id=ai_input.account_id,
        profile_id=ai_input.profile_id,
        as_of=ai_input.as_of + dt.timedelta(milliseconds=500),
        quote_context=ai_input.quote_context,
        structure_context=ai_input.structure_context,
        news_context=ai_input.news_context,
        strategy_context=ai_input.strategy_context,
        trade_plan_context=ai_input.trade_plan_context,
        risk_context=ai_input.risk_context,
        kill_switch_context=ai_input.kill_switch_context,
        provenance=ai_input.provenance,
    )
    assert later_clock == baseline

    mutations = (
        {
            "quote_context": ai_input.quote_context.model_copy(
                update={"bid": Decimal("2501.00"), "ask": Decimal("2501.30")}
            )
        },
        {"structure_context": ai_input.structure_context.model_copy(update={"context_id": "phase3-input-02"})},
        {
            "news_context": ai_input.news_context.model_copy(
                update={"revision_version": 2, "context_fingerprint": "news-vintage-02"}
            )
        },
        {"strategy_context": ai_input.strategy_context.model_copy(update={"candidate_id": "candidate-02"})},
        {
            "trade_plan_context": ai_input.trade_plan_context.model_copy(
                update={"plan_id": "plan-02", "entry_lower": Decimal("2500.10")}
            )
        },
        {"risk_context": ai_input.risk_context.model_copy(update={"decision_id": "decision-02"})},
        {"risk_context": ai_input.risk_context.model_copy(update={"reservation_id": "reservation-02"})},
        {
            "kill_switch_context": ai_input.kill_switch_context.model_copy(
                update={"record_id": "kill-switch-02", "policy_version": "risk-policy-1.0.1"}
            )
        },
    )
    assert all(semantic_fingerprint(ai_input, **mutation) != baseline for mutation in mutations)


@pytest.mark.asyncio
async def test_historical_as_of_is_rejected_explicitly(db_session, admin_user) -> None:
    session, _ = db_session
    with pytest.raises(AppValidationError, match="current-only"):
        await AIAnalysisInputAssembler.assemble(
            session,
            candidate_id="irrelevant",
            account_id="irrelevant",
            current_user=admin_user,
            as_of=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        )


class CapturingFixtureProvider(FixtureAIProvider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.payloads: list[str] = []

    async def analyze(self, **kwargs) -> ProviderResult:
        self.payloads.append(str(kwargs["user_payload"]))
        return await super().analyze(**kwargs)


@pytest.mark.asyncio
async def test_canonical_json_pipeline_fixture_direction_and_synthetic_refs() -> None:
    ai_input = authoritative_input(direction="SHORT")
    provider = CapturingFixtureProvider()
    result = await TradeThesisAgent().execute(ai_input, provider, ModelConfig(max_retries=0))
    payload = json.loads(provider.payloads[0])
    assert payload["schema"] == "ai-agent-input.v1"
    assert set(payload) == {"schema", "trusted_context", "untrusted_evidence"}
    assert payload["trusted_context"]["strategy_candidate"]["direction"] == "SHORT"
    assert "<untrusted_external_data>" not in provider.payloads[0]
    assert result.directional_bias == "SHORT"
    assert all(ref.startswith("fixture://trade_thesis/") for ref in result.evidence_refs)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload_size", [100_000, 1_000_000])
async def test_input_byte_budget_prevents_provider_call(payload_size: int) -> None:
    ai_input = authoritative_input()
    now = ai_input.as_of
    event = AINewsEventContext(
        id=f"oversize-{payload_size}",
        title="N" * payload_size,
        currency="USD",
        impact="HIGH",
        scheduled_at=now,
        available_at=now,
        updated_at=now,
    )
    news = ai_input.news_context.model_copy(update={"events": (event,), "event_ids": (event.id,)})
    provider = FixtureAIProvider()
    result = await MacroNewsAnalyst().execute(
        ai_input.model_copy(update={"news_context": news}),
        provider,
        ModelConfig(max_retries=5),
    )
    assert result.status == "DEGRADED"
    assert provider.call_history == []
    assert "budget exceeded" in result.warnings_th[0]


class OversizedOutputProvider(FixtureAIProvider):
    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode

    async def analyze(self, **kwargs) -> ProviderResult:
        result = await super().analyze(**kwargs)
        if self.mode == "content":
            return result.model_copy(update={"content": "X" * 20_000})
        if self.mode == "raw":
            return result.model_copy(update={"raw_payload": {"blob": "X" * 20_000}})
        return result.model_copy(
            update={
                "completion_tokens": 2_000,
                "total_tokens": result.prompt_tokens + 2_000,
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["content", "raw", "tokens"])
async def test_output_budgets_degrade_without_retry(mode: str) -> None:
    provider = OversizedOutputProvider(mode)
    result = await TradeThesisAgent().execute(
        authoritative_input(),
        provider,
        ModelConfig(max_output_tokens=1024, max_retries=5),
    )
    assert result.status == "DEGRADED"
    assert len(provider.call_history) == 1
    assert "budget exceeded" in result.warnings_th[0]


class TransientOnceProvider(CapturingFixtureProvider):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def analyze(self, **kwargs) -> ProviderResult:
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("temporary provider failure")
        return await super().analyze(**kwargs)


@pytest.mark.asyncio
async def test_retry_once_for_transient_failure_only() -> None:
    provider = TransientOnceProvider()
    result = await TradeThesisAgent().execute(
        authoritative_input(),
        provider,
        ModelConfig(max_retries=1),
    )
    assert result.status == "READY"
    assert provider.attempts == 2

    invalid = FixtureAIProvider(schema_invalid_agents={"trade_thesis"})
    invalid_result = await TradeThesisAgent().execute(
        authoritative_input(),
        invalid,
        ModelConfig(max_retries=5),
    )
    assert invalid_result.status == "DEGRADED"
    assert len(invalid.call_history) == 1


class HangingProvider(AIProvider):
    def __init__(self):
        self.attempts = 0
        self.cancelled = False

    async def analyze(self, **kwargs) -> ProviderResult:
        self.attempts += 1
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_retries_share_one_hard_deadline_and_cancel_provider() -> None:
    provider = HangingProvider()
    started = time.perf_counter()
    result = await TradeThesisAgent().execute(
        authoritative_input(),
        provider,
        ModelConfig(timeout_seconds=0.05, max_retries=5),
    )
    elapsed = time.perf_counter() - started
    assert result.status == "DEGRADED"
    assert elapsed < 0.20
    assert 1 <= provider.attempts <= 1 + 5
    assert provider.cancelled is True
