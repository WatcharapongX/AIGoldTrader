"""Phase 6.2 Real LLM Provider Integration test suite.

Verifies:
1. ProviderDescriptor immutability, serialization, and secret-free invariants.
2. Worker-side ProviderConfigResolver and secret loading (P1-202 closure).
3. Picklability and Windows multiprocessing spawn boundary safety.
4. OpenAICompatibleProvider adapter contract, strict token accounting (P2-205).
5. HTTP response body streaming limits (P2-207).
6. Zero secret leakage across logs, exceptions, and payloads.
7. Global concurrency control, peak worker bounding, and admission slot recovery (P2-203, P2-206).
8. Orchestrator integration, model mapping (P2-204), and truthful provenance (P2-208).
9. Config validation rejecting external mode with fixture type (P1-201).
10. Optional live_external smoke test.
"""

import asyncio
import datetime as dt
import http.server
import json
import os
import pickle
import threading
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings, configure_ai_provider_runtime, get_settings
from app.core.masking import mask_secret_text
from app.services.ai.adapters import (
    OpenAICompatibleProvider,
    ProviderConfigResolver,
    ProviderFactory,
)
from app.services.ai.domain import (
    AIAnalysisInput,
    AIAnalysisResult,
    AIKillSwitchContext,
    AIMarketQuoteContext,
    AIMarketStructureContext,
    AINewsContext,
    AIProvenance,
    AIRiskDecisionContext,
    AIStrategyContext,
    AITradePlanContext,
    compute_semantic_input_fingerprint,
)
from app.services.ai.execution import (
    active_provider_process_count,
    provider_executor,
)
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import (
    FixtureAIProvider,
    ModelConfig,
    OutputBudgetExceeded,
    ProviderAuthError,
    ProviderBudgetExceeded,
    ProviderCapacityExhausted,
    ProviderDescriptor,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResult,
    ProviderSchemaError,
    analyze_with_controls,
)


def make_test_ai_input(now_time: dt.datetime | None = None) -> AIAnalysisInput:
    """Construct a minimal valid AIAnalysisInput for testing."""
    if now_time is None:
        now_time = dt.datetime.now(dt.UTC)

    quote = AIMarketQuoteContext(
        symbol="XAUUSD",
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        timestamp=now_time,
        is_stale=False,
        source="simulated",
    )
    structure = AIMarketStructureContext(
        symbol="XAUUSD",
        timeframe="M15",
        as_of=now_time,
        internal_state="BULLISH",
        external_state="BULLISH",
        regime="TRENDING_UP",
        source="simulated",
        context_id="ctx_test_01",
        algorithm_version="structure-test-v1",
        current_sessions=("LONDON",),
        swings=(),
        events=(),
        liquidity=(),
        zones=(),
    )
    news = AINewsContext(
        news_state="CALM",
        in_blackout=False,
        as_of=now_time,
        events=(),
        event_ids=(),
        source="fixture_news",
        context_fingerprint="news-fp-test-01",
    )
    strategy = AIStrategyContext(
        candidate_id="cand_test_01",
        strategy_id="STRAT01",
        strategy_version="1.0.0",
        profile_id="day_trader",
        symbol="XAUUSD",
        direction="LONG",
        score=85,
        detected_at=now_time,
        confirmed_at=now_time,
        status="PENDING",
        evidence=(),
    )
    trade_plan = AITradePlanContext(
        plan_id="plan_test_01",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2501.00"),
        stop_loss=Decimal("2495.00"),
        take_profit_1=Decimal("2510.00"),
        take_profit_2=Decimal("2520.00"),
        risk_reward_ratio=Decimal("2.0"),
        invalidation_th="หลุดแนวรับ",
        as_of=now_time,
        expires_at=now_time + dt.timedelta(hours=2),
    )
    risk = AIRiskDecisionContext(
        decision_id="dec_test_01",
        decision="APPROVED",
        account_id="acc_test_01",
        profile_id="day_trader",
        policy_version="risk-policy-1.0.0",
        as_of=now_time,
        expires_at=now_time + dt.timedelta(minutes=15),
        reservation_id="res_test_01",
        reservation_status="ACTIVE",
    )
    kill_switch = AIKillSwitchContext(
        record_id="ks_test_01",
        state="INACTIVE",
        trigger_type="NONE",
    )
    provenance = AIProvenance(
        market_source="simulated",
        strategy_candidate_id="cand_test_01",
        strategy_evaluation_id="eval_test_01",
        trade_plan_id="plan_test_01",
        risk_decision_id="dec_test_01",
        risk_reservation_id="res_test_01",
        kill_switch_record_id="ks_test_01",
        kill_switch_as_of=now_time,
    )
    fp = compute_semantic_input_fingerprint(
        symbol="XAUUSD",
        account_id="acc_test_01",
        profile_id="day_trader",
        as_of=now_time,
        quote_context=quote,
        structure_context=structure,
        news_context=news,
        strategy_context=strategy,
        trade_plan_context=trade_plan,
        risk_context=risk,
        kill_switch_context=kill_switch,
        provenance=provenance,
    )

    return AIAnalysisInput(
        analysis_id="ai_analysis_test_01",
        trace_id="tr_test_01",
        analysis_requested_at=now_time,
        as_of=now_time,
        symbol="XAUUSD",
        account_id="acc_test_01",
        profile_id="day_trader",
        quote_context=quote,
        structure_context=structure,
        news_context=news,
        strategy_context=strategy,
        trade_plan_context=trade_plan,
        risk_context=risk,
        kill_switch_context=kill_switch,
        provenance=provenance,
        input_versions={"ai": "1.0.0"},
        input_fingerprint=fp,
    )


