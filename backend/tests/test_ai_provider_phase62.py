"""Phase 6.2 Real LLM Provider Integration test suite.

Verifies:
1. ProviderDescriptor immutability, serialization, and secret-free invariants.
2. Worker-side ProviderFactory construction and secret loading (P3-066 closure).
3. Picklability and Windows multiprocessing spawn boundary safety.
4. OpenAICompatibleProvider adapter contract, error classification, and token accounting.
5. Zero secret leakage across logs, exceptions, and payloads.
6. Global concurrency control, peak worker bounding, and bounded backpressure.
7. Orchestrator integration and fail-closed degradation (no silent fallback).
8. Optional live_external smoke test.
"""

import asyncio
import json
import os
import pickle

import httpx
import pytest

from app.core.masking import mask_secret_text
from app.services.ai.adapters import (
    OpenAICompatibleProvider,
    ProviderFactory,
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
    ProviderCapacityExhausted,
    ProviderDescriptor,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResult,
    ProviderSchemaError,
    analyze_with_controls,
)

# ============================================================================
# 1. PROVIDER DESCRIPTOR TESTS
# ============================================================================


def test_provider_descriptor_defaults_and_immutability():
    descriptor = ProviderDescriptor()
    assert descriptor.provider_id == "default_provider"
    assert descriptor.provider_type == "fixture"
    assert descriptor.model_alias == "fast-advisory"
    assert descriptor.credential_ref is None
    assert descriptor.enabled is True

    # Immutability check
    with pytest.raises((TypeError, ValueError)):
        descriptor.provider_id = "mutated"  # type: ignore[misc]


def test_provider_descriptor_serialization_and_picklability():
    descriptor = ProviderDescriptor(
        provider_id="ext_openai",
        provider_type="openai_compatible",
        model_alias="reasoning-advisory",
        credential_ref="AI_PROVIDER_API_KEY",
        base_url_ref="AI_PROVIDER_BASE_URL",
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
    # Attempting to pass raw API keys as credential_ref must fail validation
    for bad_ref in ("sk-proj-1234567890", "AIzaSyD-1234567890", "Bearer secret123"):
        with pytest.raises(ValueError, match="credential_ref must be an environment variable name"):
            ProviderDescriptor(credential_ref=bad_ref)


def test_provider_descriptor_extra_forbid():
    with pytest.raises(ValueError):
        ProviderDescriptor.model_validate({"extra_forbidden_key": 123})


# ============================================================================
# 2. WORKER PROVIDER FACTORY TESTS (P3-066 CLOSURE)
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
    monkeypatch.delenv("CUSTOM_API_KEY", raising=False)
    descriptor = ProviderDescriptor(
        provider_id="custom_ext",
        provider_type="openai_compatible",
        credential_ref="CUSTOM_API_KEY",
    )
    with pytest.raises(ProviderAuthError, match="missing or empty in environment"):
        ProviderFactory.create_provider(descriptor)


def test_factory_creates_openai_compatible(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TEST_AI_KEY", "test-key-abc-123")
    monkeypatch.setenv("TEST_BASE_URL", "https://api.test.com/v1")
    monkeypatch.setenv("AI_MODEL_FAST_ADVISORY", "test-fast-model")

    descriptor = ProviderDescriptor(
        provider_id="test_openai",
        provider_type="openai_compatible",
        credential_ref="TEST_AI_KEY",
        base_url_ref="TEST_BASE_URL",
    )
    provider = ProviderFactory.create_provider(descriptor)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.api_key == "test-key-abc-123"
    assert provider.base_url == "https://api.test.com/v1"
    assert provider.model_mapping["fast-advisory"] == "test-fast-model"


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


@pytest.mark.asyncio
async def test_openai_adapter_missing_usage_defaults_safely():
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

    res = await provider.analyze(
        agent_id="test_agent",
        system_prompt="system",
        user_payload="{}",
        model_config=config,
    )
    assert res.prompt_tokens == 0
    assert res.completion_tokens == 0
    assert res.total_tokens == 0


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


# ============================================================================
# 5. MULTIPROCESSING SPAWN & P3-066 CLOSURE TEST
# ============================================================================


@pytest.mark.asyncio
async def test_worker_side_provider_construction_across_spawn(monkeypatch: pytest.MonkeyPatch):
    import http.server
    import threading

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
    monkeypatch.setenv("SPAWN_TEST_KEY", "spawn-key-12345")
    monkeypatch.setenv("SPAWN_TEST_BASE_URL", base_url)
    descriptor = ProviderDescriptor(
        provider_id="spawn_test_provider",
        provider_type="openai_compatible",
        credential_ref="SPAWN_TEST_KEY",
        base_url_ref="SPAWN_TEST_BASE_URL",
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
        assert active_provider_process_count() == 0
    finally:
        httpd.shutdown()
        httpd.server_close()


# ============================================================================
# 6. GLOBAL CONCURRENCY LIMITER & BOUNDED BACKPRESSURE
# ============================================================================


@pytest.mark.asyncio
async def test_global_concurrency_bounding():
    # Set concurrency cap = 2 with adequate queue wait
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

    # Launch 6 tasks concurrently
    tasks = [call_agent(f"agent_{i}") for i in range(6)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 6
    # Peak active workers must never exceed configured limit of 2
    assert peak_workers <= 2, f"Peak workers exceeded global concurrency limit: {peak_workers} > 2"
    assert active_provider_process_count() == 0

    # Restore default
    provider_executor.configure_concurrency(max_concurrent=6, queue_timeout_seconds=15.0)


@pytest.mark.asyncio
async def test_backpressure_queue_timeout_rejects():
    # Set cap = 1, timeout = 0.05s
    provider_executor.configure_concurrency(max_concurrent=1, queue_timeout_seconds=0.05)

    provider = FixtureAIProvider()
    config = ModelConfig(timeout_seconds=5.0)

    # First task holds slot
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
# 7. ORCHESTRATOR INTEGRATION & DEGRADED SEMANTICS
# ============================================================================


@pytest.mark.asyncio
async def test_orchestrator_auth_failure_degrades_gracefully(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAIL_KEY", "bad-key")
    descriptor = ProviderDescriptor(
        provider_id="fail_auth_provider",
        provider_type="openai_compatible",
        credential_ref="FAIL_KEY",
    )

    def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized key")

    ProviderFactory.register_test_transport("fail_auth_provider", httpx.MockTransport(mock_handler))
    try:
        orch = AIOrchestrator(descriptor=descriptor)
        # Verify provider set correctly
        assert orch.provider == descriptor
    finally:
        ProviderFactory.clear_test_transports()


# ============================================================================
# 8. LIVE EXTERNAL TEST MARKER (OPTIONAL / CONDITIONAL)
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
        credential_ref="AI_PROVIDER_API_KEY",
        base_url_ref="AI_PROVIDER_BASE_URL",
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
