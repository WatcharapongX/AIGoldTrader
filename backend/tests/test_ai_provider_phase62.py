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
import contextlib
import datetime as dt
import http.server
import json
import os
import pickle
import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings, configure_ai_provider_runtime, get_settings
from app.core.masking import mask_secret_text
from app.services.ai.adapters import (
    OpenAIChatCompletionsProvider,
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
    MIN_PROVIDER_TIMEOUT_SECONDS,
    FixtureAIProvider,
    FixtureProviderOptions,
    ModelConfig,
    OutputBudgetExceeded,
    ProviderAuthError,
    ProviderBudgetExceeded,
    ProviderCapacityExhausted,
    ProviderDescriptor,
    ProviderInternalError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResult,
    ProviderSchemaError,
    ProviderTimeoutError,
    ProviderWorkerTerminationError,
    SpawnSafeTestProvider,
    analyze_with_controls,
    public_provider_failure_code,
)

TEST_MODEL_MAPPING = {"fast-advisory": "gpt-4o-mini"}


class SlowFixtureProvider(FixtureAIProvider):
    async def analyze(self, **kwargs):
        await asyncio.sleep(0.2)
        return await super().analyze(**kwargs)


class CancellationResistantFixtureProvider(FixtureAIProvider):
    async def analyze(self, **kwargs):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            while True:
                await asyncio.sleep(60)


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


def test_c1_external_configuration_matrix_is_static_and_fail_closed(monkeypatch):
    """C-ADR-005: mode selection is explicit and validation performs no network I/O."""
    network_calls = 0

    def forbidden_network(*_args, **_kwargs):
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("Settings validation must not perform network I/O")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_network)
    fixture = Settings(ai_provider_mode="fixture", ai_provider_type="fixture")
    assert fixture.ai_provider_mode == "fixture"
    valid = Settings(
        ai_provider_mode="external",
        ai_provider_type="openai_compatible",
        ai_provider_api_key="configured-c1-secret",
        ai_provider_base_url="https://api.openai.com/v1",
        ai_model_mapping={"fast-advisory": "vendor-model-1"},
    )
    assert valid.ai_provider_type == "openai_compatible"
    assert network_calls == 0

    invalid_cases = (
        {"ai_provider_mode": "external", "ai_provider_type": "fixture"},
        {
            "ai_provider_mode": "external",
            "ai_provider_type": "openai_compatible",
            "ai_provider_api_key": "",
            "ai_model_mapping": {"fast-advisory": "vendor-model-1"},
        },
        {
            "ai_provider_mode": "external",
            "ai_provider_type": "openai_compatible",
            "ai_provider_api_key": "configured-c1-secret",
            "ai_model_mapping": {},
        },
        {
            "ai_provider_mode": "external",
            "ai_provider_type": "openai_compatible",
            "ai_provider_api_key": "configured-c1-secret",
            "ai_model_mapping": {"INVALID ALIAS": "vendor-model-1"},
        },
        {
            "ai_provider_mode": "external",
            "ai_provider_type": "openai_compatible",
            "ai_provider_api_key": "configured-c1-secret",
            "ai_model_mapping": {"fast-advisory": "https://invalid.example/model"},
        },
        {
            "ai_provider_mode": "external",
            "ai_provider_type": "openai_compatible",
            "ai_provider_api_key": "configured-c1-secret",
            "ai_provider_base_url": "http://provider.invalid/v1",
            "ai_model_mapping": {"fast-advisory": "vendor-model-1"},
        },
        {
            "ai_provider_mode": "external",
            "ai_provider_type": "openai_compatible",
            "ai_provider_api_key": "configured-c1-secret",
            "ai_provider_base_url": "https://user:password@provider.example/v1",
            "ai_model_mapping": {"fast-advisory": "vendor-model-1"},
        },
        {"ai_provider_mode": "fixture", "ai_provider_type": "openai_compatible"},
    )
    for values in invalid_cases:
        with pytest.raises(ValueError):
            Settings(**values)
    assert network_calls == 0


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (ProviderAuthError("hostile"), "PROVIDER_AUTH_FAILED"),
        (ProviderRateLimitError("hostile"), "PROVIDER_RATE_LIMITED"),
        (ProviderTimeoutError("hostile"), "PROVIDER_TIMEOUT"),
        (ProviderNetworkError("hostile"), "PROVIDER_NETWORK_ERROR"),
        (ProviderCapacityExhausted("hostile"), "PROVIDER_CAPACITY_EXHAUSTED"),
        (ProviderRequestError("hostile"), "PROVIDER_REQUEST_REJECTED"),
        (ProviderSchemaError("hostile"), "PROVIDER_SCHEMA_INVALID"),
        (ProviderBudgetExceeded("hostile"), "PROVIDER_BUDGET_EXCEEDED"),
        (ProviderWorkerTerminationError("hostile"), "PROVIDER_WORKER_FAILURE"),
        (ProviderInternalError("hostile"), "PROVIDER_INTERNAL_ERROR"),
    ],
)
def test_c1_provider_failure_mapping_is_deterministic(error, expected_code):
    assert public_provider_failure_code(error) == expected_code