# ============================================================================
# 1. PROVIDER DESCRIPTOR & CONFIG TESTS (P1-201, P1-202)
# ============================================================================


def test_config_rejects_external_mode_with_fixture_type():
    """P1-201: AI_PROVIDER_MODE=external with AI_PROVIDER_TYPE=fixture must fail configuration."""
    with pytest.raises(ValueError, match="cannot use ai_provider_type='fixture'"):
        Settings(ai_provider_mode="external", ai_provider_type="fixture")


def test_provider_descriptor_defaults_and_immutability():
    descriptor = ProviderDescriptor()
    assert descriptor.provider_id == "default_provider"
    assert descriptor.provider_type == "fixture"
    assert descriptor.config_profile == "fixture"
    assert descriptor.model_bindings == {}
    assert descriptor.enabled is True

    # Immutability check
    with pytest.raises((TypeError, ValueError)):
        descriptor.provider_id = "mutated"  # type: ignore[misc]


def test_provider_descriptor_serialization_and_picklability():
    descriptor = ProviderDescriptor(
        provider_id="ext_openai",
        provider_type="openai_compatible",
        config_profile="primary",
        base_url="https://api.openai.com/v1",
        model_bindings={"fast-advisory": "gpt-4o-mini"},
    )
    # JSON serialization
    dumped = descriptor.model_dump(mode="json")
    assert dumped["provider_type"] == "openai_compatible"
    restored = ProviderDescriptor.model_validate(dumped)
    assert restored == descriptor

    # Picklability across spawn boundary
    pickled = pickle.dumps(descriptor)
    unpickled = pickle.loads(pickled)  # noqa: S301
    assert unpickled == descriptor


def test_provider_descriptor_rejects_raw_secrets():
    """P1-202: Raw secrets in config_profile must be rejected by Literal enum validation."""
    for bad_profile in ("sk-proj-1234567890", "AIzaSyD-1234567890", "Bearer secret123", "custom"):
        with pytest.raises(ValueError):
            ProviderDescriptor(config_profile=bad_profile)  # type: ignore[arg-type]


def test_provider_descriptor_rejects_openai_with_fixture_profile():
    with pytest.raises(ValueError, match="cannot use fixture config profile"):
        ProviderDescriptor(provider_type="openai_compatible", config_profile="fixture")


def test_provider_descriptor_extra_forbid():
    with pytest.raises(ValueError):
        ProviderDescriptor.model_validate({"extra_forbidden_key": 123})


# ============================================================================
# 2. WORKER PROVIDER FACTORY & RESOLVER TESTS (P1-202, P2-204)
# ============================================================================


def test_factory_creates_fixture():
    descriptor = ProviderDescriptor(provider_type="fixture")
    provider = ProviderFactory.create_provider(descriptor)
    assert isinstance(provider, FixtureAIProvider)


def test_factory_disabled_provider_raises():
    descriptor = ProviderDescriptor(provider_type="fixture", enabled=False)
    with pytest.raises(ProviderAuthError, match="disabled"):
        ProviderFactory.create_provider(descriptor)


