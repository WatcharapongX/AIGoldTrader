"""Batch C2 focused aggregate runtime-control tests."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

from app.services.ai.budget import AnalysisBudget, AnalysisBudgetLimits
from app.services.ai.execution import active_provider_process_count, provider_executor
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import (
    AnalysisDeadlineExceeded,
    FixtureAIProvider,
    ModelConfig,
    ProviderNetworkError,
    ProviderResult,
    SpawnSafeTestProvider,
)
from tests.test_ai_provider_phase62 import make_test_ai_input


class TransientOnceProvider(SpawnSafeTestProvider):
    def __init__(self) -> None:
        self.attempts = 0

    async def analyze(self, **kwargs: Any) -> ProviderResult:
        self.attempts += 1
        if self.attempts == 1:
            raise ProviderNetworkError("transient fixture failure")
        return _result()


class DelayedProvider(SpawnSafeTestProvider):
    def __init__(self, delay: float = 0.6) -> None:
        self.delay = delay
        self.attempts = 0

    async def analyze(self, **kwargs: Any) -> ProviderResult:
        self.attempts += 1
        await asyncio.sleep(self.delay)
        return _result()


def _limits(*, attempts: int = 4, prompt: int = 400, completion: int = 256,
            total: int = 656, measured_bytes: int = 160_000,
            deadline: float = 5.0) -> AnalysisBudgetLimits:
    return AnalysisBudgetLimits(
        max_provider_attempts=attempts,
        max_prompt_tokens=prompt,
        max_completion_tokens=completion,
        max_total_tokens=total,
        max_measured_bytes=measured_bytes,
        deadline_seconds=deadline,
    )


def _config(*, retries: int = 1) -> ModelConfig:
    return ModelConfig(
        max_input_tokens=100,
        max_output_tokens=64,
        max_total_tokens=164,
        max_retries=retries,
    )


def _result(prompt: int = 20, completion: int = 10) -> ProviderResult:
    return ProviderResult(
        content="{}",
        raw_payload={},
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


@pytest.mark.asyncio
async def test_exact_boundary_and_successful_usage_reconciliation():
    budget = AnalysisBudget(_limits(attempts=2))
    reservation = await budget.reserve("market_context", _config(retries=1))
    assert reservation is not None and reservation.authorized_attempts == 2
    reservation.mark_attempt_started(1)
    await reservation.reconcile_success(_result(), input_bytes=11, output_bytes=7)

    snapshot = await budget.snapshot()
    assert snapshot.attempts.used == 1
    assert snapshot.attempts.reserved == 0
    assert snapshot.attempts.remaining == 1
    assert snapshot.prompt_tokens.used == 20
    assert snapshot.completion_tokens.used == 10
    assert snapshot.total_tokens.used == 30
    assert snapshot.measured_bytes.used == 18


@pytest.mark.asyncio
async def test_retry_started_is_conservatively_charged_and_unused_retry_refunded():
    budget = AnalysisBudget(_limits(attempts=3, prompt=300, completion=192, total=492, measured_bytes=120_000))
    reservation = await budget.reserve("smc_ict", _config(retries=2))
    assert reservation is not None and reservation.authorized_attempts == 3
    reservation.mark_attempt_started(1)
    reservation.mark_attempt_started(2)
    await reservation.reconcile_success(_result(), input_bytes=10, output_bytes=5)

    snapshot = await budget.snapshot()
    assert snapshot.attempts.used == 2
    assert snapshot.attempts.remaining == 1
    assert snapshot.prompt_tokens.used == 120  # failed attempt cap + truthful success
    assert snapshot.completion_tokens.used == 74
    assert snapshot.total_tokens.used == 194
    assert snapshot.measured_bytes.used == 40_015


@pytest.mark.asyncio
async def test_failed_attempt_never_refunds_unknown_token_or_byte_usage():
    budget = AnalysisBudget(_limits(attempts=1, prompt=100, completion=64, total=164, measured_bytes=40_000))
    reservation = await budget.reserve("macro_news", _config(retries=0))
    assert reservation is not None
    reservation.mark_attempt_started(1)
    await reservation.reconcile_failure()
    snapshot = await budget.snapshot()
    assert snapshot.prompt_tokens.used == 100
    assert snapshot.completion_tokens.used == 64
    assert snapshot.total_tokens.used == 164
    assert snapshot.measured_bytes.used == 40_000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "resource"),
    [
        ({"prompt": 99}, "prompt_tokens"),
        ({"completion": 63}, "completion_tokens"),
        ({"total": 163}, "total_tokens"),
        ({"measured_bytes": 39_999}, "measured_bytes"),
    ],
)
async def test_each_aggregate_resource_can_deny_before_execution(overrides: dict[str, int], resource: str):
    budget = AnalysisBudget(_limits(attempts=1, **overrides))
    assert await budget.reserve("strategy_critic", _config(retries=0)) is None
    snapshot = await budget.snapshot()
    assert getattr(snapshot, resource).used == 0
    assert getattr(snapshot, resource).reserved == 0


@pytest.mark.asyncio
async def test_concurrent_reservations_never_oversubscribe_or_go_negative():
    for _ in range(20):
        budget = AnalysisBudget(_limits(attempts=3, prompt=300, completion=192, total=492, measured_bytes=120_000))
        reservations = await asyncio.gather(
            *(budget.reserve(f"agent_{index}", _config(retries=0)) for index in range(6))
        )
        assert sum(item is not None for item in reservations) == 3
        snapshot = await budget.snapshot()
        for resource in (
            snapshot.attempts,
            snapshot.prompt_tokens,
            snapshot.completion_tokens,
            snapshot.total_tokens,
            snapshot.measured_bytes,
        ):
            assert resource.used >= 0
            assert resource.reserved >= 0
            assert resource.remaining >= 0
            assert resource.used + resource.reserved <= resource.limit
        for reservation in reservations:
            if reservation is not None:
                await reservation.reconcile_failure()


@pytest.mark.asyncio
async def test_cancellation_before_and_after_attempt_and_double_reconcile_are_safe():
    budget = AnalysisBudget(_limits(attempts=2, prompt=200, completion=128, total=328, measured_bytes=80_000))
    before = await budget.reserve("risk_interpreter", _config(retries=0))
    assert before is not None
    assert await before.reconcile_failure() is True
    assert await before.reconcile_failure() is False
    first = await budget.snapshot()
    assert first.attempts.used == 0

    after = await budget.reserve("trade_thesis", _config(retries=0))
    assert after is not None
    after.mark_attempt_started(1)
    assert await after.reconcile_failure() is True
    assert await after.reconcile_success(_result(), input_bytes=1, output_bytes=1) is False
    final = await budget.snapshot()
    assert final.attempts.used == 1
    assert final.attempts.reserved == 0


@pytest.mark.asyncio
async def test_expired_deadline_denies_reservation():
    budget = AnalysisBudget(_limits(deadline=0.01), now=time.monotonic() - 1.0)
    assert await budget.reserve("market_context", _config(retries=0)) is None


def _orchestrator_limits(attempts: int, deadline: float = 5.0) -> AnalysisBudgetLimits:
    return AnalysisBudgetLimits(
        max_provider_attempts=attempts,
        max_prompt_tokens=attempts * 8192,
        max_completion_tokens=attempts * 1024,
        max_total_tokens=attempts * 9216,
        max_measured_bytes=attempts * 40_000,
        deadline_seconds=deadline,
    )


@pytest.fixture
def in_process_executor(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    async def execute(
        provider: Any,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: ModelConfig,
        timeout_seconds: float | None = None,
        analysis_reservation: Any = None,
    ) -> ProviderResult:
        calls.append(agent_id)
        analysis_reservation.mark_attempt_started(1)
        result = await FixtureAIProvider(provider_id=provider.provider_id).analyze(
            agent_id=agent_id,
            system_prompt=system_prompt,
            user_payload=user_payload,
            model_config=model_config,
            timeout_seconds=timeout_seconds,
        )
        raw_bytes = len(
            json.dumps(
                result.raw_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        await analysis_reservation.reconcile_success(
            result,
            input_bytes=len(system_prompt.encode()) + len(user_payload.encode()),
            output_bytes=len(result.content.encode()) + raw_bytes,
        )
        return result

    monkeypatch.setattr(provider_executor, "execute", execute)
    return calls


@pytest.mark.asyncio
async def test_normal_six_agent_plus_meta_flow_and_exact_attempt_boundary(in_process_executor: list[str]):
    orchestrator = AIOrchestrator(
        provider=FixtureAIProvider().to_descriptor(),
        default_config=ModelConfig(max_retries=0),
        budget_limits=_orchestrator_limits(7),
    )
    result = await orchestrator.analyze(make_test_ai_input())
    assert result.status == "READY"
    assert in_process_executor == [
        "market_context", "smc_ict", "macro_news", "strategy_critic",
        "risk_interpreter", "trade_thesis", "meta_controller",
    ]


@pytest.mark.asyncio
async def test_tight_attempt_budget_selects_canonical_agents_deterministically_and_skips_meta(
    in_process_executor: list[str],
):
    expected = ["market_context", "smc_ict", "macro_news"]
    for _ in range(5):
        in_process_executor.clear()
        orchestrator = AIOrchestrator(
            provider=FixtureAIProvider().to_descriptor(),
            default_config=ModelConfig(max_retries=0),
            budget_limits=_orchestrator_limits(3),
        )
        result = await orchestrator.analyze(make_test_ai_input())
        assert in_process_executor == expected
        assert result.status == "DEGRADED"
        assert result.warnings_th == ("ANALYSIS_BUDGET_EXHAUSTED",)
        assert result.execution_provenance is None
        assert result.agent_results["strategy_critic"].warnings_th == ("ANALYSIS_BUDGET_EXHAUSTED",)


@pytest.mark.asyncio
async def test_meta_is_skipped_when_agents_truthfully_consume_token_budget(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    async def max_usage_execute(
        provider: Any,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: ModelConfig,
        timeout_seconds: float | None = None,
        analysis_reservation: Any = None,
    ) -> ProviderResult:
        calls.append(agent_id)
        analysis_reservation.mark_attempt_started(1)
        base = await FixtureAIProvider(provider_id=provider.provider_id).analyze(
            agent_id=agent_id,
            system_prompt=system_prompt,
            user_payload=user_payload,
            model_config=model_config,
            timeout_seconds=timeout_seconds,
        )
        result = base.model_copy(
            update={
                "prompt_tokens": model_config.max_input_tokens,
                "completion_tokens": model_config.max_output_tokens,
                "total_tokens": model_config.max_total_tokens,
            }
        )
        await analysis_reservation.reconcile_success(
            result,
            input_bytes=len(system_prompt.encode()) + len(user_payload.encode()),
            output_bytes=len(result.content.encode()),
        )
        return result

    monkeypatch.setattr(provider_executor, "execute", max_usage_execute)
    limits = AnalysisBudgetLimits(
        max_provider_attempts=7,
        max_prompt_tokens=6 * 8192,
        max_completion_tokens=6 * 1024,
        max_total_tokens=6 * 9216,
        max_measured_bytes=7 * 40_000,
        deadline_seconds=5.0,
    )
    result = await AIOrchestrator(
        provider=FixtureAIProvider().to_descriptor(),
        default_config=ModelConfig(max_retries=0),
        budget_limits=limits,
    ).analyze(make_test_ai_input())
    assert calls == [
        "market_context", "smc_ict", "macro_news", "strategy_critic",
        "risk_interpreter", "trade_thesis",
    ]
    assert result.status == "DEGRADED"
    assert result.warnings_th == ("ANALYSIS_BUDGET_EXHAUSTED",)
    assert result.execution_provenance is None


@pytest.mark.asyncio
async def test_authority_gate_creates_no_budget_or_provider_work(monkeypatch: pytest.MonkeyPatch):
    from app.services.ai import orchestrator as orchestrator_module

    def forbidden_budget(*args: Any, **kwargs: Any):
        raise AssertionError("Budget must not be created before authority gates")

    monkeypatch.setattr(orchestrator_module, "AnalysisBudget", forbidden_budget)
    ai_input = make_test_ai_input().model_copy(
        update={"kill_switch_context": make_test_ai_input().kill_switch_context.model_copy(update={"state": "ACTIVE"})}
    )
    result = await AIOrchestrator(provider=FixtureAIProvider().to_descriptor()).analyze(ai_input)
    assert result.status == "BLOCKED_BY_KILL_SWITCH"


def _worker_limits(attempts: int, *, deadline: float = 5.0) -> AnalysisBudgetLimits:
    return AnalysisBudgetLimits(
        max_provider_attempts=attempts,
        max_prompt_tokens=attempts * 8192,
        max_completion_tokens=attempts * 1024,
        max_total_tokens=attempts * 9216,
        max_measured_bytes=attempts * 40_000,
        deadline_seconds=deadline,
    )


@pytest.mark.asyncio
async def test_worker_retry_consumes_two_attempts_and_conservatively_charges_failed_attempt():
    provider = TransientOnceProvider()
    config = ModelConfig(max_retries=1, timeout_seconds=5.0)
    budget = AnalysisBudget(_worker_limits(2))
    reservation = await budget.reserve("retry_success", config)
    assert reservation is not None
    result = await provider_executor._execute_test_provider_instance(
        provider,
        agent_id="retry_success",
        system_prompt="system",
        user_payload="{}",
        model_config=config,
        analysis_reservation=reservation,
    )
    assert result.total_tokens == 30
    assert provider.attempts == 2
    snapshot = await budget.snapshot()
    assert snapshot.attempts.used == 2
    assert snapshot.prompt_tokens.used == 8192 + 20
    assert snapshot.completion_tokens.used == 1024 + 10
    assert snapshot.total_tokens.used == 9216 + 30
    assert active_provider_process_count() == 0


@pytest.mark.asyncio
async def test_worker_retry_is_denied_when_aggregate_authorizes_one_attempt():
    provider = TransientOnceProvider()
    requested = ModelConfig(max_retries=3, timeout_seconds=5.0)
    budget = AnalysisBudget(_worker_limits(1))
    reservation = await budget.reserve("retry_denied", requested)
    assert reservation is not None and reservation.authorized_attempts == 1
    bounded = requested.model_copy(update={"max_retries": 0})
    with pytest.raises(ProviderNetworkError):
        await provider_executor._execute_test_provider_instance(
            provider,
            agent_id="retry_denied",
            system_prompt="system",
            user_payload="{}",
            model_config=bounded,
            analysis_reservation=reservation,
        )
    assert provider.attempts == 1
    snapshot = await budget.snapshot()
    assert snapshot.attempts.used == 1
    assert snapshot.attempts.remaining == 0
    assert active_provider_process_count() == 0


@pytest.mark.asyncio
async def test_queue_wait_counts_against_aggregate_deadline_and_waiter_never_spawns():
    provider_executor.configure_concurrency(max_concurrent=1, queue_timeout_seconds=15.0)
    holder = DelayedProvider(delay=0.6)
    waiter = DelayedProvider(delay=0.01)
    # Leave ample holder runtime for Windows spawn contention in the full suite;
    # only the waiter's 0.30s aggregate deadline is under test here.
    config = ModelConfig(max_retries=0, timeout_seconds=10.0)
    holder_task = asyncio.create_task(
        provider_executor._execute_test_provider_instance(
            holder,
            agent_id="holder",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )
    )
    try:
        while active_provider_process_count() == 0:
            await asyncio.sleep(0.005)
        budget = AnalysisBudget(_worker_limits(1, deadline=0.30))
        reservation = await budget.reserve("queued", config)
        assert reservation is not None
        with pytest.raises(AnalysisDeadlineExceeded):
            await provider_executor._execute_test_provider_instance(
                waiter,
                agent_id="queued",
                system_prompt="system",
                user_payload="{}",
                model_config=config,
                analysis_reservation=reservation,
            )
        assert waiter.attempts == 0
        await holder_task
        assert active_provider_process_count() == 0
    finally:
        if not holder_task.done():
            holder_task.cancel()
            await asyncio.gather(holder_task, return_exceptions=True)
        provider_executor.configure_concurrency(max_concurrent=6, queue_timeout_seconds=15.0)


@pytest.mark.asyncio
async def test_aggregate_deadline_caps_worker_timeout_and_kills_worker():
    provider = DelayedProvider(delay=5.0)
    config = ModelConfig(max_retries=0, timeout_seconds=5.0)
    budget = AnalysisBudget(_worker_limits(1, deadline=0.35))
    reservation = await budget.reserve("deadline_cap", config)
    assert reservation is not None
    started = time.monotonic()
    with pytest.raises(AnalysisDeadlineExceeded):
        await provider_executor._execute_test_provider_instance(
            provider,
            agent_id="deadline_cap",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
            analysis_reservation=reservation,
        )
    assert time.monotonic() - started < 1.5
    assert active_provider_process_count() == 0
    snapshot = await budget.snapshot()
    assert snapshot.attempts.used == 1


@pytest.mark.asyncio
async def test_cancellation_after_worker_start_kills_worker_and_retains_started_attempt():
    provider = DelayedProvider(delay=5.0)
    config = ModelConfig(max_retries=1, timeout_seconds=5.0)
    budget = AnalysisBudget(_worker_limits(2))
    reservation = await budget.reserve("cancelled", config)
    assert reservation is not None
    task = asyncio.create_task(
        provider_executor._execute_test_provider_instance(
            provider,
            agent_id="cancelled",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
            analysis_reservation=reservation,
        )
    )
    while active_provider_process_count() == 0:
        await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active_provider_process_count() == 0
    snapshot = await budget.snapshot()
    assert snapshot.attempts.used == 1
    assert snapshot.attempts.reserved == 0