def test_provider_descriptor_defaults_and_immutability():
    descriptor = ProviderDescriptor()
    assert descriptor.provider_id == "default_provider"
    assert descriptor.provider_type == "fixture"
    assert descriptor.config_profile == "fixture"
    assert descriptor.model_bindings == ()
    assert descriptor.enabled is True

    # Immutability check
    with pytest.raises((TypeError, ValueError)):
        descriptor.provider_id = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("provider_type", "config_profile", "valid"),
    [
        ("fixture", "fixture", True),
        ("fixture", "primary", False),
        ("openai_compatible", "primary", True),
        ("openai_compatible", "fixture", False),
    ],
)
def test_provider_descriptor_enforces_complete_type_profile_matrix(provider_type, config_profile, valid):
    kwargs = {
        "provider_type": provider_type,
        "config_profile": config_profile,
    }
    if provider_type == "openai_compatible":
        kwargs.update(model_bindings=TEST_MODEL_MAPPING)
    if valid:
        ProviderDescriptor(**kwargs)
    else:
        with pytest.raises(ValueError):
            ProviderDescriptor(**kwargs)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:password@example.com/v1",
        "https://TOKEN@example.com/v1",
        "https://example.com/v1?api_key=SECRET",
        "https://example.com/v1#secret",
        " https://example.com/v1",
        "https://example.com/v1 ",
        "https://example.com/a b",
        "https://example.com/%20",
        "https://example.com/a%20b",
        "https://example.com/%09",
        "https://example.com/%0a",
        "https://example.com/%0d",
        "https://example.com/v1%0a",
        "https://example.com/%2520",
        "http://provider.example/v1",
    ],
)
def test_external_descriptor_rejects_credential_bearing_or_unsafe_urls(base_url):
    from app.services.ai.provider import validate_provider_base_url

    with pytest.raises(ValueError):
        validate_provider_base_url(base_url)

    with pytest.raises(ValueError):
        Settings(ai_provider_base_url=base_url)

    # ProviderDescriptor itself must reject base_url as forbidden extra input
    with pytest.raises(ValueError):
        ProviderDescriptor(
            provider_id="safe_provider",
            provider_type="openai_compatible",
            config_profile="primary",
            base_url=base_url,  # type: ignore[call-arg]
            model_bindings=TEST_MODEL_MAPPING,
        )


def test_external_descriptor_requires_bounded_explicit_immutable_model_bindings():
    with pytest.raises(ValueError, match="non-empty"):
        ProviderDescriptor(
            provider_id="external",
            provider_type="openai_compatible",
            config_profile="primary",
        )
    with pytest.raises(ValueError):
        ProviderDescriptor(
            provider_id="external",
            provider_type="openai_compatible",
            config_profile="primary",
            model_bindings={f"model-{i}": "vendor-model" for i in range(17)},
        )
    for bindings in (
        {"A": "vendor-model"},
        {"a" * 65: "vendor-model"},
        {"fast-advisory": "X" * 129},
        {"fast-advisory": "https://secret.example/model"},
    ):
        with pytest.raises(ValueError):
            ProviderDescriptor(
                provider_id="external",
                provider_type="openai_compatible",
                config_profile="primary",
                model_bindings=bindings,
            )

    descriptor = ProviderDescriptor(
        provider_id="external",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings=TEST_MODEL_MAPPING,
    )
    assert descriptor.model_mapping == TEST_MODEL_MAPPING
    with pytest.raises((TypeError, ValueError)):
        descriptor.model_bindings[0].model = "changed"  # type: ignore[misc]


def test_provider_descriptor_rejects_oversized_or_secret_like_identity_fields():
    for provider_id in ("P" * 65, "sk-live-secret", "provider id"):
        with pytest.raises(ValueError):
            ProviderDescriptor(provider_id=provider_id)


def test_model_config_enforces_measured_windows_subprocess_minimum():
    with pytest.raises(ValueError):
        ModelConfig(timeout_seconds=MIN_PROVIDER_TIMEOUT_SECONDS - 0.001)
    assert ModelConfig(timeout_seconds=MIN_PROVIDER_TIMEOUT_SECONDS).timeout_seconds == MIN_PROVIDER_TIMEOUT_SECONDS
    assert ModelConfig(timeout_seconds=10.0).timeout_seconds == 10.0


@pytest.mark.asyncio
async def test_execution_timeout_override_cannot_bypass_windows_minimum():
    with pytest.raises(ValueError, match="execution timeout must be between"):
        await analyze_with_controls(
            ProviderDescriptor(provider_type="fixture", config_profile="fixture"),
            agent_id="tiny_timeout",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(),
            timeout_seconds=MIN_PROVIDER_TIMEOUT_SECONDS - 0.001,
        )


@pytest.mark.asyncio
async def test_cancellation_resistant_worker_is_killed_within_documented_contract():
    started = asyncio.get_running_loop().time()
    with pytest.raises(ProviderTimeoutError):
        await provider_executor._execute_test_provider_instance(
            CancellationResistantFixtureProvider(),
            agent_id="cancellation_resistant",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(timeout_seconds=MIN_PROVIDER_TIMEOUT_SECONDS, max_retries=3),
        )
    elapsed = asyncio.get_running_loop().time() - started
    TEST_WATCHDOG = 1.5
    assert elapsed < TEST_WATCHDOG, f"Watchdog exceeded: elapsed {elapsed:.3f}s >= {TEST_WATCHDOG}s"
    assert active_provider_process_count() == 0


@pytest.mark.parametrize(("max_retries", "expected_calls"), [(0, 1), (1, 2), (3, 4)])
@pytest.mark.asyncio
async def test_spawned_rate_limit_retries_match_configured_count(
    monkeypatch: pytest.MonkeyPatch, max_retries: int, expected_calls: int
):
    calls = 0

    class RateLimitServer(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal calls
            calls += 1
            size = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(size)
            body = b'{"error":"rate limited"}'
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), RateLimitServer)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "rate-limit-test-key")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "rate-limit-test-key")
    monkeypatch.setattr(settings, "ai_provider_base_url", f"http://127.0.0.1:{httpd.server_address[1]}")
    descriptor = ProviderDescriptor(
        provider_id="rate_limit_provider",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings=TEST_MODEL_MAPPING,
    )
    try:
        with pytest.raises(ProviderRateLimitError):
            await analyze_with_controls(
                descriptor,
                agent_id="rate_limit_test",
                system_prompt="system",
                user_payload="{}",
                model_config=ModelConfig(timeout_seconds=20.0, max_retries=max_retries),
            )
        assert calls == expected_calls
        assert active_provider_process_count() == 0
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.asyncio
async def test_network_error_defensively_redacts_unsafe_direct_adapter_url():
    secret = "URL_PASSWORD_VALUE_887766"

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection failed for {request.url}", request=request)

    provider = OpenAICompatibleProvider(
        api_key="different-api-key",
        model_mapping=TEST_MODEL_MAPPING,
        base_url=f"https://user:{secret}@provider.example/v1?api_key={secret}",
        transport=httpx.MockTransport(fail),
    )
    with pytest.raises(ProviderNetworkError) as caught:
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(),
        )
    assert secret not in str(caught.value)
    assert "user" not in str(caught.value)
    assert "api_key" not in str(caught.value)
    # Section 19: No host or URL logged in network error
    assert "provider.example" not in str(caught.value)
    assert "Provider network error: provider_id=" in str(caught.value)


