"""Phase 6.1 AI Foundation domain contracts.

All AI outputs are strictly ADVISORY ONLY.
AI has NO execution authority, cannot modify RiskPolicy, bypass Kill Switch,
override RiskDecision, mutate TradePlan geometry (Entry, SL, TP), or increase risk.
"""

import datetime as dt
import hashlib
import json
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

VERSION = "ai-1.0.0"
PROMPT_SCHEMA_VERSION = "prompt-1.0.0"

DirectionalBias = Literal["LONG", "SHORT", "NEUTRAL", "NO_BIAS"]
EvidenceStrength = Literal["STRONG", "MODERATE", "WEAK", "INSUFFICIENT"]
AgentAgreement = Literal["HIGH", "MEDIUM", "LOW", "CONFLICTING", "UNAVAILABLE"]
AgentStatus = Literal[
    "READY",
    "PARTIAL",
    "DEGRADED",
    "UNAVAILABLE",
    "BLOCKED_BY_UPSTREAM",
    "STALE_INPUT",
]
MetaStatus = Literal[
    "READY",
    "PARTIAL",
    "DEGRADED",
    "UNAVAILABLE",
    "STALE",
    "BLOCKED_BY_KILL_SWITCH",
    "BLOCKED_BY_RISK",
    "BLOCKED_BY_UPSTREAM",
]

# Explicit analytical agent IDs
ANALYTICAL_AGENT_IDS = (
    "market_context",
    "smc_ict",
    "macro_news",
    "strategy_critic",
    "risk_interpreter",
    "trade_thesis",
)
META_CONTROLLER_ID = "meta_controller"


def fingerprint(value: object) -> str:
    """Compute deterministic SHA-256 fingerprint of semantic JSON structure."""

    def encode(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, (dt.datetime, dt.date)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return format(item, "f")
        raise TypeError(type(item).__name__)

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode, ensure_ascii=False).encode()
    ).hexdigest()


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(ge=0, default=0)
    completion_tokens: int = Field(ge=0, default=0)
    total_tokens: int = Field(ge=0, default=0)


class AgentAnalysisResult(BaseModel):
    """Strict agent output contract.

    Forbidden fields (enforced via extra='forbid'):
    entry, stop_loss, take_profit, approved_risk, position_size, order_type, execute, etc.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    agent_version: str = VERSION
    status: AgentStatus
    directional_bias: DirectionalBias
    evidence_strength: EvidenceStrength
    summary_th: str
    evidence_refs: tuple[str, ...] = ()
    supporting_factors_th: tuple[str, ...] = ()
    conflicting_factors_th: tuple[str, ...] = ()
    warnings_th: tuple[str, ...] = ()
    missing_context_th: tuple[str, ...] = ()
    provider_provenance: str = "fixture"
    prompt_version: str = "v1"
    generated_at: AwareDatetime
    as_of: AwareDatetime
    token_usage: TokenUsage | None = None

    @field_validator("generated_at", "as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class AIAnalysisInput(BaseModel):
    """Immutable input contract for the multi-agent AI analysis layer.

    Aggregates authoritative outputs from Market Data, Market Structure,
    News, Strategy Engine, and Risk Engine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: str
    trace_id: str
    symbol: str
    as_of: AwareDatetime

    # Upstream authoritative states
    market_quote: dict[str, Any] = Field(default_factory=dict)
    market_structure_context: dict[str, Any] = Field(default_factory=dict)
    news_context: dict[str, Any] = Field(default_factory=dict)
    strategy_candidate: dict[str, Any] = Field(default_factory=dict)
    trade_plan: dict[str, Any] = Field(default_factory=dict)
    risk_decision: dict[str, Any] = Field(default_factory=dict)
    kill_switch_state: dict[str, Any] = Field(default_factory=dict)

    # Provenance and versions
    market_provenance: dict[str, Any] = Field(default_factory=dict)
    news_provenance: dict[str, Any] = Field(default_factory=dict)
    input_versions: dict[str, str] = Field(default_factory=dict)
    input_fingerprint: str = ""

    @field_validator("as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class AIAnalysisResult(BaseModel):
    """Meta Controller final aggregated output.

    Strictly ADVISORY ONLY with no execution authority.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: str
    symbol: str
    as_of: AwareDatetime
    status: MetaStatus

    directional_bias: DirectionalBias
    evidence_strength: EvidenceStrength
    agent_agreement: AgentAgreement

    summary_th: str
    key_evidence_th: tuple[str, ...] = ()
    conflicts_th: tuple[str, ...] = ()
    risk_notes_th: tuple[str, ...] = ()
    warnings_th: tuple[str, ...] = ()

    # Exactly six analytical agent results
    agent_results: dict[str, AgentAnalysisResult] = Field(default_factory=dict)

    # Traceability & safety bindings
    strategy_id: str = ""
    strategy_version: str = ""
    risk_decision_id: str = ""
    risk_decision_status: str = ""
    kill_switch_state: str = "INACTIVE"

    provider_provenance: str = "fixture"
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    generated_at: AwareDatetime
    input_fingerprint: str = ""
    analysis_fingerprint: str = ""

    # Immutable safety disclaimer
    execution_disclaimer: Literal[
        "ADVISORY_ONLY_NO_EXECUTION_AUTHORITY"
    ] = "ADVISORY_ONLY_NO_EXECUTION_AUTHORITY"

    @field_validator("generated_at", "as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)
