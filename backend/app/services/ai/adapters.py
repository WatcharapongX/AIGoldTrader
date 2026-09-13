"""Real LLM Provider adapters and worker-side ProviderFactory.

Implements production-ready external model adapters (e.g. OpenAI-compatible Chat Completions)
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
    MAX_PROVIDER_OUTPUT_BYTES,
    AIProvider,
    FixtureAIProvider,
    ModelConfig,
    OutputBudgetExceeded,
    ProviderAuthError,
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

DEFAULT_MODEL_MAPPING: dict[str, str] = {
    "fast-advisory": "gpt-4o-mini",
    "reasoning-advisory": "gpt-4o",
    "deep-analysis": "gpt-4o",
}


class OpenAICompatibleProvider(AIProvider):
    """External LLM adapter using the standard OpenAI-compatible Chat Completions API.

    Constructed worker-side; supports OpenAI, Gemini OpenAI-compatibility endpoint,
    DeepSeek, Groq, Ollama, vLLM, and any compliant REST server.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model_mapping: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_mapping = dict(model_mapping or DEFAULT_MODEL_MAPPING)
        self.transport = transport

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
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(timeout),
            ) as client:
                response = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            msg = mask_secret_text(f"Provider request timed out after {timeout}s: {exc}", [self.api_key])
            raise ProviderTimeoutError(msg) from exc
        except (httpx.ConnectError, httpx.NetworkError, httpx.ProtocolError) as exc:
            msg = mask_secret_text(f"Provider network error connecting to {self.base_url}: {exc}", [self.api_key])
            raise ProviderNetworkError(msg) from exc
        except Exception as exc:
            msg = mask_secret_text(f"Provider HTTP request failed: {exc}", [self.api_key])
            raise ProviderNetworkError(msg) from exc

        duration_ms = (time.perf_counter() - t0) * 1000

        # Handle HTTP status codes
        if response.status_code in (401, 403):
            msg = mask_secret_text(
                f"Provider authentication failure (HTTP {response.status_code}): {response.text[:200]}",
                [self.api_key],
            )
            raise ProviderAuthError(msg)

        if response.status_code == 429:
            msg = mask_secret_text(
                f"Provider rate limit exceeded (HTTP 429): {response.text[:200]}",
                [self.api_key],
            )
            raise ProviderRateLimitError(msg)

        if 400 <= response.status_code < 500:
            msg = mask_secret_text(
                f"Provider rejected request with HTTP {response.status_code}: {response.text[:200]}",
                [self.api_key],
            )
            raise ProviderRequestError(msg)

        if response.status_code >= 500:
            msg = mask_secret_text(
                f"Provider internal server error (HTTP {response.status_code}): {response.text[:200]}",
                [self.api_key],
            )
            raise ProviderNetworkError(msg)

        # Parse valid 200 response
        try:
            resp_json = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderSchemaError(f"Provider returned malformed JSON: {exc}") from exc

        choices = resp_json.get("choices")
        if not choices or not isinstance(choices, list):
            raise ProviderSchemaError("Provider response missing 'choices' array")

        first_choice = choices[0]
        message = first_choice.get("message") or {}
        content = message.get("content") or ""

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

        # Extract and validate token usage
        usage = resp_json.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        # Invariant: non-negative and arithmetic consistency
        prompt_tokens = max(int(prompt_tokens), 0)
        completion_tokens = max(int(completion_tokens), 0)
        total_tokens = prompt_tokens + completion_tokens

        return ProviderResult(
            content=content,
            raw_payload=raw_payload,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            model_used=vendor_model,
        )


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
        if not descriptor.enabled:
            raise ProviderAuthError(f"AI Provider '{descriptor.provider_id}' is disabled")

        if descriptor.provider_type == "fixture":
            return FixtureAIProvider()

        if descriptor.provider_type == "openai_compatible":
            # Resolve secret reference
            cred_ref = descriptor.credential_ref or "AI_PROVIDER_API_KEY"
            api_key = os.environ.get(cred_ref, "").strip()
            if not api_key:
                raise ProviderAuthError(
                    f"AI Provider credential '{cred_ref}' is missing or empty in environment"
                )

            # Resolve base URL reference
            base_url_ref = descriptor.base_url_ref or "AI_PROVIDER_BASE_URL"
            base_url = os.environ.get(base_url_ref, "https://api.openai.com/v1").strip()

            # Resolve model mapping
            mapping = dict(DEFAULT_MODEL_MAPPING)
            for alias in ("fast-advisory", "reasoning-advisory", "deep-analysis"):
                env_key = f"AI_MODEL_{alias.upper().replace('-', '_')}"
                if os.environ.get(env_key):
                    mapping[alias] = os.environ[env_key]

            transport = cls._custom_transports.get(descriptor.provider_id)
            return OpenAICompatibleProvider(
                api_key=api_key,
                base_url=base_url,
                model_mapping=mapping,
                transport=transport,
            )

        raise ProviderInternalError(f"Unsupported provider_type: '{descriptor.provider_type}'")