def test_provider_descriptor_serialization_and_picklability():
    descriptor = ProviderDescriptor(
        provider_id="ext_openai",
        provider_type="openai_compatible",
        config_profile="primary",
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
    with pytest.raises(ValueError, match="must use primary config profile"):
        ProviderDescriptor(
            provider_type="openai_compatible",
            config_profile="fixture",
            model_bindings=TEST_MODEL_MAPPING,
        )


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
        model_bindings=TEST_MODEL_MAPPING,
    )
    with pytest.raises(ProviderAuthError, match="Configured external provider credential is unavailable"):
        ProviderFactory.create_provider(descriptor)


def test_factory_creates_openai_compatible(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-key-abc-123")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://api.test.com/v1")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "test-key-abc-123")
    monkeypatch.setattr(settings, "ai_provider_base_url", "https://api.test.com/v1")

    descriptor = ProviderDescriptor(
        provider_id="test_openai",
        provider_type="openai_compatible",
        config_profile="primary",
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
    monkeypatch.setattr(settings, "ai_provider_mode", "external")
    monkeypatch.setattr(settings, "ai_provider_type", "openai_compatible")
    monkeypatch.setattr(settings, "ai_provider_base_url", "https://provider.example/v1")
    monkeypatch.setattr(
        settings,
        "ai_model_mapping",
        {"fast-advisory": "gpt-4o-mini", "reasoning-advisory": "o1-mini"},
    )

    descriptor = AIOrchestrator().provider
    assert isinstance(descriptor, ProviderDescriptor)
    assert descriptor.model_mapping == settings.ai_model_mapping
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
        model_mapping=TEST_MODEL_MAPPING,
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
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key", model_mapping=TEST_MODEL_MAPPING, transport=transport
    )
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
    provider = OpenAICompatibleProvider(api_key="mock-key", model_mapping=TEST_MODEL_MAPPING, transport=transport)
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
    provider = OpenAICompatibleProvider(api_key="mock-key", model_mapping=TEST_MODEL_MAPPING, transport=transport)
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
    provider = OpenAICompatibleProvider(api_key="mock-key", model_mapping=TEST_MODEL_MAPPING, transport=transport)
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
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key", model_mapping=TEST_MODEL_MAPPING, transport=transport
    )
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
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key", model_mapping=TEST_MODEL_MAPPING, transport=transport
    )
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
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key", model_mapping=TEST_MODEL_MAPPING, transport=transport
    )
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
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key", model_mapping=TEST_MODEL_MAPPING, transport=transport
    )
    config = ModelConfig(timeout_seconds=5.0)

    with pytest.raises(ProviderNetworkError, match="HTTP 500"):
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (400, ProviderRequestError),
        (500, ProviderNetworkError),
    ],
)
async def test_c1_http_error_body_and_secret_never_cross_adapter_boundary(status, error_type):
    hostile = "SECRET_MARKER_C1 Bearer SECRET_MARKER_C1 http://internal-provider.invalid/private"

    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=hostile)

    provider = OpenAICompatibleProvider(
        api_key="SECRET_MARKER_C1",
        model_mapping=TEST_MODEL_MAPPING,
        transport=httpx.MockTransport(mock_handler),
    )
    with pytest.raises(error_type) as exc_info:
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(timeout_seconds=5.0),
        )
    public_error = str(exc_info.value)
    assert "SECRET_MARKER_C1" not in public_error
    assert "internal-provider.invalid" not in public_error
    assert "Bearer" not in public_error


