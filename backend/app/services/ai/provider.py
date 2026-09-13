"""AI Provider abstraction and deterministic fixture implementation for testing."""

import abc
import asyncio
import datetime as dt
import json
import logging
import time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.ai.domain import (
    META_CONTROLLER_ID,
    PROMPT_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = "fixture"
    model_alias: str = "fast-advisory"
    temperature: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0.0"), le=Decimal("1.0"))
    max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    max_retries: int = Field(default=1, ge=0, le=5)
    schema_version: str = PROMPT_SCHEMA_VERSION


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    model_used: str = "fixture-v1"


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


class FixtureAIProvider(AIProvider):
    """Deterministic, reproducible fixture provider for testing multi-agent orchestration.

    Zero external network calls; zero vendor API dependencies.
    Configurable for testing edge cases, timeouts, malformed JSON, and injections.
    """

    def __init__(
        self,
        *,
        fail_agents: set[str] | None = None,
        malformed_json_agents: set[str] | None = None,
        schema_invalid_agents: set[str] | None = None,
        injection_agents: set[str] | None = None,
        timeout_agents: set[str] | None = None,
        token_budget_exceeded_agents: set[str] | None = None,
        agent_biases: dict[str, str] | None = None,
        agent_strengths: dict[str, str] | None = None,
    ):
        self.fail_agents = set(fail_agents or ())
        self.malformed_json_agents = set(malformed_json_agents or ())
        self.schema_invalid_agents = set(schema_invalid_agents or ())
        self.injection_agents = set(injection_agents or ())
        self.timeout_agents = set(timeout_agents or ())
        self.token_budget_exceeded_agents = set(token_budget_exceeded_agents or ())
        self.agent_biases = dict(agent_biases or {})
        self.agent_strengths = dict(agent_strengths or {})
        self.call_history: list[dict[str, object]] = []

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
                model_used=model_config.model_alias,
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
                cand = parsed.get("strategy_candidate")
                if isinstance(cand, dict) and cand.get("direction"):
                    direction = str(cand["direction"])
                if parsed.get("symbol"):
                    symbol = str(parsed["symbol"])
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
                "evidence_refs": [f"ref_{agent_id}_01", f"ref_{agent_id}_02"],
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
        return ProviderResult(
            content=json_content,
            raw_payload=payload,
            prompt_tokens=250,
            completion_tokens=150,
            total_tokens=400,
            duration_ms=(time.perf_counter() - t0) * 1000,
            model_used=model_config.model_alias,
        )