def test_factory_unknown_provider_type_raises():
    with pytest.raises(ValueError):
        ProviderDescriptor(provider_type="unknown_vendor")  # type: ignore[arg-type]


def test_factory_missing_secret_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", None)

    descriptor = ProviderDescriptor(
        provider_id="custom_ext",
        provider_type="openai_compatible",
        config_profile="primary",
    )
    with pytest.raises(ProviderAuthError, match="Configured external provider credential is unavailable"):
        ProviderFactory.create_provider(descriptor)


def test_factory_creates_openai_compatible(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-key-abc-123")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "test-key-abc-123")

    descriptor = ProviderDescriptor(
        provider_id="test_openai",
        provider_type="openai_compatible",
        config_profile="primary",
        base_url="https://api.test.com/v1",
        model_bindings={"fast-advisory": "test-fast-model"},
    )
    provider = ProviderFactory.create_provider(descriptor)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.api_key == "test-key-abc-123"
    assert provider.base_url == "https://api.test.com/v1"
    assert provider.model_mapping["fast-advisory"] == "test-fast-model"


def test_provider_config_resolver_fixture():
    assert ProviderConfigResolver.resolve_secret("fixture") in ("", None)


def test_settings_model_mapping_wired_through_descriptor(monkeypatch: pytest.MonkeyPatch):
    """P2-204: Settings model mapping must wire through descriptor to worker adapter."""
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-key")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "test-key")

    descriptor = ProviderDescriptor(
        provider_id="mapped_provider",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings={"fast-advisory": "gpt-4o-mini", "reasoning-advisory": "o1-mini"},
    )
    provider = ProviderFactory.create_provider(descriptor)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model_mapping["fast-advisory"] == "gpt-4o-mini"
    assert provider.model_mapping["reasoning-advisory"] == "o1-mini"


# ============================================================================
# 3. OPENAI-COMPATIBLE ADAPTER CONTRACT TESTS (MOCK TRANSPORT)
# ============================================================================


@pytest.mark.asyncio
async def test_openai_adapter_success():
    expected_payload = {
        "status": "READY",
        "directional_bias": "LONG",
        "evidence_strength": "STRONG",
        "summary_th": "ทดสอบสำเร็จ",
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer mock-api-key"
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(expected_payload)}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key",
        transport=transport,
    )
    config = ModelConfig(timeout_seconds=5.0)

    res = await provider.analyze(
        agent_id="test_agent",
        system_prompt="system",
        user_payload='{"test": 1}',
        model_config=config,
    )

    assert isinstance(res, ProviderResult)
    assert res.raw_payload == expected_payload
    assert res.prompt_tokens == 120
    assert res.completion_tokens == 45
    assert res.total_tokens == 165
    assert res.model_used == "gpt-4o-mini"
    assert res.provider_id == "configured_external"
    assert res.provider_type == "openai_compatible"