@pytest.mark.asyncio
async def test_c1_redirect_is_not_followed_and_location_is_not_exposed():
    requests: list[httpx.Request] = []
    location = "https://redirect-target.invalid/private?token=SECRET_MARKER_C1"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(307, headers={"Location": location})

    provider = OpenAICompatibleProvider(
        api_key="SECRET_MARKER_C1",
        model_mapping=TEST_MODEL_MAPPING,
        transport=httpx.MockTransport(mock_handler),
    )
    with pytest.raises(ProviderRequestError) as exc_info:
        await provider.analyze(
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(timeout_seconds=5.0),
        )
    assert len(requests) == 1
    assert requests[0].url.host == "api.openai.com"
    assert requests[0].headers["Authorization"] == "Bearer SECRET_MARKER_C1"
    assert "redirect-target.invalid" not in str(exc_info.value)
    assert "SECRET_MARKER_C1" not in str(exc_info.value)


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
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key", model_mapping=TEST_MODEL_MAPPING, transport=transport
    )
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
    provider = OpenAICompatibleProvider(
        api_key="mock-api-key", model_mapping=TEST_MODEL_MAPPING, transport=transport
    )
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
        provider = OpenAICompatibleProvider(
            api_key=secret_key, model_mapping=TEST_MODEL_MAPPING, transport=transport
        )
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
            assert "Error containing" not in exc_str


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
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", base_url)
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "spawn-key-12345")
    monkeypatch.setattr(settings, "ai_provider_base_url", base_url)

    descriptor = ProviderDescriptor(
        provider_id="spawn_test_provider",
        provider_type="openai_compatible",
        config_profile="primary",
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
async def test_execution_deadline_starts_before_process_resource_setup():
    provider = ProviderDescriptor()
    config = ModelConfig(timeout_seconds=MIN_PROVIDER_TIMEOUT_SECONDS)
    recv_pipe = MagicMock()
    send_pipe = MagicMock()
    process = MagicMock()
    process.is_alive.return_value = False
    process.pid = None

    def delayed_pipe(*, duplex):
        assert duplex is False
        import time

        time.sleep(MIN_PROVIDER_TIMEOUT_SECONDS + 0.02)
        return recv_pipe, send_pipe

    with patch("multiprocessing.get_context") as get_context:
        context = get_context.return_value
        context.Pipe.side_effect = delayed_pipe
        context.Process.return_value = process
        with pytest.raises(ProviderTimeoutError, match="during process setup"):
            await provider_executor.execute(
                provider,
                agent_id="setup_deadline",
                system_prompt="sys",
                user_payload="{}",
                model_config=config,
            )

    process.start.assert_not_called()
    recv_pipe.close.assert_called_once()
    send_pipe.close.assert_called_once()


@pytest.mark.asyncio
async def test_global_concurrency_bounding():
    provider_executor.configure_concurrency(max_concurrent=2, queue_timeout_seconds=15.0)

    peak_workers = 0
    provider = SlowFixtureProvider()
    config = ModelConfig(timeout_seconds=10.0)

    async def call_agent(aid: str):
        res = await provider_executor._execute_test_provider_instance(
            provider,
            agent_id=aid,
            system_prompt="sys",
            user_payload='{"test": 1}',
            model_config=config,
        )
        return res

    tasks = [asyncio.create_task(call_agent(f"agent_{i}")) for i in range(6)]
    while not all(task.done() for task in tasks):
        peak_workers = max(peak_workers, active_provider_process_count())
        await asyncio.sleep(0.005)
    results = await asyncio.gather(*tasks)

    assert len(results) == 6
    assert 0 < peak_workers <= 2, f"Peak workers outside expected bound: {peak_workers}"
    assert active_provider_process_count() == 0

    provider_executor.configure_concurrency(max_concurrent=6, queue_timeout_seconds=15.0)


@pytest.mark.asyncio
async def test_backpressure_queue_timeout_rejects():
    provider_executor.configure_concurrency(max_concurrent=1, queue_timeout_seconds=0.05)

    provider = SlowFixtureProvider()
    config = ModelConfig(timeout_seconds=5.0)

    async def long_task():
        return await provider_executor._execute_test_provider_instance(
            provider,
            agent_id="slot_holder",
            system_prompt="sys",
            user_payload='{"test": 1}',
            model_config=config,
        )

    async def blocked_task():
        await asyncio.sleep(0.01)
        return await provider_executor._execute_test_provider_instance(
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
    orch = AIOrchestrator(provider=FixtureAIProvider().to_descriptor(), default_config=spoofed_config)
    res = await orch.analyze(ai_input)

    assert res.provider_provenance == "fixture"
    assert res.provider_provenance != "attacker_spoofed_provider"
    assert res.execution_provenance is not None
    assert res.execution_provenance.model_alias == "fast-advisory"
    assert res.execution_provenance.model_used == "fixture-v1"
    for _agent_id, a_res in res.agent_results.items():
        assert a_res.provider_provenance == "fixture"
        assert a_res.provider_provenance != "attacker_spoofed_provider"
        assert a_res.execution_provenance is not None
        assert a_res.execution_provenance.provider_id == "fixture"


@pytest.mark.asyncio
async def test_custom_fixture_descriptor_preserves_identity_end_to_end():
    descriptor = ProviderDescriptor(provider_id="primary-fixture")
    result = await AIOrchestrator(descriptor=descriptor).analyze(make_test_ai_input())
    assert result.provider_provenance == "primary-fixture"
    assert result.execution_provenance is not None
    assert result.execution_provenance.provider_id == "primary-fixture"
    assert result.execution_provenance.provider_type == "fixture"
    assert result.execution_provenance.model_used == "fixture-v1"
    assert all(
        agent.execution_provenance is not None
        and agent.execution_provenance.provider_id == "primary-fixture"
        for agent in result.agent_results.values()
    )


@pytest.mark.asyncio
async def test_zero_call_gate_has_no_execution_provenance():
    ai_input = make_test_ai_input()
    blocked = ai_input.model_copy(
        update={"kill_switch_context": ai_input.kill_switch_context.model_copy(update={"state": "ACTIVE"})}
    )
    result = await AIOrchestrator().analyze(blocked)
    assert result.execution_provenance is None
    assert result.agent_results == {}


@pytest.mark.asyncio
async def test_orchestrator_auth_failure_degrades_gracefully(monkeypatch: pytest.MonkeyPatch):
    calls = 0

    class AuthFailureServer(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal calls
            calls += 1
            size = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(size)
            body = b'{"error":"unauthorized"}'
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), AuthFailureServer)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    monkeypatch.setenv("AI_PROVIDER_API_KEY", "bad-key")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "bad-key")
    monkeypatch.setattr(settings, "ai_provider_base_url", f"http://127.0.0.1:{httpd.server_address[1]}")

    descriptor = ProviderDescriptor(
        provider_id="fail_auth_provider",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings=TEST_MODEL_MAPPING,
    )
    ai_input = make_test_ai_input()
    before = ai_input.model_dump(mode="json")
    try:
        result = await AIOrchestrator(
            descriptor=descriptor, default_config=ModelConfig(timeout_seconds=20.0, max_retries=3)
        ).analyze(ai_input)
        assert result.status == "UNAVAILABLE"
        assert calls == 7
        assert all(agent.status != "READY" for agent in result.agent_results.values())
        assert ai_input.model_dump(mode="json") == before
        assert result.execution_provenance is None
        assert active_provider_process_count() == 0
    finally:
        httpd.shutdown()
        httpd.server_close()


# ============================================================================
# 8. MOCK SERVER SPAWN: FULL ORCHESTRATION PIPELINE (6 AGENTS + METACONTROLLER)
# ============================================================================


