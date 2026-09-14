"""Real LLM Provider adapters and worker-side ProviderFactory.

Implements production-ready external model adapters (OpenAI-compatible Chat Completions subset)
constructed strictly worker-side to satisfy Windows multiprocessing picklability (P3-066).
Zero credentials or vendor clients ever cross the parent-child spawn boundary.
"""

import json
import logging
import os
import time
from typing import Any

import httpx

from app.core.masking import mask_secret_text
from app.services.ai.provider import (
    MAX_PROVIDER_HTTP_RESPONSE_BYTES,
    MAX_PROVIDER_OUTPUT_BYTES,
    AIProvider,
    FixtureAIProvider,
    ModelConfig,
    OutputBudgetExceeded,
    ProviderAuthError,
    ProviderBudgetExceeded,
    ProviderDescriptor,
    ProviderInternalError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResult,
    ProviderSchemaError,
    ProviderTimeoutError,
)

logger = logging.getLogger(__name__)

class ProviderConfigResolver:
    """Worker-side resolution of secrets and endpoints from Settings or environment.

    Resolves secrets and network base URLs exclusively inside the child worker process
    based on symbolic config profiles. Never exposes raw secrets or arbitrary endpoint
    URLs across IPC pipes or in ProviderDescriptors.
    """

    _custom_endpoints: dict[str, str] = {}

    @classmethod
    def register_test_endpoint(cls, config_profile: str, base_url: str) -> None:
        cls._custom_endpoints[config_profile] = base_url

    @classmethod
    def clear_test_endpoints(cls) -> None:
        cls._custom_endpoints.clear()

    @classmethod
    def resolve_secret(cls, config_profile: str) -> str:
        if config_profile == "fixture":
            return ""
        if config_profile == "primary":
            from app.core.config import get_settings

            try:
                settings = get_settings()
                api_key = settings.ai_provider_api_key.strip()
            except Exception:
                api_key = ""
            if not api_key:
                api_key = os.environ.get("AI_PROVIDER_API_KEY", "").strip()
            if not api_key:
                raise ProviderAuthError("Configured external provider credential is unavailable")
            return api_key
        raise ProviderAuthError(f"Unsupported config profile for secret: '{config_profile}'")

    @classmethod
    def resolve_base_url(cls, config_profile: str) -> str:
        if config_profile == "fixture":
            return ""
        if config_profile == "primary":
            if "primary" in cls._custom_endpoints:
                return cls._custom_endpoints["primary"]
            from app.core.config import get_settings

            try:
                settings = get_settings()
                base_url = settings.ai_provider_base_url.strip()
            except Exception:
                base_url = ""
            if not base_url:
                base_url = os.environ.get("AI_PROVIDER_BASE_URL", "").strip()
            if not base_url:
                base_url = "https://api.openai.com/v1"
            return base_url
        raise ProviderAuthError(f"Unsupported config profile for base_url: '{config_profile}'")

    @classmethod
    def resolve_external_config(cls, config_profile: str) -> tuple[str, str]:
        """Resolve and validate both secret and network endpoint together worker-side."""
        from app.services.ai.provider import validate_provider_base_url

        api_key = cls.resolve_secret(config_profile)
        raw_base_url = cls.resolve_base_url(config_profile)
        try:
            validated_url = validate_provider_base_url(raw_base_url, active_secret=api_key)
        except ValueError as exc:
            raise ProviderAuthError(f"Invalid external provider base_url configuration: {exc}") from exc
        return api_key, validated_url


