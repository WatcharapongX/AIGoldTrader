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
from app.services.ai.execution import active_provider_process_count, provider_executor
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import (
    MIN_PROVIDER_TIMEOUT_SECONDS,
    ModelConfig,
    ProviderDescriptor,
    ProviderResult,
    SpawnSafeTestProvider,
)
from app.services.analysis.domain import DealingRange, LiquidityLevel, StructureEvent, SwingPoint, Zone
from tests.test_ai_corrective_round2 import authoritative_input

TEST_WATCHDOG_TIMEOUT_SECONDS = 1.5


class CancellationResistantProvider(SpawnSafeTestProvider):
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

    result = await AIOrchestrator().analyze(
        ai_input.model_copy(update={"structure_context": structure})
    )

    assert result.status == "BLOCKED_BY_UPSTREAM"


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
    descriptor = ProviderDescriptor(
        provider_type="fixture",
        config_profile="fixture",
        fixture_options={"token_mode": mode},
    )
    result = await TradeThesisAgent().execute(
        authoritative_input(),
        descriptor,
        ModelConfig(max_retries=3),
    )

    assert result.status == "DEGRADED"


@pytest.mark.asyncio
async def test_cancellation_resistant_provider_cannot_defeat_wall_clock_deadline() -> None:
    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        await provider_executor._execute_test_provider_instance(
            CancellationResistantProvider(),
            agent_id="cancellation_resistant",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(timeout_seconds=MIN_PROVIDER_TIMEOUT_SECONDS, max_retries=3),
        )
    elapsed = time.perf_counter() - started

    assert elapsed <= TEST_WATCHDOG_TIMEOUT_SECONDS
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
