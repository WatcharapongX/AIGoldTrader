"""Immutable contracts for infrastructure-free deterministic Risk evaluation."""

import datetime as dt
import enum
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.risk.domain import (
    AccountSnapshot,
    Decision,
    Direction,
    MarketProvenance,
    NewsRiskProvenance,
    RiskPolicy,
    SymbolSpecification,
)
from app.services.strategy.domain import SetupCandidate, TradePlanSuggestion

PURE_RISK_CORE_VERSION = "risk-pure-core-1.0.0"


class PureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KillSwitchInputState(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


class DataHealthInputState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    TRIGGERED = "TRIGGERED"
    UNKNOWN = "UNKNOWN"


class ReservationIntegrityState(str, enum.Enum):
    OK = "OK"
    DUPLICATE_ACTIVE_RESERVATION = "DUPLICATE_ACTIVE_RESERVATION"
    UNKNOWN = "UNKNOWN"


class QuoteAvailability(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class NewsAvailability(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class MarketSafetyState(str, enum.Enum):
    AVAILABLE_SAFE = "AVAILABLE_SAFE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    SPREAD_BLOCKED = "SPREAD_BLOCKED"
    POST_NEWS_SPREAD_BLOCKED = "POST_NEWS_SPREAD_BLOCKED"


class PureRiskCode(str, enum.Enum):
    APPROVED = "APPROVED"
    APPROVED_REDUCED = "APPROVED_REDUCED"
    POSITION_SIZED = "POSITION_SIZED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    KILL_SWITCH_UNKNOWN = "KILL_SWITCH_UNKNOWN"
    DATA_HEALTH_TRIGGERED = "DATA_HEALTH_TRIGGERED"
    DATA_HEALTH_UNKNOWN = "DATA_HEALTH_UNKNOWN"
    NEWS_UNAVAILABLE = "NEWS_UNAVAILABLE"
    NEWS_BLACKOUT = "NEWS_BLACKOUT"
    NEWS_PRE_REDUCTION = "NEWS_PRE_REDUCTION"
    NEWS_POST_WARNING = "NEWS_POST_WARNING"
    NEWS_POST_SPREAD_BLOCKED = "NEWS_POST_SPREAD_BLOCKED"
    CANDIDATE_TERMINAL = "CANDIDATE_TERMINAL"
    ACCOUNT_STALE = "ACCOUNT_STALE"
    EQUITY_NON_POSITIVE = "EQUITY_NON_POSITIVE"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    WEEKLY_LOSS_LIMIT = "WEEKLY_LOSS_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    SYMBOL_SPEC_INVALID = "SYMBOL_SPEC_INVALID"
    SYMBOL_SPEC_STALE = "SYMBOL_SPEC_STALE"
    QUOTE_UNAVAILABLE = "QUOTE_UNAVAILABLE"
    QUOTE_STALE = "QUOTE_STALE"
    SPREAD_EXCESSIVE = "SPREAD_EXCESSIVE"
    PLAN_STATUS_INVALID = "PLAN_STATUS_INVALID"
    PLAN_EXPIRED = "PLAN_EXPIRED"
    RESERVATION_DUPLICATE = "RESERVATION_DUPLICATE"
    RESERVATION_INTEGRITY_UNKNOWN = "RESERVATION_INTEGRITY_UNKNOWN"
    UNATTRIBUTED_OPEN_RISK = "UNATTRIBUTED_OPEN_RISK"
    CONCURRENT_LIMIT = "CONCURRENT_LIMIT"
    ACCOUNT_CAPACITY = "ACCOUNT_CAPACITY"
    SYMBOL_CAPACITY = "SYMBOL_CAPACITY"
    DIRECTIONAL_CAPACITY = "DIRECTIONAL_CAPACITY"
    PORTFOLIO_REDUCTION = "PORTFOLIO_REDUCTION"
    PER_TRADE_REDUCTION = "PER_TRADE_REDUCTION"
    POSITION_SIZING_FAILED = "POSITION_SIZING_FAILED"


class PureKillSwitchInput(PureModel):
    state: KillSwitchInputState
    reason_th: str = ""
    source: str = ""
    state_id: str = ""


class PureDataHealthInput(PureModel):
    state: DataHealthInputState
    provider: str = ""
    source: str = ""
    consecutive_failures: int = Field(default=0, ge=0)
    threshold: int = Field(default=1, ge=1)
    reason_th: str = ""


class PureQuoteState(PureModel):
    availability: QuoteAvailability
    timestamp: AwareDatetime | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    spread: Decimal | None = None
    source: str = ""
    mode: str = ""
    status: str = ""

    @field_validator("timestamp")
    @classmethod
    def utc_clock(cls, value: dt.datetime | None) -> dt.datetime | None:
        return value.astimezone(dt.UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_available_quote(self):
        values = (self.timestamp, self.bid, self.ask, self.spread)
        if self.availability == QuoteAvailability.AVAILABLE:
            if any(value is None for value in values):
                raise ValueError("Available quote requires timestamp, bid, ask, and spread")
            if self.bid <= 0 or self.ask < self.bid or self.spread < 0:
                raise ValueError("Invalid available quote")
            if self.spread != self.ask - self.bid:
                raise ValueError("Quote spread must equal ask minus bid")
        elif any(value is not None for value in values):
            raise ValueError("Unavailable quote cannot contain market values")
        return self


class PureNewsEvent(PureModel):
    event_id: str
    event_name: str
    currency: str
    impact: str
    scheduled_at: AwareDatetime
    available_at: AwareDatetime | None = None
    provider: str = ""
    source: str = ""
    revision_id: str = ""
    revision_version: int | None = None

    @field_validator("scheduled_at", "available_at")
    @classmethod
    def utc_clock(cls, value: dt.datetime | None) -> dt.datetime | None:
        return value.astimezone(dt.UTC) if value is not None else None


class PureNewsState(PureModel):
    availability: NewsAvailability
    events: tuple[PureNewsEvent, ...] = ()
    provider: str = ""
    source: str = ""
    revision_id: str = ""
    revision_version: int | None = None
    reason_th: str = ""

    @model_validator(mode="after")
    def unavailable_has_no_events(self):
        if self.availability == NewsAvailability.UNAVAILABLE and self.events:
            raise ValueError("Unavailable news state cannot contain events")
        return self


class PortfolioExposureSnapshot(PureModel):
    symbol: str
    direction: Direction
    open_risk_pct: Decimal = Field(ge=0)
    reserved_risk_pct: Decimal = Field(ge=0)
    symbol_risk_pct: Decimal = Field(ge=0)
    directional_risk_pct: Decimal = Field(ge=0)
    active_reservation_count: int = Field(ge=0)
    open_position_count: int = Field(ge=0)
    reservation_integrity: ReservationIntegrityState = ReservationIntegrityState.OK
    duplicate_candidate_id: str | None = None

    @model_validator(mode="after")
    def duplicate_evidence(self):
        if (
            self.reservation_integrity == ReservationIntegrityState.DUPLICATE_ACTIVE_RESERVATION
            and not self.duplicate_candidate_id
        ):
            raise ValueError("Duplicate reservation state requires duplicate_candidate_id")
        return self


class SafetyTriggerFacts(PureModel):
    daily_loss_breach: bool
    weekly_loss_breach: bool
    drawdown_breach: bool
    quote_safety_state: MarketSafetyState
    data_health_state: DataHealthInputState


class PureRiskEvaluationInput(PureModel):
    as_of: AwareDatetime
    candidate: SetupCandidate
    trade_plan: TradePlanSuggestion
    account: AccountSnapshot
    policy: RiskPolicy
    symbol_specification: SymbolSpecification
    quote: PureQuoteState
    news: PureNewsState
    kill_switch: PureKillSwitchInput
    data_health: PureDataHealthInput
    candidate_lifecycle_status: Literal[
        "DETECTED",
        "WAITING_CONFIRMATION",
        "READY",
        "BLOCKED_CONTEXT",
        "NO_TRADE",
        "INVALIDATED",
        "EXPIRED",
        "SUPERSEDED",
    ]
    candidate_transition_count: int = Field(ge=0)
    caller_requested_risk_pct: Decimal | None = None
    portfolio: PortfolioExposureSnapshot

    @field_validator("as_of")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return value.astimezone(dt.UTC)

    @model_validator(mode="after")
    def validate_semantic_links(self):
        if self.trade_plan.candidate_id != self.candidate.id:
            raise ValueError("TradePlan candidate_id must match candidate")
        if self.trade_plan.symbol != self.candidate.symbol:
            raise ValueError("TradePlan symbol must match candidate")
        if self.trade_plan.direction != self.candidate.direction:
            raise ValueError("TradePlan direction must match candidate")
        if self.portfolio.symbol != self.candidate.symbol:
            raise ValueError("Portfolio symbol must match candidate")
        if self.portfolio.direction != self.trade_plan.direction:
            raise ValueError("Portfolio direction must match TradePlan")
        if self.symbol_specification.symbol != self.candidate.symbol:
            raise ValueError("SymbolSpecification symbol must match candidate")
        if self.portfolio.open_risk_pct != self.account.open_risk_pct:
            raise ValueError("Portfolio open risk must match account evidence")
        if self.portfolio.open_position_count != self.account.open_positions_count:
            raise ValueError("Portfolio open-position count must match account evidence")
        if any(event.available_at is not None and event.available_at > self.as_of for event in self.news.events):
            raise ValueError("News event is not available at the evaluation time")
        return self


class PureRiskResult(PureModel):
    decision: Decision
    caller_requested_risk_pct: Decimal | None
    normalized_requested_risk_pct: Decimal
    target_risk_pct: Decimal
    approved_risk_pct: Decimal
    normalized_requested_risk_amount: Decimal
    target_risk_amount: Decimal
    approved_risk_amount: Decimal
    position_size: Decimal
    stop_distance: Decimal
    loss_per_lot: Decimal
    portfolio_exposure_before: Decimal
    portfolio_exposure_after: Decimal
    reason_codes: tuple[PureRiskCode, ...]
    warning_codes: tuple[PureRiskCode, ...]
    blocked_codes: tuple[PureRiskCode, ...]
    reasons_th: tuple[str, ...]
    warnings_th: tuple[str, ...]
    blocked_reasons_th: tuple[str, ...]
    market_provenance: MarketProvenance | None
    news_provenance: NewsRiskProvenance | None
    safety_trigger_facts: SafetyTriggerFacts
    pure_core_version: Literal["risk-pure-core-1.0.0"] = PURE_RISK_CORE_VERSION
    semantic_payload: str
    semantic_fingerprint: str
