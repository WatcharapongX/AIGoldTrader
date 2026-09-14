"""Phase 6.1 AI Foundation domain contracts.

All AI outputs are strictly ADVISORY ONLY.
AI has NO execution authority, cannot modify RiskPolicy, bypass Kill Switch,
override RiskDecision, mutate TradePlan geometry (Entry, SL, TP), or increase risk.
"""

import datetime as dt
import hashlib
import json
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

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


class AIProviderExecutionProvenance(BaseModel):
    """Immutable, non-secret identity of one completed provider execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    provider_type: Literal["fixture", "openai_compatible"]
    model_alias: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model_used: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/:-]*$")
    mode: Literal["fixture", "external"]
AuthorityAvailability = Literal["AVAILABLE", "STALE", "UNAVAILABLE"]

# Explicit Phase 3 -> AI temporal projection audit. Every clock on the actual
# upstream evidence models is represented as a typed AI field and is checked by
# the orchestrator; no listed safety clock is authoritative only in data_json.
PHASE3_TEMPORAL_FIELD_MAP: Final[dict[str, tuple[str, ...]]] = {
    "SwingPoint": ("swing_time", "confirmed_at"),
    "StructureEvent": ("swing_time", "occurred_at", "confirmed_at"),
    "LiquidityLevel": ("created_at", "confirmed_at", "swept_at", "ended_at"),
    "Zone": ("occurred_at", "confirmed_at", "ended_at"),
    "DealingRange": ("origin_time", "confirmed_at"),
}

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
    execution_provenance: AIProviderExecutionProvenance | None = None
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

    availability: AuthorityAvailability = "AVAILABLE"
    symbol: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    spread: Decimal | None = None
    timestamp: AwareDatetime | None = None
    is_stale: bool = False
    source: str = ""
    unavailable_reason: str = ""

    @field_validator("timestamp")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def authoritative_quote(self):
        if self.availability in ("AVAILABLE", "STALE"):
            if self.bid is None or self.ask is None or self.spread is None or self.timestamp is None or not self.source:
                raise ValueError("Available quote requires values, observed timestamp, and source")
            if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid or self.spread != self.ask - self.bid:
                raise ValueError("Invalid authoritative quote values")
        return self


def _canonical_evidence(value: Any, temporal_fields: tuple[str, ...]) -> dict[str, Any]:
    """Copy evidence into typed clocks plus immutable canonical JSON metadata."""
    if isinstance(value, BaseModel):
        raw = value.model_dump(mode="json")
    elif isinstance(value, dict):
        raw = dict(value)
    else:
        raise TypeError("Evidence must be a mapping or Pydantic model")
    projected = {name: raw.get(name) for name in temporal_fields if raw.get(name) is not None}
    projected["id"] = str(raw.get("id") or "")
    projected["kind"] = str(raw.get("kind") or raw.get("code") or "")
    projected["data_json"] = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return projected


class AISwingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = ""
    kind: str = ""
    swing_time: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    data_json: str = "{}"

    @model_validator(mode="before")
    @classmethod
    def canonicalize(cls, value: Any):
        return value if isinstance(value, cls) else _canonical_evidence(value, PHASE3_TEMPORAL_FIELD_MAP["SwingPoint"])


class AIStructureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = ""
    kind: str = ""
    swing_time: AwareDatetime
    occurred_at: AwareDatetime | None = None
    created_at: AwareDatetime | None = None
    detected_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    available_at: AwareDatetime | None = None
    data_json: str = "{}"

    @model_validator(mode="before")
    @classmethod
    def canonicalize(cls, value: Any):
        fields = PHASE3_TEMPORAL_FIELD_MAP["StructureEvent"] + ("created_at", "detected_at", "available_at")
        return value if isinstance(value, cls) else _canonical_evidence(value, fields)


class AILiquidityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = ""
    kind: str = ""
    created_at: AwareDatetime | None = None
    detected_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    swept_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    data_json: str = "{}"

    @model_validator(mode="before")
    @classmethod
    def canonicalize(cls, value: Any):
        fields = PHASE3_TEMPORAL_FIELD_MAP["LiquidityLevel"] + ("detected_at",)
        return value if isinstance(value, cls) else _canonical_evidence(value, fields)


class AIZoneEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = ""
    kind: str = ""
    occurred_at: AwareDatetime | None = None
    created_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    data_json: str = "{}"

    @model_validator(mode="before")
    @classmethod
    def canonicalize(cls, value: Any):
        fields = PHASE3_TEMPORAL_FIELD_MAP["Zone"] + ("created_at",)
        return value if isinstance(value, cls) else _canonical_evidence(value, fields)


class AIDealingRangeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = ""
    kind: str = ""
    origin_time: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    data_json: str = "{}"

    @model_validator(mode="before")
    @classmethod
    def canonicalize(cls, value: Any):
        return value if isinstance(value, cls) else _canonical_evidence(
            value, PHASE3_TEMPORAL_FIELD_MAP["DealingRange"]
        )


class AIMarketStructureContext(BaseModel):
    """Authoritative market structure context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    availability: AuthorityAvailability = "AVAILABLE"
    symbol: str
    timeframe: str | None = None
    as_of: AwareDatetime | None = None
    source: str = ""
    context_id: str = ""
    algorithm_version: str = ""
    internal_state: str | None = None
    external_state: str | None = None
    regime: str | None = None
    current_sessions: tuple[str, ...] = ()
    swings: tuple[AISwingEvidence, ...] = ()
    events: tuple[AIStructureEvent, ...] = ()
    liquidity: tuple[AILiquidityEvidence, ...] = ()
    zones: tuple[AIZoneEvidence, ...] = ()
    dealing_range: AIDealingRangeEvidence | None = None
    unavailable_reason: str = ""

    @field_validator("as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def authoritative_structure(self):
        if self.availability == "AVAILABLE" and (
            self.as_of is None
            or not self.timeframe
            or not self.source
            or not self.context_id
            or not self.algorithm_version
            or self.internal_state is None
            or self.external_state is None
            or self.regime is None
        ):
            raise ValueError("Available structure requires a complete authoritative identity and state")
        return self


class AINewsEventContext(BaseModel):
    """Authoritative individual economic news event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    currency: str
    impact: str
    scheduled_at: AwareDatetime
    available_at: AwareDatetime
    updated_at: AwareDatetime
    released_at: AwareDatetime | None = None
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    revision_version: int | None = None

    @field_validator("scheduled_at", "available_at", "updated_at", "released_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def valid_vintage(self):
        if not self.id or not self.title or not self.currency or not self.impact:
            raise ValueError("News event requires canonical identity and classification")
        if self.updated_at > self.available_at:
            raise ValueError("News revision update cannot be visible before its availability")
        if self.released_at is not None and not self.scheduled_at <= self.released_at <= self.available_at:
            raise ValueError("News release time must fall between schedule and availability")
        if self.actual is not None and self.released_at is None:
            raise ValueError("News actual requires a release timestamp")
        return self


class AINewsContext(BaseModel):
    """Authoritative news context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    availability: AuthorityAvailability = "AVAILABLE"
    news_state: str | None = None
    in_blackout: bool = False
    in_pre_news_window: bool = False
    in_post_news_window: bool = False
    as_of: AwareDatetime | None = None
    events: tuple[AINewsEventContext, ...] = ()
    event_ids: tuple[str, ...] = ()
    description_th: str = ""
    source: str = ""
    revision_version: int | None = None
    context_fingerprint: str = ""
    unavailable_reason: str = ""

    @field_validator("as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def authoritative_news(self):
        if self.availability == "AVAILABLE" and (
            self.as_of is None or not self.news_state or not self.source or not self.context_fingerprint
        ):
            raise ValueError("Available news requires state, as_of, source, and fingerprint")
        canonical_ids = tuple(event.id for event in self.events)
        if self.availability == "AVAILABLE" and (
            self.event_ids != canonical_ids or len(set(canonical_ids)) != len(canonical_ids)
        ):
            raise ValueError("News event_ids must exactly match unique canonical event identities")
        return self


class AIStrategyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = ""
    kind: str = ""
    created_at: AwareDatetime | None = None
    detected_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    available_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    data_json: str = "{}"

    @model_validator(mode="before")
    @classmethod
    def canonicalize(cls, value: Any):
        fields = ("created_at", "detected_at", "confirmed_at", "available_at", "expires_at")
        return value if isinstance(value, cls) else _canonical_evidence(value, fields)


class AIStrategyContext(BaseModel):
    """Authoritative strategy candidate context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    availability: AuthorityAvailability = "AVAILABLE"
    candidate_id: str
    strategy_id: str
    strategy_version: str = ""
    profile_id: str
    symbol: str
    direction: str | None = None
    score: int | None = None
    detected_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    status: str = ""
    evidence: tuple[AIStrategyEvidence, ...] = ()
    unavailable_reason: str = ""

    @field_validator("detected_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @field_validator("confirmed_at")
    @classmethod
    def utc_confirmed_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def authoritative_strategy(self):
        if self.availability == "AVAILABLE" and (
            not self.strategy_version
            or self.direction not in ("LONG", "SHORT")
            or self.score is None
            or self.detected_at is None
            or not self.status
        ):
            raise ValueError("Available strategy requires canonical direction, version, score, time, and status")
        return self


class AITradePlanContext(BaseModel):
    """Authoritative trade plan context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    availability: AuthorityAvailability = "AVAILABLE"
    plan_id: str = ""
    entry_lower: Decimal | None = None
    entry_upper: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit_1: Decimal | None = None
    take_profit_2: Decimal | None = None
    risk_reward_ratio: Decimal | None = None
    invalidation_th: str = ""
    as_of: AwareDatetime | None = None
    created_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    evidence: tuple[AIStrategyEvidence, ...] = ()
    unavailable_reason: str = ""

    @field_validator("as_of", "created_at", "expires_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def authoritative_plan(self):
        if self.availability == "AVAILABLE" and (
            not self.plan_id
            or self.entry_lower is None
            or self.entry_upper is None
            or self.stop_loss is None
            or self.as_of is None
            or self.expires_at is None
            or self.entry_lower <= 0
            or self.entry_upper < self.entry_lower
            or self.stop_loss <= 0
        ):
            raise ValueError("Available trade plan requires valid canonical geometry")
        return self


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
    reservation_status: str | None = None  # ACTIVE, RELEASED, EXPIRED, MISMATCHED, NONE
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

    market_source: str = ""
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
    as_of: dt.datetime | None,
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

    input_versions: tuple[tuple[str, str], ...] = ()
    input_fingerprint: str = ""

    @field_validator("analysis_requested_at", "as_of")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)

    @field_validator("input_versions", mode="before")
    @classmethod
    def immutable_versions(cls, value: Any):
        if isinstance(value, dict):
            return tuple(sorted((str(k), str(v)) for k, v in value.items()))
        return value

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
    # Meta Controller execution identity. None means no successful Meta provider call.
    execution_provenance: AIProviderExecutionProvenance | None = None
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
