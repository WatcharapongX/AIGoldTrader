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


# -------------------------------------------------------------------------
# Strict Nested Immutable Input Contracts
# -------------------------------------------------------------------------


class AIMarketQuoteContext(BaseModel):
    """Authoritative market quote context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    bid: Decimal = Decimal("0.0")
    ask: Decimal = Decimal("0.0")
    spread: Decimal = Decimal("0.0")
    timestamp: AwareDatetime
    is_stale: bool = False
    source: str = "simulated"

    @field_validator("timestamp")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class AIMarketStructureContext(BaseModel):
    """Authoritative market structure context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    timeframe: str = "M15"
    as_of: AwareDatetime
    internal_state: str = "UNKNOWN"
    external_state: str = "UNKNOWN"
    regime: str = "UNKNOWN"
    current_sessions: tuple[str, ...] = ()
    swings: tuple[dict[str, Any], ...] = ()
    events: tuple[dict[str, Any], ...] = ()
    liquidity: tuple[dict[str, Any], ...] = ()
    zones: tuple[dict[str, Any], ...] = ()
    dealing_range: dict[str, Any] | None = None

    @field_validator("as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class AINewsEventContext(BaseModel):
    """Authoritative individual economic news event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    currency: str
    impact: str
    scheduled_at: AwareDatetime
    available_at: AwareDatetime
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    revision_version: int | None = None

    @field_validator("scheduled_at", "available_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class AINewsContext(BaseModel):
    """Authoritative news context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    news_state: str = "CALM"  # CALM, EVENT_RISK_ACTIVE, UNAVAILABLE
    in_blackout: bool = False
    in_pre_news_window: bool = False
    in_post_news_window: bool = False
    as_of: AwareDatetime
    events: tuple[AINewsEventContext, ...] = ()
    event_ids: tuple[str, ...] = ()
    description_th: str = ""
    source: str = ""
    revision_version: int | None = None

    @field_validator("as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class AIStrategyContext(BaseModel):
    """Authoritative strategy candidate context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    strategy_id: str
    strategy_version: str = "1.0.0"
    profile_id: str
    symbol: str
    direction: str  # LONG, SHORT
    score: int = 0
    detected_at: AwareDatetime
    confirmed_at: AwareDatetime | None = None
    status: str = "PENDING"
    evidence: tuple[dict[str, Any], ...] = ()

    @field_validator("detected_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)

    @field_validator("confirmed_at")
    @classmethod
    def utc_confirmed_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None


class AITradePlanContext(BaseModel):
    """Authoritative trade plan context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    entry_lower: Decimal
    entry_upper: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal | None = None
    take_profit_2: Decimal | None = None
    risk_reward_ratio: Decimal | None = None
    invalidation_th: str = ""
    expires_at: AwareDatetime | None = None

    @field_validator("expires_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None


class AIRiskDecisionContext(BaseModel):
    """Authoritative risk decision and reservation context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    decision: str  # APPROVED, REDUCED, BLOCKED, RISK_NOT_EVALUATED, EXPIRED
    account_id: str
    profile_id: str
    requested_risk_pct: Decimal = Decimal("0.0")
    approved_risk_pct: Decimal = Decimal("0.0")
    requested_risk_amount: Decimal = Decimal("0.0")
    approved_risk_amount: Decimal = Decimal("0.0")
    position_size: Decimal = Decimal("0.0")
    policy_version: str = "risk-policy-1.0.0"
    as_of: AwareDatetime
    expires_at: AwareDatetime
    reservation_id: str | None = None
    reservation_status: str | None = None  # ACTIVE, RELEASED, EXPIRED, NONE
    blocked_reasons_th: tuple[str, ...] = ()

    @field_validator("as_of", "expires_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class AIKillSwitchContext(BaseModel):
    """Authoritative kill switch context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    state: str  # ACTIVE, INACTIVE, UNKNOWN
    trigger_type: str = "NONE"
    reason_th: str = ""
    activated_at: AwareDatetime | None = None
    cleared_at: AwareDatetime | None = None
    policy_version: str = "risk-policy-1.0.0"

    @field_validator("activated_at", "cleared_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None


class AIProvenance(BaseModel):
    """Authoritative provenance tracking across all upstream domains."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    market_source: str = "simulated"
    market_context_id: str = ""
    structure_context_id: str = ""
    news_provider: str = ""
    news_revision: str = ""
    strategy_candidate_id: str = ""
    strategy_evaluation_id: str = ""
    trade_plan_id: str = ""
    risk_decision_id: str = ""
    risk_reservation_id: str = ""
    kill_switch_record_id: str = ""
    kill_switch_as_of: AwareDatetime | None = None

    @field_validator("kill_switch_as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None


def compute_semantic_input_fingerprint(
    *,
    symbol: str,
    account_id: str,
    profile_id: str,
    as_of: dt.datetime,
    quote_context: AIMarketQuoteContext,
    structure_context: AIMarketStructureContext,
    news_context: AINewsContext,
    strategy_context: AIStrategyContext,
    trade_plan_context: AITradePlanContext,
    risk_context: AIRiskDecisionContext,
    kill_switch_context: AIKillSwitchContext,
    provenance: AIProvenance,
) -> str:
    """Derive deterministic SHA-256 fingerprint from SEMANTIC authority only.

    Excludes request-clock jitter (analysis_requested_at), request UUID (analysis_id, trace_id).
    """
    semantic_data = {
        "symbol": symbol,
        "account_id": account_id,
        "profile_id": profile_id,
        "as_of": as_of.isoformat(),
        "quote": quote_context.model_dump(mode="json"),
        "structure": structure_context.model_dump(mode="json"),
        "news": news_context.model_dump(mode="json"),
        "strategy": strategy_context.model_dump(mode="json"),
        "trade_plan": trade_plan_context.model_dump(mode="json"),
        "risk": risk_context.model_dump(mode="json"),
        "kill_switch": kill_switch_context.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
    }
    return fingerprint(semantic_data)


class AIAnalysisInput(BaseModel):
    """Immutable input contract for the multi-agent AI analysis layer.

    Aggregates authoritative outputs from Market Data, Market Structure,
    News, Strategy Engine, and Risk Engine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: str
    trace_id: str
    analysis_requested_at: AwareDatetime
    as_of: AwareDatetime
    symbol: str
    account_id: str
    profile_id: str

    # Typed authoritative contexts
    quote_context: AIMarketQuoteContext
    structure_context: AIMarketStructureContext
    news_context: AINewsContext
    strategy_context: AIStrategyContext
    trade_plan_context: AITradePlanContext
    risk_context: AIRiskDecisionContext
    kill_switch_context: AIKillSwitchContext
    provenance: AIProvenance

    input_versions: dict[str, str] = Field(default_factory=dict)
    input_fingerprint: str = ""

    @field_validator("analysis_requested_at", "as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)

    # Backwards-compatible convenience properties
    @property
    def market_quote(self) -> dict[str, Any]:
        return self.quote_context.model_dump(mode="json")

    @property
    def market_structure_context(self) -> dict[str, Any]:
        return self.structure_context.model_dump(mode="json")

    @property
    def strategy_candidate(self) -> dict[str, Any]:
        return self.strategy_context.model_dump(mode="json")

    @property
    def trade_plan(self) -> dict[str, Any]:
        return self.trade_plan_context.model_dump(mode="json")

    @property
    def risk_decision(self) -> dict[str, Any]:
        return self.risk_context.model_dump(mode="json")

    @property
    def kill_switch_state(self) -> dict[str, Any]:
        return self.kill_switch_context.model_dump(mode="json")


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
    execution_disclaimer: Literal["ADVISORY_ONLY_NO_EXECUTION_AUTHORITY"] = "ADVISORY_ONLY_NO_EXECUTION_AUTHORITY"

    @field_validator("generated_at", "as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)