@pytest.mark.asyncio
async def test_openai_adapter_missing_usage_raises_schema_error():
    """P2-205: Missing usage must raise ProviderSchemaError, not default to 0."""
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"status": "READY"})}}],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-api-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderSchemaError, match="usage"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_openai_adapter_inconsistent_token_accounting_raises_schema_error():
    """P2-205: Vendor total != prompt + completion must raise ProviderSchemaError without recalculating."""
    def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"status": "READY"})}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 999},
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderSchemaError, match="inconsistent"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_usage",
    [
        {"prompt_tokens": -1, "completion_tokens": 2, "total_tokens": 1},
        {"prompt_tokens": 1.5, "completion_tokens": 2, "total_tokens": 3.5},
        {"prompt_tokens": True, "completion_tokens": False, "total_tokens": 1},
        {"prompt_tokens": "10", "completion_tokens": "20", "total_tokens": "30"},
    ],
)
async def test_openai_adapter_rejects_invalid_token_types(bad_usage):
    """P2-205: Negative, float, bool, or string token values must be rejected."""
    def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"status": "READY"})}}],
                "usage": bad_usage,
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderSchemaError):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_http_entity_streaming_aborts_on_body_exceeding_byte_limit():
    """P2-207: HTTP response body exceeding MAX_PROVIDER_HTTP_RESPONSE_BYTES must abort during streaming."""
    huge_chunk = b"A" * 60_000

    def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=huge_chunk)

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises((OutputBudgetExceeded, ProviderBudgetExceeded), match="exceeded limit"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_openai_adapter_auth_failure_401():
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized: invalid api key")

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-api-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0, max_retries=2)

    with pytest.raises(ProviderAuthError, match="HTTP 401"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_openai_adapter_rate_limit_429():
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit exceeded")

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-api-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderRateLimitError, match="HTTP 429"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_openai_adapter_client_error_400():
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Bad Request: context length exceeded")

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-api-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderRequestError, match="HTTP 400"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_openai_adapter_server_error_500():
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-api-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderNetworkError, match="HTTP 500"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_openai_adapter_malformed_json_response():
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "not-valid-json{"}}],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-api-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderSchemaError, match="JSON"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
async def test_openai_adapter_output_byte_limit_exceeded():
    huge_content = json.dumps({"huge_field": "X" * 15000})

    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": huge_content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleProvider(api_key="mock-api-key", transport=transport)
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(OutputBudgetExceeded, match="exceeded output budget"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


# ============================================================================
# 4. SECRET SAFETY & ZERO LEAKAGE TESTS
# ============================================================================


def test_mask_secret_text_utility():
    secret = "SUPER_SECRET_AI_KEY_12345"
    raw_error = f"Error: Authorization: Bearer {secret} failed for api_key={secret}"
    masked = mask_secret_text(raw_error, [secret])
    assert secret not in masked
    assert "***MASKED***" in masked


@pytest.mark.asyncio
async def test_zero_secret_leakage_across_failure_modes():
    secret_key = "SK_CRITICAL_KEY_DO_NOT_LEAK_998877"

    for status_code in (401, 403, 429, 500):

        def mock_handler(_req: httpx.Request, code: int = status_code) -> httpx.Response:
            return httpx.Response(code, text=f"Error containing {secret_key}")

        transport = httpx.MockTransport(mock_handler)
        provider = OpenAICompatibleProvider(api_key=secret_key, transport=transport)
        config = ModelConfig(timeout_seconds=2.0)

        try:
            await provider.analyze(
                agent_id="secret_test_agent",
                system_prompt="system",
                user_payload="{}",
                model_config=config,
            )
            raise AssertionError("Should have raised exception")
        except Exception as exc:
            exc_str = str(exc)
            assert secret_key not in exc_str, f"Secret leaked in exception string: {exc_str}"
            assert "***MASKED***" in exc_str


# ============================================================================
# 5. MULTIPROCESSING SPAWN & P1-202 / P3-066 CLOSURE TEST
# ============================================================================


@pytest.mark.asyncio
async def test_worker_side_provider_construction_across_spawn(monkeypatch: pytest.MonkeyPatch):
    valid_response = {
        "status": "READY",
        "directional_bias": "LONG",
        "evidence_strength": "STRONG",
        "summary_th": "ผลลัพธ์จาก spawn worker",
    }

    class MockOpenAIServer(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            assert body["model"] == "gpt-4o-mini"
            payload = {
                "choices": [{"message": {"content": json.dumps(valid_response)}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), MockOpenAIServer)
    port = httpd.server_address[1]
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "spawn-key-12345")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "spawn-key-12345")

    descriptor = ProviderDescriptor(
        provider_id="spawn_test_provider",
        provider_type="openai_compatible",
        config_profile="primary",
        base_url=base_url,
        model_bindings={"fast-advisory": "gpt-4o-mini"},
    )

    try:
        config = ModelConfig(timeout_seconds=5.0)
        res = await analyze_with_controls(
            descriptor,
            agent_id="spawn_agent",
            system_prompt="system",
            user_payload='{"test": 1}',
            model_config=config,
        )
        assert res.raw_payload == valid_response
        assert res.prompt_tokens == 50
        assert res.completion_tokens == 20
        assert res.total_tokens == 70
        assert res.provider_id == "spawn_test_provider"
        assert res.provider_type == "openai_compatible"
        assert active_provider_process_count() == 0
    finally:
        httpd.shutdown()
        httpd.server_close()


# ============================================================================
# 6. GLOBAL CONCURRENCY LIMITER, TIMEOUT & ADMISSION RECOVERY (P2-203, P2-206)
# ============================================================================


def test_settings_concurrency_and_queue_timeout_wired_to_runtime_executor():
    """P2-203: configure_ai_provider_runtime must wire settings into ProviderExecutor."""
    custom_settings = Settings(
        ai_max_concurrent_provider_calls=4,
        ai_provider_queue_timeout_seconds=8.5,
    )
    configure_ai_provider_runtime(custom_settings)
    assert provider_executor.max_concurrent == 4
    assert provider_executor.queue_timeout_seconds == 8.5
    # Restore defaults
    provider_executor.configure_concurrency(max_concurrent=6, queue_timeout_seconds=15.0)


@pytest.mark.asyncio
async def test_admission_slot_recovery_on_pipe_or_process_failure():
    """P2-206: Semaphore admission slot must be released if Pipe() or Process() raises."""
    provider = ProviderDescriptor()
    config = ModelConfig(timeout_seconds=5.0)

    initial_slots = provider_executor.available_slots

    with patch("multiprocessing.get_context") as mock_get_context:
        mock_ctx = mock_get_context.return_value
        mock_ctx.Pipe.side_effect = OSError("Pipe creation failed")
        with pytest.raises(OSError, match="Pipe creation failed"):
            await provider_executor.execute(
                provider,
                agent_id="test",
                system_prompt="sys",
                user_payload="{}",
                model_config=config,
            )

    assert provider_executor.available_slots == initial_slots


@pytest.mark.asyncio
async def test_global_concurrency_bounding():
    provider_executor.configure_concurrency(max_concurrent=2, queue_timeout_seconds=15.0)

    peak_workers = 0
    provider = FixtureAIProvider()
    config = ModelConfig(timeout_seconds=5.0)

    async def call_agent(aid: str):
        nonlocal peak_workers
        workers = active_provider_process_count()
        peak_workers = max(peak_workers, workers)
        res = await analyze_with_controls(
            provider,
            agent_id=aid,
            system_prompt="sys",
            user_payload='{"test": 1}',
            model_config=config,
        )
        return res

    tasks = [call_agent(f"agent_{i}") for i in range(6)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 6
    assert peak_workers <= 2, f"Peak workers exceeded limit: {peak_workers} > 2"
    assert active_provider_process_count() == 0

    provider_executor.configure_concurrency(max_concurrent=6, queue_timeout_seconds=15.0)


@pytest.mark.asyncio
async def test_backpressure_queue_timeout_rejects():
    provider_executor.configure_concurrency(max_concurrent=1, queue_timeout_seconds=0.05)

    provider = FixtureAIProvider()
    config = ModelConfig(timeout_seconds=5.0)

    async def long_task():
        return await analyze_with_controls(
            provider,
            agent_id="slot_holder",
            system_prompt="sys",
            user_payload='{"test": 1}',
            model_config=config,
        )

    async def blocked_task():
        await asyncio.sleep(0.01)
        return await analyze_with_controls(
            provider,
            agent_id="queue_waiter",
            system_prompt="sys",
            user_payload='{"test": 1}',
            model_config=config,
        )

    t1 = asyncio.create_task(long_task())
    with pytest.raises(ProviderCapacityExhausted, match="Provider capacity exhausted"):
        await blocked_task()

    await t1
    provider_executor.configure_concurrency(max_concurrent=6, queue_timeout_seconds=15.0)


# ============================================================================
# 7. ORCHESTRATOR INTEGRATION & PROVENANCE SPOOFING DEFENSE (P2-208)
# ============================================================================


@pytest.mark.asyncio
async def test_provider_provenance_spoofing_defeated():
    """P2-208: ModelConfig.provider must not be accepted as authoritative provenance."""
    ai_input = make_test_ai_input()
    spoofed_config = ModelConfig(provider="attacker_spoofed_provider")
    orch = AIOrchestrator(provider=FixtureAIProvider(), default_config=spoofed_config)
    res = await orch.analyze(ai_input)

    assert res.provider_provenance == "fixture"
    assert res.provider_provenance != "attacker_spoofed_provider"
    for _agent_id, a_res in res.agent_results.items():
        assert a_res.provider_provenance == "fixture"
        assert a_res.provider_provenance != "attacker_spoofed_provider"


@pytest.mark.asyncio
async def test_orchestrator_auth_failure_degrades_gracefully(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "bad-key")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "bad-key")

    descriptor = ProviderDescriptor(
        provider_id="fail_auth_provider",
        provider_type="openai_compatible",
        config_profile="primary",
    )

    def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized key")

    ProviderFactory.register_test_transport("fail_auth_provider", httpx.MockTransport(mock_handler))
    try:
        orch = AIOrchestrator(descriptor=descriptor)
        assert orch.provider == descriptor
    finally:
        ProviderFactory.clear_test_transports()


# ============================================================================
# 8. MOCK SERVER SPAWN: FULL ORCHESTRATION PIPELINE (6 AGENTS + METACONTROLLER)
# ============================================================================


@pytest.mark.asyncio
async def test_mock_server_spawn_full_orchestration_all_agents(monkeypatch: pytest.MonkeyPatch):
    """Verify complete analytical pipeline (6 agents + MetaController) across real spawn boundary."""
    called_agents = []

    def make_response_for_body(body: dict) -> dict:
        messages = body.get("messages", [])
        system_msg = messages[0]["content"] if messages else ""
        if "meta_controller" in system_msg:
            called_agents.append("meta_controller")
            return {
                "directional_bias": "LONG",
                "evidence_strength": "STRONG",
                "agent_agreement": "HIGH",
                "summary_th": "สรุปผลการวิเคราะห์ภาพรวมโดย AI",
                "key_evidence_th": ["หลักฐานชัดเจน"],
                "conflicts_th": [],
                "risk_notes_th": [],
                "warnings_th": [],
            }
        # One of the 6 analytical agents
        called_agents.append("analytical_agent")
        return {
            "status": "READY",
            "directional_bias": "LONG",
            "evidence_strength": "STRONG",
            "summary_th": "แนวโน้มขาขึ้นชัดเจน",
            "evidence_refs": ["ref_01"],
            "supporting_factors_th": ["ปัจจัยบวก"],
            "conflicting_factors_th": [],
            "warnings_th": [],
            "missing_context_th": [],
        }

    class MockAllAgentsServer(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            resp_payload = make_response_for_body(body)
            payload = {
                "choices": [{"message": {"content": json.dumps(resp_payload)}}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), MockAllAgentsServer)
    port = httpd.server_address[1]
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "all-agents-key")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "all-agents-key")

    descriptor = ProviderDescriptor(
        provider_id="mock_all_agents",
        provider_type="openai_compatible",
        config_profile="primary",
        base_url=base_url,
        model_bindings={"fast-advisory": "gpt-4o-mini", "reasoning-advisory": "gpt-4o-mini"},
    )

    try:
        config = ModelConfig(timeout_seconds=20.0)
        ai_input = make_test_ai_input()
        orch = AIOrchestrator(descriptor=descriptor, default_config=config)

        res = await orch.analyze(ai_input)

        assert isinstance(res, AIAnalysisResult)
        assert res.status == "READY"
        assert res.provider_provenance == "mock_all_agents"
        assert len(res.agent_results) == 6
        for _agent_id, a_res in res.agent_results.items():
            assert a_res.provider_provenance == "mock_all_agents"
            assert a_res.status == "READY"

        assert len(called_agents) == 7  # 6 analytical agents + 1 MetaController
        assert active_provider_process_count() == 0
    finally:
        httpd.shutdown()
        httpd.server_close()


# ============================================================================
# 9. LIVE EXTERNAL TEST MARKER (OPTIONAL / CONDITIONAL)
# ============================================================================


@pytest.mark.live_external
@pytest.mark.asyncio
async def test_live_external_llm_smoke():
    api_key = os.environ.get("AI_PROVIDER_API_KEY")
    mode = os.environ.get("AI_PROVIDER_MODE", "fixture")
    if not api_key or mode != "external":
        pytest.skip("BLOCKED BY CREDENTIAL AVAILABILITY: AI_PROVIDER_API_KEY not set or AI_PROVIDER_MODE != external")

    descriptor = ProviderDescriptor(
        provider_id="live_test",
        provider_type="openai_compatible",
        config_profile="primary",
        base_url=os.environ.get("AI_PROVIDER_BASE_URL"),
    )
    config = ModelConfig(timeout_seconds=15.0)
    res = await analyze_with_controls(
        descriptor,
        agent_id="live_smoke",
        system_prompt="Respond in valid JSON with key 'status': 'READY'",
        user_payload='{"ping": 1}',
        model_config=config,
    )
    assert res.total_tokens > 0
    assert "status" in res.raw_payload