class OpenAIChatCompletionsProvider(AIProvider):
    """External LLM adapter using the standard OpenAI-compatible Chat Completions subset.

    Requires:
    - Chat Completions endpoint (POST /chat/completions)
    - JSON response format support
    - Valid usage telemetry object
    """

    def __init__(
        self,
        api_key: str,
        model_mapping: dict[str, str],
        base_url: str = "https://api.openai.com/v1",
        transport: httpx.AsyncBaseTransport | None = None,
        provider_id: str = "configured_external",
    ):
        if not model_mapping:
            raise ValueError("External provider requires explicit non-empty model mapping")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_mapping = dict(model_mapping)
        self.transport = transport
        self.provider_id = provider_id

    async def analyze(
        self,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: ModelConfig,
        timeout_seconds: float | None = None,
    ) -> ProviderResult:
        vendor_model = self.model_mapping.get(model_config.model_alias)
        if not vendor_model:
            raise ProviderSchemaError(
                f"Unknown model_alias '{model_config.model_alias}' for OpenAICompatibleProvider. "
                f"Available aliases: {list(self.model_mapping.keys())}"
            )

        timeout = timeout_seconds or model_config.timeout_seconds
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": vendor_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            "response_format": {"type": "json_object"},
            "temperature": float(model_config.temperature),
            "max_tokens": model_config.max_output_tokens,
        }

        t0 = time.perf_counter()
        response_status: int = 0
        chunks: list[bytes] = []
        total_http_bytes: int = 0

        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(timeout),
            ) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    response_status = response.status_code
                    async for chunk in response.aiter_bytes():
                        total_http_bytes += len(chunk)
                        if total_http_bytes > MAX_PROVIDER_HTTP_RESPONSE_BYTES:
                            raise ProviderBudgetExceeded(
                                f"Provider HTTP response entity exceeded limit: "
                                f"{total_http_bytes} > {MAX_PROVIDER_HTTP_RESPONSE_BYTES}"
                            )
                        chunks.append(chunk)
        except httpx.TimeoutException as exc:
            msg = mask_secret_text(f"Provider request timed out after {timeout}s: {exc}", [self.api_key])
            raise ProviderTimeoutError(msg) from exc
        except (httpx.ConnectError, httpx.NetworkError, httpx.ProtocolError) as exc:
            msg = mask_secret_text(
                f"Provider network error: provider_id={self.provider_id}, error_type={type(exc).__name__}",
                [self.api_key],
            )
            raise ProviderNetworkError(msg) from exc
        except ProviderBudgetExceeded:
            raise
        except Exception as exc:
            msg = mask_secret_text(f"Provider HTTP request failed: {exc}", [self.api_key])
            raise ProviderNetworkError(msg) from exc

        duration_ms = (time.perf_counter() - t0) * 1000
        raw_body = b"".join(chunks)
        body_text = raw_body.decode("utf-8", errors="replace")

        # Handle HTTP status codes
        if response_status in (401, 403):
            msg = mask_secret_text(
                f"Provider authentication failure (HTTP {response_status}): {body_text[:200]}",
                [self.api_key],
            )
            raise ProviderAuthError(msg)

        if response_status == 429:
            msg = mask_secret_text(
                f"Provider rate limit exceeded (HTTP 429): {body_text[:200]}",
                [self.api_key],
            )
            raise ProviderRateLimitError(msg)

        if 400 <= response_status < 500:
            msg = mask_secret_text(
                f"Provider rejected request with HTTP {response_status}: {body_text[:200]}",
                [self.api_key],
            )
            raise ProviderRequestError(msg)

        if response_status >= 500:
            msg = mask_secret_text(
                f"Provider internal server error (HTTP {response_status}): {body_text[:200]}",
                [self.api_key],
            )
            raise ProviderNetworkError(msg)

        # Parse valid 200 response
        try:
            resp_json = json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise ProviderSchemaError(f"Provider returned malformed JSON: {exc}") from exc

        if not isinstance(resp_json, dict):
            raise ProviderSchemaError("Provider response is not a JSON object")

        choices = resp_json.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            raise ProviderSchemaError("Provider response missing or empty 'choices' list")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ProviderSchemaError("Provider response choice item is not an object")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ProviderSchemaError("Provider response missing 'message' object")

        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderSchemaError("Provider response missing 'content' string")

        # Enforce output byte limit before JSON parsing
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > MAX_PROVIDER_OUTPUT_BYTES:
            raise OutputBudgetExceeded(
                f"Provider raw content exceeded output budget: {content_bytes} > {MAX_PROVIDER_OUTPUT_BYTES}"
            )

        # Parse structured JSON payload
        try:
            raw_payload = json.loads(content)
            if not isinstance(raw_payload, dict):
                raise ProviderSchemaError("Provider content is valid JSON but not a JSON object")
        except json.JSONDecodeError as exc:
            raise ProviderSchemaError(f"Provider content failed JSON parsing: {exc}") from exc

        raw_payload_bytes = len(
            json.dumps(raw_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode(
                "utf-8"
            )
        )
        if raw_payload_bytes > MAX_PROVIDER_OUTPUT_BYTES:
            raise OutputBudgetExceeded(
                f"Provider structured payload exceeded output budget: "
                f"{raw_payload_bytes} > {MAX_PROVIDER_OUTPUT_BYTES}"
            )

        # Extract and validate token usage strictly
        usage = resp_json.get("usage")
        if not isinstance(usage, dict):
            raise ProviderSchemaError("Provider response missing required 'usage' object")

        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if field not in usage:
                raise ProviderSchemaError(f"Provider usage object missing required field '{field}'")
            val = usage[field]
            if type(val) is not int:
                raise ProviderSchemaError(
                    f"Provider usage field '{field}' must be integer, got {type(val).__name__}"
                )
            if val < 0:
                raise ProviderSchemaError(f"Provider usage field '{field}' must be non-negative, got {val}")

        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        total_tokens = usage["total_tokens"]

        if total_tokens != prompt_tokens + completion_tokens:
            raise ProviderSchemaError(
                f"Vendor token usage inconsistent: total_tokens ({total_tokens}) != "
                f"prompt_tokens ({prompt_tokens}) + completion_tokens ({completion_tokens})"
            )

        return ProviderResult(
            content=content,
            raw_payload=raw_payload,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            provider_id=self.provider_id,
            provider_type="openai_compatible",
            model_used=vendor_model,
        )


OpenAICompatibleProvider = OpenAIChatCompletionsProvider


class ProviderFactory:
    """Worker-side factory for instantiating AI providers from ProviderDescriptors.

    Runs strictly inside the child worker process.
    Resolves secrets from local process environment; never receives live client instances from parent.
    """

    _custom_transports: dict[str, httpx.AsyncBaseTransport] = {}

    @classmethod
    def register_test_transport(cls, provider_id: str, transport: httpx.AsyncBaseTransport) -> None:
        """Register a mock transport for deterministic testing without external network."""
        cls._custom_transports[provider_id] = transport

    @classmethod
    def clear_test_transports(cls) -> None:
        cls._custom_transports.clear()

    @classmethod
    def create_provider(cls, descriptor: ProviderDescriptor) -> AIProvider:
        """Construct provider adapter from descriptor inside the worker process."""
        from pydantic import BaseModel

        # Defensive revalidation from plain dictionary to prevent model_construct bypass
        if isinstance(descriptor, BaseModel):
            descriptor = ProviderDescriptor.model_validate(descriptor.model_dump(mode="json"))
        elif isinstance(descriptor, dict):
            descriptor = ProviderDescriptor.model_validate(descriptor)
        else:
            raise ProviderInternalError(f"Invalid descriptor type: {type(descriptor)}")

        if not descriptor.enabled:
            raise ProviderAuthError(f"AI Provider '{descriptor.provider_id}' is disabled")

        if descriptor.provider_type == "fixture":
            opts = getattr(descriptor, "fixture_options", None) or {}
            return FixtureAIProvider(
                provider_id=descriptor.provider_id,
                fail_agents=set(opts.get("fail_agents", ())),
                malformed_json_agents=set(opts.get("malformed_json_agents", ())),
                schema_invalid_agents=set(opts.get("schema_invalid_agents", ())),
                injection_agents=set(opts.get("injection_agents", ())),
                timeout_agents=set(opts.get("timeout_agents", ())),
                hanging_agents=set(opts.get("hanging_agents", ())),
                token_budget_exceeded_agents=set(opts.get("token_budget_exceeded_agents", ())),
                agent_biases=dict(opts.get("agent_biases", {})),
                agent_strengths=dict(opts.get("agent_strengths", {})),
                token_mode=opts.get("token_mode"),
                oversized_mode=opts.get("oversized_mode"),
            )

        if descriptor.provider_type == "openai_compatible":
            api_key, base_url = ProviderConfigResolver.resolve_external_config(descriptor.config_profile)
            mapping = descriptor.model_mapping

            transport = cls._custom_transports.get(descriptor.provider_id)
            return OpenAIChatCompletionsProvider(
                api_key=api_key,
                base_url=base_url,
                model_mapping=mapping,
                transport=transport,
                provider_id=descriptor.provider_id,
            )

        raise ProviderInternalError(f"Unsupported provider_type: '{descriptor.provider_type}'")