@pytest.mark.asyncio
async def test_mock_server_spawn_full_orchestration_all_agents(monkeypatch: pytest.MonkeyPatch):
    """Verify complete analytical pipeline (6 agents + MetaController) across real spawn boundary."""
    called_agents = []
    called_models = []

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
            called_models.append(body["model"])
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
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", base_url)
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider_api_key", "all-agents-key")
    monkeypatch.setattr(settings, "ai_provider_base_url", base_url)

    descriptor = ProviderDescriptor(
        provider_id="mock_all_agents",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings={"fast-advisory": "test-model-fast-123"},
    )

    try:
        config = ModelConfig(provider="ATTACKER_FAKE_PROVIDER", timeout_seconds=20.0)
        ai_input = make_test_ai_input()
        orch = AIOrchestrator(descriptor=descriptor, default_config=config)

        res = await orch.analyze(ai_input)

        assert isinstance(res, AIAnalysisResult)
        assert res.status == "READY"
        assert res.provider_provenance == "mock_all_agents"
        assert res.execution_provenance is not None
        assert res.execution_provenance.model_dump() == {
            "provider_id": "mock_all_agents",
            "provider_type": "openai_compatible",
            "model_alias": "fast-advisory",
            "model_used": "test-model-fast-123",
            "mode": "external",
        }
        assert len(res.agent_results) == 6
        for _agent_id, a_res in res.agent_results.items():
            assert a_res.provider_provenance == "mock_all_agents"
            assert a_res.status == "READY"
            assert a_res.execution_provenance == res.execution_provenance

        assert len(called_agents) == 7  # 6 analytical agents + 1 MetaController
        assert called_models == ["test-model-fast-123"] * 7
        assert "ATTACKER_FAKE_PROVIDER" not in res.model_dump_json()
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

    settings = Settings()
    descriptor = ProviderDescriptor(
        provider_id="live_test",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings=settings.ai_model_mapping,
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


# ============================================================================
# 10. PHASE 6.2 ROUND 3 CORRECTIVE TESTS: TRUST BOUNDARY, ENDPOINT & DEADLINES
# ============================================================================


def test_model_construct_fixture_primary_rejected_at_factory_and_worker():
    """P1-201: model_construct bypass must fail revalidation in child worker and factory."""
    forged = ProviderDescriptor.model_construct(
        provider_id="forged_fixture",
        provider_type="fixture",
        config_profile="primary",
        model_bindings=(),
        request_schema_version="v1",
        response_schema_version="v1",
        capabilities=("structured_json",),
        enabled=True,
    )
    with pytest.raises(Exception) as exc_info:
        ProviderFactory.create_provider(forged)
    assert "fixture provider must use fixture config profile" in str(exc_info.value)


@pytest.mark.asyncio
async def test_model_construct_forged_descriptor_rejected_across_spawn_boundary():
    """P1-201: Forged descriptor sent across spawn boundary fails revalidation, zero calls made."""
    forged = ProviderDescriptor.model_construct(
        provider_id="forged_fixture_spawn",
        provider_type="fixture",
        config_profile="primary",
        model_bindings=(),
        request_schema_version="v1",
        response_schema_version="v1",
        capabilities=("structured_json",),
        enabled=True,
    )
    with pytest.raises((ProviderInternalError, Exception)) as exc:
        await analyze_with_controls(
            forged,
            agent_id="test_agent",
            system_prompt="system",
            user_payload="{}",
            model_config=ModelConfig(),
        )
    assert "fixture provider must use fixture config profile" in str(exc.value)
    assert active_provider_process_count() == 0


def test_model_construct_external_fixture_rejected():
    """P1-201: model_construct external with fixture profile fails revalidation."""
    from app.services.ai.provider import ModelBinding

    forged = ProviderDescriptor.model_construct(
        provider_id="forged_ext",
        provider_type="openai_compatible",
        config_profile="fixture",
        model_bindings=(ModelBinding(alias="fast-advisory", model="gpt-4o-mini"),),
        request_schema_version="v1",
        response_schema_version="v1",
        capabilities=("structured_json",),
        enabled=True,
    )
    with pytest.raises(Exception) as exc:
        ProviderFactory.create_provider(forged)
    assert "openai_compatible provider must use primary config profile" in str(exc.value)


def test_model_construct_invalid_bindings_rejected():
    """P1-201: model_construct invalid bindings fail defensive revalidation."""
    from app.services.ai.provider import ModelBinding

    # Empty bindings
    forged_empty = ProviderDescriptor.model_construct(
        provider_id="forged_empty",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings=(),
    )
    with pytest.raises(ValidationError):
        ProviderFactory.create_provider(forged_empty)

    # >16 bindings
    forged_17 = ProviderDescriptor.model_construct(
        provider_id="forged_17",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings=tuple(ModelBinding(alias=f"m{i}", model="gpt-4o") for i in range(17)),
    )
    with pytest.raises(ValidationError):
        ProviderFactory.create_provider(forged_17)


def test_descriptor_wire_dto_ipc_has_zero_urls_and_zero_secrets():
    """P1-202: Serialized descriptor / wire DTO must contain ZERO URLs and ZERO secrets."""
    secret = "SUPER_SECRET_AI_KEY_998877"
    url = "https://api.openai.com/v1/some_endpoint"
    descriptor = ProviderDescriptor(
        provider_id="ipc_test_provider",
        provider_type="openai_compatible",
        config_profile="primary",
        model_bindings={"fast-advisory": "gpt-4o-mini"},
    )
    dumped = descriptor.model_dump(mode="json")
    assert "base_url" not in dumped
    pickled = pickle.dumps(dumped)
    assert secret.encode() not in pickled
    assert url.encode() not in pickled
    assert b"http" not in pickled


def test_worker_active_secret_in_endpoint_rejected():
    """P1-202: Active API credential in URL path or hostname raises error and halts execution."""
    from app.services.ai.provider import validate_provider_base_url

    secret = "sk-live-secret-test-key-554433"
    with pytest.raises(ValueError, match="contains active API credential"):
        validate_provider_base_url(f"https://api.openai.com/v1/{secret}", active_secret=secret)

    with pytest.raises(ValueError, match="contains active API credential"):
        validate_provider_base_url(f"https://{secret}.openai.com/v1", active_secret=secret)


@pytest.mark.parametrize(
    "ws_url",
    [
        "https://example.com/a b",
        "https://example.com/%20",
        "https://example.com/a%20b",
        "https://example.com/%09",
        "https://example.com/%0a",
        "https://example.com/%0d",
        "https://example.com/\u2003",
        "https://example.com/%2520",
    ],
)
def test_url_whitespace_matrix_all_rejected(ws_url):
    """New P2: All whitespace variants (ASCII, Unicode, percent-encoded, double-encoded) are rejected."""
    from app.services.ai.provider import validate_provider_base_url

    with pytest.raises(ValueError):
        validate_provider_base_url(ws_url)


@pytest.mark.asyncio
async def test_deadline_terminates_resistant_worker_with_truthful_watchdog():
    """P2-217: Enforced execution deadline terminates resistant child; verified with TEST_WATCHDOG."""
    provider = CancellationResistantFixtureProvider()
    config = ModelConfig(timeout_seconds=0.25, max_retries=0)
    t0 = asyncio.get_running_loop().time()
    with pytest.raises(ProviderTimeoutError):
        await provider_executor._execute_test_provider_instance(
            provider,
            agent_id="resistant_worker_test",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
            timeout_seconds=0.25,
        )
    elapsed = asyncio.get_running_loop().time() - t0
    # Generous TEST_WATCHDOG (1.5s) to detect process hangs/leaks without claiming a non-real-time 0.360s ceiling
    TEST_WATCHDOG = 1.5
    assert elapsed < TEST_WATCHDOG, f"Watchdog exceeded: elapsed {elapsed:.3f}s >= {TEST_WATCHDOG}s"
    assert active_provider_process_count() == 0


# ============================================================================
# 11. ROUND 4 CORRECTIVE: DESCRIPTOR-ONLY PRODUCTION EXECUTION & VERIFIED TERMINATION
# ============================================================================


@pytest.mark.asyncio
async def test_provider_executor_execute_rejects_direct_openai_provider_before_spawn():
    """P1: ProviderExecutor.execute rejects OpenAIChatCompletionsProvider before spawn/network."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(500))
    real_provider = OpenAIChatCompletionsProvider(
        api_key="SUPER_SECRET_AI_KEY_12345",
        base_url="https://api.openai.com/v1",
        model_mapping=TEST_MODEL_MAPPING,
        transport=mock_transport,
    )
    with pytest.raises(
        ProviderRequestError,
        match="requires ProviderDescriptor; live OpenAIChatCompletionsProvider instances are prohibited",
    ):
        await provider_executor.execute(
            real_provider,  # type: ignore[arg-type]
            agent_id="test_agent",
            system_prompt="sys",
            user_payload="{}",
            model_config=ModelConfig(),
        )
    assert active_provider_process_count() == 0


@pytest.mark.asyncio
async def test_provider_executor_execute_rejects_direct_fixture_provider_before_spawn():
    """P1: ProviderExecutor.execute rejects FixtureAIProvider before spawn."""
    fixture_provider = FixtureAIProvider()
    with pytest.raises(
        ProviderRequestError,
        match="requires ProviderDescriptor; live FixtureAIProvider instances are prohibited",
    ):
        await provider_executor.execute(
            fixture_provider,  # type: ignore[arg-type]
            agent_id="test_agent",
            system_prompt="sys",
            user_payload="{}",
            model_config=ModelConfig(),
        )
    assert active_provider_process_count() == 0


@pytest.mark.asyncio
async def test_analyze_with_controls_rejects_direct_provider_instances():
    """P1: analyze_with_controls rejects direct provider instances before process handoff."""
    real_provider = OpenAIChatCompletionsProvider(
        api_key="KEY",
        base_url="https://api.openai.com/v1",
        model_mapping=TEST_MODEL_MAPPING,
    )
    with pytest.raises(
        ProviderRequestError,
        match="requires ProviderDescriptor; live OpenAIChatCompletionsProvider instances are prohibited",
    ):
        await analyze_with_controls(
            real_provider,  # type: ignore[arg-type]
            agent_id="test_agent",
            system_prompt="sys",
            user_payload="{}",
            model_config=ModelConfig(),
        )
    assert active_provider_process_count() == 0


def test_ai_orchestrator_init_rejects_direct_provider_instances():
    """P1: AIOrchestrator constructor rejects direct AIProvider instances."""
    fixture = FixtureAIProvider()
    with pytest.raises(
        ValueError,
        match="AIOrchestrator requires ProviderDescriptor; live FixtureAIProvider instances are prohibited",
    ):
        AIOrchestrator(provider=fixture)  # type: ignore[arg-type]

    real = OpenAIChatCompletionsProvider(
        api_key="KEY",
        base_url="https://api.openai.com/v1",
        model_mapping=TEST_MODEL_MAPPING,
    )
    with pytest.raises(
        ValueError,
        match="AIOrchestrator requires ProviderDescriptor; live OpenAIChatCompletionsProvider instances are prohibited",
    ):
        AIOrchestrator(provider=real)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_test_provider_executor_rejects_openai_provider():
    """P1: _execute_test_provider_instance strictly rejects external providers and credentials."""
    real = OpenAIChatCompletionsProvider(
        api_key="SECRET_KEY",
        base_url="https://api.openai.com/v1",
        model_mapping=TEST_MODEL_MAPPING,
    )
    with pytest.raises(
        ProviderRequestError,
        match="External provider OpenAIChatCompletionsProvider is strictly forbidden",
    ):
        await provider_executor._execute_test_provider_instance(
            real,  # type: ignore[arg-type]
            agent_id="test_agent",
            system_prompt="sys",
            user_payload="{}",
            model_config=ModelConfig(),
        )
    assert active_provider_process_count() == 0


@pytest.mark.asyncio
async def test_verified_worker_termination_failure_raises_and_retains_tracking(monkeypatch: pytest.MonkeyPatch):
    """P2-217: If child process terminate/kill fails, raise ProviderWorkerTerminationError and keep tracked."""
    import app.services.ai.execution as exec_mod

    original_terminate = exec_mod._terminate_worker

    def broken_terminate(process):
        # Do not kill the process, simulate unkillable zombie
        pass

    monkeypatch.setattr(exec_mod, "_terminate_worker", broken_terminate)

    provider = CancellationResistantFixtureProvider()
    config = ModelConfig(timeout_seconds=0.25, max_retries=0)

    try:
        pattern = "could not be terminated|is still alive after cleanup"
        with pytest.raises(ProviderWorkerTerminationError, match=pattern):
            await provider_executor._execute_test_provider_instance(
                provider,
                agent_id="unkillable_test",
                system_prompt="system",
                user_payload="{}",
                model_config=config,
                timeout_seconds=0.25,
            )
        # Verify process remained tracked in _ACTIVE_PROCESSES
        assert len(exec_mod._ACTIVE_PROCESSES) >= 1
    finally:
        # Cleanup any remaining live processes
        monkeypatch.undo()
        for p in list(exec_mod._ACTIVE_PROCESSES):
            with contextlib.suppress(Exception):
                original_terminate(p)
            exec_mod._ACTIVE_PROCESSES.discard(p)
        assert active_provider_process_count() == 0


@pytest.mark.asyncio
async def test_parent_cancellation_terminates_worker_and_cleans_up():
    """P2-217: Parent asyncio cancellation terminates child worker cleanly."""
    provider = CancellationResistantFixtureProvider()
    config = ModelConfig(timeout_seconds=10.0, max_retries=0)

    task = asyncio.create_task(
        provider_executor._execute_test_provider_instance(
            provider,
            agent_id="cancellation_test",
            system_prompt="system",
            user_payload="{}",
            model_config=config,
            timeout_seconds=10.0,
        )
    )
    # Wait for process to spawn
    await asyncio.sleep(0.3)
    assert active_provider_process_count() == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Assert worker terminated and cleaned up
    assert active_provider_process_count() == 0


# ==============================================================================
# 12. Corrective Round 4.1: Pre-Final Trust-Boundary Hardening
# ==============================================================================


def test_fixture_options_strict_typed_model_extra_forbid():
    """Section 3-6: FixtureProviderOptions rejects unknown/arbitrary/secret fields."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs are not permitted"):
        FixtureProviderOptions(secret="SUPER_SECRET_AI_KEY_12345")  # type: ignore[call-arg]

    for forbidden_key in ("api_key", "token", "password", "credential", "base_url", "custom_secret"):
        with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs are not permitted"):
            FixtureProviderOptions(**{forbidden_key: "leaked_val"})  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="Fixture agent IDs must not contain credential material"):
        FixtureProviderOptions(fail_agents=["sk-proj-super-secret-key-12345"])

    with pytest.raises(ValidationError, match="Fixture agent IDs must not contain credential material"):
        FixtureProviderOptions(agent_biases={"sk-bearer-token": "LONG"})


