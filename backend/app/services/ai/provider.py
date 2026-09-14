"""AI Provider abstraction and deterministic fixture implementation for testing."""

import abc
import asyncio
import datetime as dt
import json
import logging
import re
import time
from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.ai.domain import (
    META_CONTROLLER_ID,
    PROMPT_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
MAX_INPUT_BYTES_PER_AGENT = 20_000
MAX_PROVIDER_OUTPUT_BYTES = 10_000
MAX_PROVIDER_HTTP_RESPONSE_BYTES = 50_000
# Measured Windows spawn-heavy runs exceeded 0.10s before useful worker execution;
# 0.25s is the minimum truthful isolated-process execution budget on this runtime.
MIN_PROVIDER_TIMEOUT_SECONDS = 0.25

_SAFE_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_CREDENTIAL_MARKERS = ("authorization", "bearer", "api_key", "apikey", "credential", "password", "secret", "token")


def _looks_like_credential(value: str) -> bool:
    lowered = value.casefold()
    return lowered.startswith(("sk-", "sk_", "aiza")) or any(marker in lowered for marker in _CREDENTIAL_MARKERS)


def sanitize_provider_url_for_logging(value: str) -> str:
    """Return a URL safe for diagnostics, stripping userinfo, query, and fragment."""
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        if not parsed.scheme or not host:
            return "<invalid-provider-url>"
        display_host = f"[{host}]" if ":" in host else host
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit((parsed.scheme, f"{display_host}{port}", parsed.path, "", ""))
    except (TypeError, ValueError):
        return "<invalid-provider-url>"


class AIProviderError(Exception):
    """Base exception for AI provider failures."""


class ProviderTimeoutError(AIProviderError, TimeoutError):
    """Execution deadline or timeout exhausted."""


class ProviderNetworkError(AIProviderError):
    """Low-level network, TLS, or DNS error connecting to provider."""


class ProviderAuthError(AIProviderError):
    """Authentication or authorization failure (401/403 or missing credentials)."""


class ProviderRateLimitError(AIProviderError):
    """Provider rate limit / 429 quota exhaustion."""


class ProviderCapacityExhausted(AIProviderError):
    """Local server-side concurrent worker slot capacity exhausted."""


class ProviderRequestError(AIProviderError):
    """Invalid client request payload or schema (4xx)."""


class ProviderSchemaError(AIProviderError):
    """Provider output failed schema validation."""


class ProviderBudgetExceeded(AIProviderError):
    """Provider exceeded token or byte limits."""


class ProviderInternalError(AIProviderError):
    """Unhandled internal provider or worker error."""


class ProviderWorkerTerminationError(ProviderInternalError):
    """Worker process termination failure (process remained alive after SIGTERM/SIGKILL)."""


class InputBudgetExceeded(ProviderBudgetExceeded, ValueError):
    """Serialized provider input exceeds the safe local boundary."""


class OutputBudgetExceeded(ProviderBudgetExceeded, ValueError):
    """Provider output exceeds the safe local boundary."""


class ModelBinding(BaseModel):
    """One immutable, bounded alias-to-vendor-model mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alias: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/:-]*$")

    @field_validator("model")
    @classmethod
    def reject_secret_like_model_ids(cls, value: str) -> str:
        if "://" in value or _looks_like_credential(value):
            raise ValueError("Vendor model identifier must not contain URLs or credential material")
        return value

    @field_validator("alias")
    @classmethod
    def reject_secret_like_aliases(cls, value: str) -> str:
        if _looks_like_credential(value):
            raise ValueError("Model alias must not contain credential material")
        return value


def validate_provider_base_url(value: str, active_secret: str | None = None) -> str:
    """Validate external provider base_url strictly.

    Rejects:
    - Whitespace: leading, trailing, internal ASCII space, tabs, newlines, Unicode whitespace.
    - Percent-encoded whitespace: %20, %09, %0a, %0A, %0d, %0D, and recursive/double-decoded whitespace.
    - Control characters (ord < 32 or ord == 127).
    - Userinfo (username, password).
    - Query parameters or fragments.
    - Non-localhost plain HTTP (allowed only for localhost, 127.0.0.1, ::1).
    - Active API secret in URL path or hostname (if active_secret provided).
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Provider base_url must be a non-empty string")

    # 1. Reject leading/trailing whitespace
    if value != value.strip():
        raise ValueError("Provider base_url must not contain leading or trailing whitespace")

    # 2. Reject internal ASCII or Unicode whitespace
    if any(char.isspace() for char in value):
        raise ValueError("Provider base_url must not contain whitespace")

    # 3. Reject percent-encoded whitespace and control characters (check recursive decoding)
    current = value
    for _ in range(3):
        decoded = unquote(current)
        if any(char.isspace() for char in decoded):
            raise ValueError("Provider base_url must not contain percent-encoded whitespace")
        if any(ord(char) < 32 or ord(char) == 127 for char in decoded):
            raise ValueError("Provider base_url must not contain control characters")
        if decoded == current:
            break
        current = decoded

    # 4. URL structure validation via urlsplit
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Provider base_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Provider base_url must not contain userinfo")
    if parsed.query or parsed.fragment:
        raise ValueError("Provider base_url must not contain a query or fragment")
    if parsed.scheme == "http" and parsed.hostname.casefold() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Plain HTTP provider base_url is allowed only for localhost integration")
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("Provider base_url contains an invalid port") from None

    # 5. Active secret in endpoint check
    if active_secret and active_secret.strip():
        secret_clean = active_secret.strip()
        if secret_clean in value or secret_clean in current:
            raise ValueError("Provider base_url contains active API credential")

    return value.rstrip("/")


class ProviderDescriptor(BaseModel):
    """Strict, immutable, serializable descriptor for AI providers.

    Contains configuration identity and references only; NEVER raw secrets, arbitrary URLs,
    or live client objects.
    Survives Windows spawn multiprocessing boundary and JSON serialization.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(
        default="default_provider", min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$"
    )
    provider_type: Literal["fixture", "openai_compatible"] = "fixture"
    config_profile: Literal["primary", "fixture"] = "fixture"
    model_bindings: tuple[ModelBinding, ...] = Field(default_factory=tuple, max_length=16)
    request_schema_version: str = Field(
        default="v1", min_length=1, max_length=16, pattern=r"^[a-z0-9][a-z0-9_.-]*$"
    )
    response_schema_version: str = Field(
        default="v1", min_length=1, max_length=16, pattern=r"^[a-z0-9][a-z0-9_.-]*$"
    )
    capabilities: tuple[
        Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.-]*$")], ...
    ] = Field(default=("structured_json", "system_prompt"), max_length=16)
    enabled: bool = True
    live_external_only: bool = False
    fixture_options: dict[str, Any] = Field(default_factory=dict)

    validate_base_url = staticmethod(validate_provider_base_url)

    @field_validator("model_bindings", mode="before")
    @classmethod
    def normalize_model_bindings(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return tuple({"alias": alias, "model": model} for alias, model in value.items())
        return value

    @field_validator("provider_id", "request_schema_version", "response_schema_version")
    @classmethod
    def reject_secret_like_identity_fields(cls, value: str) -> str:
        if _looks_like_credential(value):
            raise ValueError("Provider identity fields must not contain credential material")
        return value

    @field_validator("capabilities")
    @classmethod
    def reject_secret_like_capabilities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(_looks_like_credential(value) for value in values):
            raise ValueError("Provider capabilities must not contain credential material")
        return values

    @model_validator(mode="after")
    def validate_descriptor_invariants(self):
        if self.provider_type == "fixture":
            if self.config_profile != "fixture":
                raise ValueError("fixture provider must use fixture config profile")
            if self.model_bindings:
                raise ValueError("fixture provider must not define external model bindings")
        else:
            if self.config_profile != "primary":
                raise ValueError("openai_compatible provider must use primary config profile")
            if not self.model_bindings:
                raise ValueError("openai_compatible provider requires explicit non-empty model bindings")
            if self.fixture_options:
                raise ValueError("openai_compatible provider must not define fixture_options")
            aliases = [binding.alias for binding in self.model_bindings]
            if len(set(aliases)) != len(aliases):
                raise ValueError("Provider model binding aliases must be unique")
        return self

    @property
    def model_mapping(self) -> dict[str, str]:
        return {binding.alias: binding.model for binding in self.model_bindings}


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(default="fixture", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    model_alias: str = Field(
        default="fast-advisory", min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$"
    )
    temperature: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0.0"), le=Decimal("1.0"))
    max_input_tokens: int = Field(default=8192, ge=1, le=1_000_000)
    max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    max_total_tokens: int = Field(default=9216, ge=65, le=1_008_192)
    timeout_seconds: float = Field(default=10.0, ge=MIN_PROVIDER_TIMEOUT_SECONDS, le=60.0)
    max_retries: int = Field(default=1, ge=0, le=5)
    schema_version: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
        default=PROMPT_SCHEMA_VERSION,
    )

    @field_validator("provider", "model_alias", "schema_version")
    @classmethod
    def reject_secret_like_request_identity(cls, value: str) -> str:
        if _looks_like_credential(value):
            raise ValueError("Provider request identity must not contain credential material")
        return value


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    duration_ms: float = 0.0
    provider_id: str = Field(default="fixture", min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    provider_type: Literal["fixture", "openai_compatible"] = "fixture"
    model_used: str = Field(
        default="fixture-v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/:-]*$",
    )

    @field_validator("provider_id", "model_used")
    @classmethod
    def reject_secret_like_result_identity(cls, value: str) -> str:
        if _looks_like_credential(value):
            raise ValueError("Provider result identity must not contain credential material")
        return value

    @model_validator(mode="after")
    def consistent_token_accounting(self):
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("total_tokens must equal prompt_tokens + completion_tokens")
        return self


class AIProvider(abc.ABC):
    """Replaceable AI provider interface. Domain logic references only this abstraction."""

    @abc.abstractmethod
    async def analyze(
        self,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: ModelConfig,
        timeout_seconds: float | None = None,
    ) -> ProviderResult:
        """Execute model analysis asynchronously with strict timeout and structured output."""
        pass


class SpawnSafeTestProvider(AIProvider):
    """Marker base class for deterministic in-memory test doubles only.

    Only deterministic, non-network fixture providers used in testing may inherit
    from this class. OpenAIChatCompletionsProvider and real/external providers MUST NOT
    inherit from this class.
    """

    pass


async def analyze_with_controls(
    provider: ProviderDescriptor,
    *,
    agent_id: str,
    system_prompt: str,
    user_payload: str,
    model_config: ModelConfig,
    timeout_seconds: float | None = None,
) -> ProviderResult:
    """Execute through the killable provider boundary with one overall deadline."""
    if not isinstance(provider, ProviderDescriptor):
        raise ProviderRequestError(
            f"analyze_with_controls requires ProviderDescriptor; "
            f"live {type(provider).__name__} instances are prohibited"
        )
    from app.services.ai.execution import provider_executor

    return await provider_executor.execute(
        provider,
        agent_id=agent_id,
        system_prompt=system_prompt,
        user_payload=user_payload,
        model_config=model_config,
        timeout_seconds=timeout_seconds,
    )


class FixtureAIProvider(SpawnSafeTestProvider):
    """Deterministic, reproducible fixture provider for testing multi-agent orchestration.

    Zero external network calls; zero vendor API dependencies.
    Configurable for testing edge cases, timeouts, malformed JSON, and injections.
    """

    def __init__(
        self,
        *,
        provider_id: str = "fixture",
        fail_agents: set[str] | None = None,
        malformed_json_agents: set[str] | None = None,
        schema_invalid_agents: set[str] | None = None,
        injection_agents: set[str] | None = None,
        timeout_agents: set[str] | None = None,
        hanging_agents: set[str] | None = None,
        token_budget_exceeded_agents: set[str] | None = None,
        agent_biases: dict[str, str] | None = None,
        agent_strengths: dict[str, str] | None = None,
        token_mode: str | None = None,
        oversized_mode: str | None = None,
    ):
        if not _SAFE_PROVIDER_ID.fullmatch(provider_id):
            raise ValueError("Fixture provider_id must be a safe bounded identifier")
        self.provider_id = provider_id
        self.fail_agents = set(fail_agents or ())
        self.malformed_json_agents = set(malformed_json_agents or ())
        self.schema_invalid_agents = set(schema_invalid_agents or ())
        self.injection_agents = set(injection_agents or ())
        self.timeout_agents = set(timeout_agents or ())
        self.hanging_agents = set(hanging_agents or ())
        self.token_budget_exceeded_agents = set(token_budget_exceeded_agents or ())
        self.agent_biases = dict(agent_biases or {})
        self.agent_strengths = dict(agent_strengths or {})
        self.token_mode = token_mode
        self.oversized_mode = oversized_mode
        self.call_history: list[dict[str, object]] = []

    def to_descriptor(self) -> ProviderDescriptor:
        """Create a pure, validated ProviderDescriptor representing this fixture configuration."""
        opts: dict[str, Any] = {}
        if self.fail_agents:
            opts["fail_agents"] = sorted(self.fail_agents)
        if self.malformed_json_agents:
            opts["malformed_json_agents"] = sorted(self.malformed_json_agents)
        if self.schema_invalid_agents:
            opts["schema_invalid_agents"] = sorted(self.schema_invalid_agents)
        if self.injection_agents:
            opts["injection_agents"] = sorted(self.injection_agents)
        if self.timeout_agents:
            opts["timeout_agents"] = sorted(self.timeout_agents)
        if self.hanging_agents:
            opts["hanging_agents"] = sorted(self.hanging_agents)
        if self.token_budget_exceeded_agents:
            opts["token_budget_exceeded_agents"] = sorted(self.token_budget_exceeded_agents)
        if self.agent_biases:
            opts["agent_biases"] = dict(self.agent_biases)
        if self.agent_strengths:
            opts["agent_strengths"] = dict(self.agent_strengths)
        if self.token_mode:
            opts["token_mode"] = self.token_mode
        if self.oversized_mode:
            opts["oversized_mode"] = self.oversized_mode
        return ProviderDescriptor(
            provider_id=self.provider_id,
            provider_type="fixture",
            config_profile="fixture",
            fixture_options=opts,
        )

    async def analyze(
        self,
        *,
        agent_id: str,
        system_prompt: str,
        user_payload: str,
        model_config: ModelConfig,
        timeout_seconds: float | None = None,
    ) -> ProviderResult:
        t0 = time.perf_counter()
        effective_timeout = timeout_seconds or model_config.timeout_seconds

        self.call_history.append(
            {
                "agent_id": agent_id,
                "model_alias": model_config.model_alias,
                "user_payload_length": len(user_payload),
                "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            }
        )

        # 0. Simulate indefinite hang
        if agent_id in self.hanging_agents:
            await asyncio.sleep(9999)

        # 1. Simulate timeout
        if agent_id in self.timeout_agents:
            await asyncio.sleep(effective_timeout + 0.1)
            raise TimeoutError(f"Fixture provider timeout for agent {agent_id}")

        # 2. Simulate failure / exception
        if agent_id in self.fail_agents:
            raise RuntimeError(f"Fixture provider error for agent {agent_id}")

        # 3. Simulate malformed JSON
        if agent_id in self.malformed_json_agents:
            return ProviderResult(
                content="<<<INVALID JSON DETECTED>>>",
                raw_payload={},
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                duration_ms=(time.perf_counter() - t0) * 1000,
                provider_id=self.provider_id,
                provider_type="fixture",
                model_used="fixture-v1",
            )

        # 4. Simulate token budget exceeded
        if agent_id in self.token_budget_exceeded_agents:
            raise ValueError(f"Token budget exceeded for agent {agent_id}: limit={model_config.max_output_tokens}")

        # 5. Extract context from payload if possible
        direction = "LONG"
        symbol = "XAUUSD"
        try:
            parsed = json.loads(user_payload)
            if isinstance(parsed, dict):
                raw_ctx = parsed.get("trusted_context")
                ctx = raw_ctx if isinstance(raw_ctx, dict) else parsed
                if isinstance(ctx, dict):
                    cand = ctx.get("strategy_candidate") or ctx.get("strategy")
                    if isinstance(cand, dict) and cand.get("direction"):
                        direction = str(cand["direction"])
                    if ctx.get("symbol"):
                        symbol = str(ctx["symbol"])
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.debug("FixtureAIProvider failed to parse user_payload: %s", exc)

        now_utc = dt.datetime.now(dt.UTC).isoformat()
        bias = self.agent_biases.get(agent_id, direction if direction in ("LONG", "SHORT") else "NEUTRAL")
        strength = self.agent_strengths.get(agent_id, "STRONG")

        payload: dict[str, Any]
        if agent_id == META_CONTROLLER_ID:
            payload = {
                "directional_bias": bias,
                "evidence_strength": strength,
                "agent_agreement": "HIGH" if len(set(self.agent_biases.values())) <= 1 else "CONFLICTING",
                "summary_th": f"การประเมินภาพรวมเชิงสังเคราะห์สำหรับ {symbol}: มีความสอดคล้องระดับสูงในทิศทาง {bias}",
                "key_evidence_th": ["โครงสร้างราคาเป็นไปตามแนวโน้ม", "โมเมนตัมยืนยันการเคลื่อนไหว"],
                "conflicts_th": [],
                "risk_notes_th": ["ความเสี่ยงอยู่ในเกณฑ์ควบคุมตาม Policy"],
                "warnings_th": [],
            }
        else:
            payload = {
                "agent_id": agent_id,
                "agent_version": "ai-1.0.0",
                "status": "READY",
                "directional_bias": bias,
                "evidence_strength": strength,
                "summary_th": f"รายงานการวิเคราะห์ของ {agent_id} สำหรับ {symbol} พบปัจจัยสนับสนุนทิศทาง {bias}",
                "evidence_refs": [f"fixture://{agent_id}/ref-01", f"fixture://{agent_id}/ref-02"],
                "supporting_factors_th": [f"ปัจจัยสนับสนุนที่ 1 จาก {agent_id}", f"ปัจจัยสนับสนุนที่ 2 จาก {agent_id}"],
                "conflicting_factors_th": [],
                "warnings_th": [],
                "missing_context_th": [],
                "provider_provenance": model_config.provider,
                "prompt_version": "v1",
                "generated_at": now_utc,
                "as_of": now_utc,
            }

        # 6. Simulate schema invalid output (missing required fields)
        if agent_id in self.schema_invalid_agents:
            payload.pop("directional_bias", None)
            payload.pop("summary_th", None)

        # 7. Simulate adversarial prompt injection returning forbidden order fields
        if agent_id in self.injection_agents:
            payload["order_type"] = "BUY"
            payload["stop_loss"] = 2500.00
            payload["execute"] = True

        json_content = json.dumps(payload, ensure_ascii=False)
        prompt_tokens = 250
        completion_tokens = 150
        total_tokens = 400
        if self.token_mode == "huge":
            prompt_tokens = 10**12
            completion_tokens = 1
            total_tokens = 10**12 + 1
        elif self.token_mode == "inconsistent":
            prompt_tokens = 100
            completion_tokens = 20
            total_tokens = 999
        if self.oversized_mode == "content":
            json_content = "X" * 20_000
        elif self.oversized_mode == "raw":
            payload = {"blob": "X" * 20_000}
        elif self.oversized_mode == "tokens":
            completion_tokens = 2_000
            total_tokens = prompt_tokens + 2_000
        return ProviderResult(
            content=json_content,
            raw_payload=payload,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=(time.perf_counter() - t0) * 1000,
            provider_id=self.provider_id,
            provider_type="fixture",
            model_used="fixture-v1",
        )
