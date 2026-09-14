"""Behavioral closure tests for the five final Phase 6.1 acceptance blockers."""

import asyncio
import datetime as dt
import time

import pytest

import app.api.ai as ai_api
from app.services.ai.agents import TradeThesisAgent
from app.services.ai.domain import (
    PHASE3_TEMPORAL_FIELD_MAP,
    AIDealingRangeEvidence,
    AILiquidityEvidence,
    AIStructureEvent,
    AISwingEvidence,
    AIZoneEvidence,
)
from app.services.ai.execution import active_provider_process_count
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import (
    MIN_PROVIDER_TIMEOUT_SECONDS,
    AIProvider,
    FixtureAIProvider,
    ModelConfig,
    ProviderResult,
    analyze_with_controls,
)
from app.services.analysis.domain import DealingRange, LiquidityLevel, StructureEvent, SwingPoint, Zone
from tests.test_ai_corrective_round2 import authoritative_input


class HugeOrInconsistentUsageProvider(FixtureAIProvider):
    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode

    async def analyze(self, **kwargs) -> ProviderResult:
        result = await super().analyze(**kwargs)
        if self.mode == "huge":
            return result.model_copy(
                update={"prompt_tokens": 10**12, "completion_tokens": 1, "total_tokens": 10**12 + 1}
            )
        return result.model_copy(update={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 999})


class CancellationResistantProvider(AIProvider):
    async def analyze(self, **kwargs) -> ProviderResult:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            while True:
                await asyncio.sleep(60)
        raise AssertionError("unreachable")


_PHASE3_TEMPORAL_CASES = tuple(
    (source_name, field)
    for source_name, fields in PHASE3_TEMPORAL_FIELD_MAP.items()
    for field in fields
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("source_name", "future_field"), _PHASE3_TEMPORAL_CASES)
async def test_every_phase3_temporal_field_blocks_before_provider_when_future(
    source_name: str,
    future_field: str,
) -> None:
    ai_input = authoritative_input()
    past = ai_input.as_of - dt.timedelta(minutes=1)
    future = ai_input.as_of + dt.timedelta(microseconds=1)
    temporal = {
        field: future if field == future_field else past
        for field in PHASE3_TEMPORAL_FIELD_MAP[source_name]
    }
    if source_name == "SwingPoint":
        evidence = AISwingEvidence(id="future-swing", kind="HIGH", **temporal)
        structure = ai_input.structure_context.model_copy(update={"swings": (evidence,)})
    elif source_name == "StructureEvent":
        evidence = AIStructureEvent(id="future-event", kind="BOS", **temporal)
        structure = ai_input.structure_context.model_copy(update={"events": (evidence,)})
    elif source_name == "LiquidityLevel":
        evidence = AILiquidityEvidence(id="future-liquidity", kind="BSL", **temporal)
        structure = ai_input.structure_context.model_copy(update={"liquidity": (evidence,)})
    elif source_name == "Zone":
        evidence = AIZoneEvidence(id="future-zone", kind="FVG", **temporal)
        structure = ai_input.structure_context.model_copy(update={"zones": (evidence,)})
    else:
        evidence = AIDealingRangeEvidence(id="future-range", kind="BULLISH", **temporal)
        structure = ai_input.structure_context.model_copy(update={"dealing_range": evidence})
    provider = FixtureAIProvider()

    result = await AIOrchestrator(provider=provider).analyze(
        ai_input.model_copy(update={"structure_context": structure})
    )

    assert result.status == "BLOCKED_BY_UPSTREAM"
    assert provider.call_history == []


def test_phase3_temporal_projection_mapping_is_complete() -> None:
    matrix = {
        "SwingPoint": (SwingPoint, AISwingEvidence),
        "StructureEvent": (StructureEvent, AIStructureEvent),
        "LiquidityLevel": (LiquidityLevel, AILiquidityEvidence),
        "Zone": (Zone, AIZoneEvidence),
        "DealingRange": (DealingRange, AIDealingRangeEvidence),
    }
    for source_name, temporal_fields in PHASE3_TEMPORAL_FIELD_MAP.items():
        source_model, ai_model = matrix[source_name]
        actual_source_clocks = {
            field for field in source_model.model_fields if field.endswith(("_at", "_time"))
        }
        assert set(temporal_fields) == actual_source_clocks
        assert set(temporal_fields) <= set(ai_model.model_fields)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["huge", "inconsistent"])
async def test_provider_token_accounting_fails_closed(mode: str) -> None:
    provider = HugeOrInconsistentUsageProvider(mode)
    result = await TradeThesisAgent().execute(
        authoritative_input(),
        provider,
        ModelConfig(max_retries=3),
    )

    assert result.status == "DEGRADED"
    assert len(provider.call_history) == 1


@pytest.mark.asyncio
async def test_cancellation_resistant_provider_cannot_defeat_wall_clock_deadline() -> None:
    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        await analyze_with_controls(
            CancellationResistantProvider(),
            agent_id="cancellation_resistant",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(timeout_seconds=MIN_PROVIDER_TIMEOUT_SECONDS, max_retries=3),
        )
    elapsed = time.perf_counter() - started

    assert elapsed <= 0.40
    assert active_provider_process_count() == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"as_of": "2025-01-01T00:00:00Z"},
        {"execute": True},
    ],
)
def test_public_ai_request_rejects_unknown_fields_before_assembly(
    client,
    auth_headers,
    monkeypatch,
    extra: dict[str, object],
) -> None:
    called = False

    async def forbidden_assembly(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("strict request validation must run before assembly")

    monkeypatch.setattr(ai_api.AIAnalysisInputAssembler, "assemble", forbidden_assembly)
    response = client.post(
        "/api/ai-analysis/evaluate",
        headers=auth_headers,
        json={"candidate_id": "candidate", "account_id": "account", **extra},
    )

    assert response.status_code == 422
    assert called is False