def test_fixture_options_nested_immutability():
    """Section 7: ProviderDescriptor and nested FixtureProviderOptions are strictly immutable."""
    desc = ProviderDescriptor(
        provider_id="immutable_test",
        provider_type="fixture",
        config_profile="fixture",
        fixture_options=FixtureProviderOptions(
            fail_agents=["macro_analyst", "risk_analyst"],
            agent_biases={"macro_analyst": "LONG"},
            agent_strengths={"macro_analyst": "STRONG"},
        ),
    )
    assert desc.fixture_options is not None

    # Mutation of descriptor field blocked
    with pytest.raises(ValidationError, match="frozen"):
        desc.fixture_options = None  # type: ignore[misc]

    # Reassignment on FixtureProviderOptions blocked
    with pytest.raises(ValidationError, match="frozen"):
        desc.fixture_options.fail_agents = ()  # type: ignore[misc]

    # In-place mutations blocked on immutable tuples
    with pytest.raises(AttributeError):
        desc.fixture_options.fail_agents.append("new_agent")  # type: ignore[attr-defined]

    with pytest.raises(TypeError, match="does not support item assignment"):
        desc.fixture_options.fail_agents[0] = "mutated"  # type: ignore[index]

    with pytest.raises(TypeError, match="does not support item assignment"):
        desc.fixture_options.agent_biases[0] = ("macro_analyst", "SHORT")  # type: ignore[index]

    with pytest.raises(TypeError, match="does not support item assignment"):
        desc.fixture_options.agent_biases["macro_analyst"] = "SHORT"  # type: ignore[index]


def test_fixture_options_size_bounds():
    """Section 8: FixtureProviderOptions enforces strict schema bounds on payloads."""
    too_many = [f"agent_{i:03d}" for i in range(35)]
    with pytest.raises(ValidationError, match="too_long|at most 32 items"):
        FixtureProviderOptions(fail_agents=too_many)

    long_agent = "a" * 65
    with pytest.raises(ValidationError, match="too_long|at most 64 characters"):
        FixtureProviderOptions(fail_agents=[long_agent])

    huge_agent = "a" * 100_000
    with pytest.raises(ValidationError):
        FixtureProviderOptions(fail_agents=[huge_agent])


def test_fixture_options_deterministic_round_trip():
    """Section 10: Full round-trip preserves deterministic test behavior."""
    p1 = FixtureAIProvider(
        provider_id="round_trip_fixture",
        fail_agents={"macro_analyst"},
        malformed_json_agents={"risk_analyst"},
        agent_biases={"smc_analyst": "LONG"},
        agent_strengths={"smc_analyst": "STRONG"},
        token_mode="huge",
        oversized_mode="content",
    )
    desc = p1.to_descriptor()
    assert isinstance(desc.fixture_options, FixtureProviderOptions)

    dumped = desc.model_dump(mode="json")
    serialized = json.dumps(dumped)
    assert "secret" not in serialized
    assert "api_key" not in serialized

    desc2 = ProviderDescriptor.model_validate(json.loads(serialized))
    p2 = ProviderFactory.create_provider(desc2)
    assert isinstance(p2, FixtureAIProvider)
    assert p2.fail_agents == p1.fail_agents
    assert p2.malformed_json_agents == p1.malformed_json_agents
    assert p2.agent_biases == p1.agent_biases
    assert p2.agent_strengths == p1.agent_strengths
    assert p2.token_mode == p1.token_mode
    assert p2.oversized_mode == p1.oversized_mode


@pytest.mark.asyncio
async def test_failed_worker_termination_retains_slot_and_blocks_second_worker(monkeypatch):
    """Sections 11-17: Surviving worker retains capacity slot; second execution fails closed."""
    import app.services.ai.execution as exec_mod
    from app.services.ai.execution import ProviderExecutor

    test_executor = ProviderExecutor(max_concurrent=1, queue_timeout_seconds=0.25)

    original_terminate = exec_mod._terminate_worker

    def mock_unkillable_worker(p):
        raise ProviderWorkerTerminationError(f"Worker {p.pid} simulated unkillable")

    monkeypatch.setattr(exec_mod, "_terminate_worker", mock_unkillable_worker)

    provider = CancellationResistantFixtureProvider()
    config = ModelConfig(timeout_seconds=0.25, max_retries=0)

    try:
        with pytest.raises(ProviderWorkerTerminationError):
            await test_executor._execute_test_provider_instance(
                provider,
                agent_id="surviving_worker_slot_test",
                system_prompt="system",
                user_payload="{}",
                model_config=config,
                timeout_seconds=0.25,
            )

        assert len(exec_mod._ACTIVE_PROCESSES) >= 1
        assert len(exec_mod._SURVIVING_PROCESSES) >= 1
        assert test_executor.available_slots == 0

        with pytest.raises(ProviderCapacityExhausted, match="Provider capacity exhausted"):
            await test_executor._execute_test_provider_instance(
                provider,
                agent_id="second_call_must_fail",
                system_prompt="system",
                user_payload="{}",
                model_config=config,
                timeout_seconds=0.25,
            )

        assert active_provider_process_count() <= 1
    finally:
        monkeypatch.undo()
        for p in list(exec_mod._ACTIVE_PROCESSES):
            with contextlib.suppress(Exception):
                original_terminate(p)
            exec_mod._ACTIVE_PROCESSES.discard(p)
            exec_mod._SURVIVING_PROCESSES.discard(p)
        exec_mod.reap_surviving_processes(test_executor.limiter)


def test_spawn_safe_test_provider_rejects_sensitive_attributes():
    """Sections 18-20: Test provider execution strictly rejects sensitive state."""
    class LeakyTestProviderSecret(SpawnSafeTestProvider):
        def __init__(self):
            super().__init__()
            self.secret = "XYZ_SECRET"

        async def analyze(self, **kwargs):
            return ProviderResult(
                content="{}", raw_payload={}, prompt_tokens=1, completion_tokens=1, total_tokens=2, model="test"
            )

    class LeakyTestProviderToken(SpawnSafeTestProvider):
        def __init__(self):
            super().__init__()
            self.token = "XYZ_TOKEN"

        async def analyze(self, **kwargs):
            return ProviderResult(
                content="{}", raw_payload={}, prompt_tokens=1, completion_tokens=1, total_tokens=2, model="test"
            )

    class LeakyTestProviderPassword(SpawnSafeTestProvider):
        def __init__(self):
            super().__init__()
            self.password = "XYZ_PASS"

        async def analyze(self, **kwargs):
            return ProviderResult(
                content="{}", raw_payload={}, prompt_tokens=1, completion_tokens=1, total_tokens=2, model="test"
            )

    class LeakyTestProviderCredValue(SpawnSafeTestProvider):
        def __init__(self):
            super().__init__()
            self.custom_val = "sk-proj-secret-key-12345"

        async def analyze(self, **kwargs):
            return ProviderResult(
                content="{}", raw_payload={}, prompt_tokens=1, completion_tokens=1, total_tokens=2, model="test"
            )

    from app.services.ai.execution import _validate_test_provider_instance

    with pytest.raises(ProviderRequestError, match="forbidden sensitive attribute: 'secret'"):
        _validate_test_provider_instance(LeakyTestProviderSecret())

    with pytest.raises(ProviderRequestError, match="forbidden sensitive attribute: 'token'"):
        _validate_test_provider_instance(LeakyTestProviderToken())

    with pytest.raises(ProviderRequestError, match="forbidden sensitive attribute: 'password'"):
        _validate_test_provider_instance(LeakyTestProviderPassword())

    with pytest.raises(ProviderRequestError, match="contains credential material"):
        _validate_test_provider_instance(LeakyTestProviderCredValue())


def test_test_only_path_unreachable_from_production():
    """Section 19: _execute_test_provider_instance is never called from production code."""
    import inspect

    from app.services.ai import agents, orchestrator, provider

    for mod in (agents, orchestrator, provider):
        source = inspect.getsource(mod)
        assert "_execute_test_provider_instance" not in source, f"Production module {mod.__name__} calls test method"


def test_static_descriptor_only_type_contract():
    """Sections 22-23: Production APIs statically type ProviderDescriptor."""
    import inspect

    from app.services.ai.agents import BaseAnalyticalAgent, MetaController
    from app.services.ai.execution import ProviderExecutor
    from app.services.ai.orchestrator import AIOrchestrator
    from app.services.ai.provider import ProviderDescriptor, analyze_with_controls

    sig_exec = inspect.signature(ProviderExecutor.execute)
    assert sig_exec.parameters["provider"].annotation in ("ProviderDescriptor", ProviderDescriptor)

    sig_ctrl = inspect.signature(analyze_with_controls)
    assert sig_ctrl.parameters["provider"].annotation in ("ProviderDescriptor", ProviderDescriptor)

    sig_agent = inspect.signature(BaseAnalyticalAgent.execute)
    assert sig_agent.parameters["provider"].annotation in ("ProviderDescriptor", ProviderDescriptor)

    sig_meta = inspect.signature(MetaController.execute)
    assert sig_meta.parameters["provider"].annotation in ("ProviderDescriptor", ProviderDescriptor)

    sig_orch = inspect.signature(AIOrchestrator.__init__)
    assert "ProviderDescriptor" in str(sig_orch.parameters["provider"].annotation)
