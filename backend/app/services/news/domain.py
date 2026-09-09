"""Immutable canonical economic revisions and reproducible news context contracts."""

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.services.analysis.domain import Model, Number

NEWS_VERSION = "news-1.2.0"
Impact = Literal["LOW", "MEDIUM", "HIGH", "HOLIDAY", "NON_ECONOMIC", "UNKNOWN"]
Category = Literal[
    "EMPLOYMENT",
    "INFLATION",
    "CENTRAL_BANK",
    "GROWTH",
    "CONSUMER",
    "MANUFACTURING",
    "SERVICES",
    "HOUSING",
    "LABOR",
    "OTHER",
]
DirectionRule = Literal["HIGHER_IS_POSITIVE", "LOWER_IS_POSITIVE", "CONTEXT_DEPENDENT"]
Regime = Literal[
    "NORMAL",
    "PRE_NEWS",
    "NEWS_LOCK",
    "RELEASE",
    "POST_NEWS_VOLATILITY",
    "POST_NEWS_CONFIRMATION",
    "NORMALIZED",
    "UNKNOWN",
]
Bias = Literal[
    "USD_STRONG_POSITIVE",
    "USD_POSITIVE",
    "USD_NEUTRAL",
    "USD_NEGATIVE",
    "USD_STRONG_NEGATIVE",
    "CONFLICTING",
    "UNKNOWN",
]
Mode = Literal["FIXTURE", "LIVE", "UNAVAILABLE"]


class UTCModel(Model):
    @field_validator("*", mode="after")
    @classmethod
    def utc(cls, value):
        return value.astimezone(dt.UTC) if isinstance(value, dt.datetime) else value


class EconomicEvent(UTCModel):
    id: str = Field(min_length=1, max_length=100)
    provider_event_id: str = Field(min_length=1, max_length=100)
    occurrence_key: str = Field(min_length=1, max_length=100)
    event_name: str = Field(min_length=1, max_length=160)
    event_code: str = Field(min_length=1, max_length=40)
    group_id: str = Field(min_length=1, max_length=100)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    category: Category
    impact: Impact
    scheduled_at: AwareDatetime
    actual: Number | None
    forecast: Number | None
    previous: Number | None
    revised_previous: Number | None = None
    previous_before_revision: Number | None = None
    unit: Literal["PERCENT", "THOUSANDS", "INDEX", "RATE", "NUMBER", "NON_NUMERIC"]
    status: Literal["SCHEDULED", "UPCOMING", "RELEASED", "REVISED", "CANCELLED", "DELAYED", "UNKNOWN"]
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    source_mode: Mode
    updated_at: AwareDatetime
    available_at: AwareDatetime
    released_at: AwareDatetime | None = None
    revision_version: int = Field(ge=1)
    direction_rule: DirectionRule = "CONTEXT_DEPENDENT"
    field_provenance: dict[str, str] = Field(default_factory=dict, max_length=8)
    field_conflicts: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def valid_release(self):
        if self.status in ("RELEASED", "REVISED") and self.released_at is None:
            raise ValueError("Released status requires a known release time")
        if self.released_at is not None and (
            self.released_at < self.scheduled_at or self.released_at > self.available_at
        ):
            raise ValueError("Release time must be known and at or after schedule")
        if self.unit == "NON_NUMERIC" and any(
            value is not None
            for value in (
                self.actual,
                self.forecast,
                self.previous,
                self.revised_previous,
                self.previous_before_revision,
            )
        ):
            raise ValueError("Non-numeric event cannot contain invented numeric results")
        if self.actual is not None:
            if self.released_at is None or self.released_at < self.scheduled_at:
                raise ValueError("Actual requires a release at or after scheduled time")
            if self.available_at < self.released_at:
                raise ValueError("Actual cannot be available before release")
        if self.status in ("SCHEDULED", "UPCOMING", "CANCELLED", "DELAYED") and self.actual is not None:
            raise ValueError("Unreleased event cannot contain Actual")
        if self.updated_at > self.available_at:
            raise ValueError("Availability must include provider update time")
        return self


def default_channels() -> dict[str, list[Literal["USD", "INTEREST_RATES", "CROSS_CURRENCY", "RISK_SENTIMENT"]]]:
    return {"USD": ["USD", "INTEREST_RATES"], "EUR": ["CROSS_CURRENCY"]}


class NewsConfig(Model):
    # Seconds; named central configuration, not universal market prescriptions.
    pre_seconds: dict[str, int] = Field(default_factory=lambda: {"HIGH": 1800, "MEDIUM": 900, "LOW": 0})
    lock_seconds: dict[str, int] = Field(default_factory=lambda: {"HIGH": 300, "MEDIUM": 120, "LOW": 0})
    release_seconds: int = Field(default=60, ge=1, le=300)
    observation_seconds: int = Field(default=300, ge=60, le=1800)
    confirmation_seconds: int = Field(default=900, ge=300, le=3600)
    normalized_seconds: int = Field(default=1800, ge=900, le=7200)
    reaction_seconds: list[int] = Field(default_factory=lambda: [60, 300, 900], max_length=6)
    spread_baseline_seconds: int = Field(default=60, ge=10, le=600)
    minimum_spread_samples: int = Field(default=3, ge=1, le=60)
    spread_elevated: Number = Field(default=Decimal(2), gt=1)
    spread_extreme: Number = Field(default=Decimal(4), gt=1)
    directional_atr: Number = Field(default=Decimal("1.5"), gt=0)
    whipsaw_atr: Number = Field(default=Decimal(".8"), gt=0)
    muted_atr: Number = Field(default=Decimal(".25"), ge=0)
    volatility_elevated: Number = Field(default=Decimal(2), gt=0)
    volatility_extreme: Number = Field(default=Decimal(4), gt=0)
    relative_large: Number = Field(default=Decimal(".2"), gt=0)
    revision_weight: Number = Field(default=Decimal(".5"), ge=0, le=1)
    weights: dict[str, Number] = Field(
        default_factory=lambda: {"NFP": Decimal(2), "UNEMPLOYMENT": Decimal(1), "WAGES": Decimal(1)}
    )
    relevance: dict[str, int] = Field(default_factory=lambda: {"USD": 3, "EUR": 1})
    impact_relevance: dict[str, int] = Field(default_factory=lambda: {"HIGH": 3, "MEDIUM": 2, "LOW": 1})
    macro_channels: dict[str, list[Literal["USD", "INTEREST_RATES", "CROSS_CURRENCY", "RISK_SENTIMENT"]]] = Field(
        default_factory=default_channels
    )
    direction_overrides: dict[str, DirectionRule] = Field(default_factory=dict)
    provider_poll_seconds: int = Field(default=60, ge=15, le=3600)
    provider_stale_seconds: int = Field(default=300, ge=30, le=7200)
    medium_event_codes: tuple[str, ...] = ("JOBLESS_CLAIMS",)
    quote_max_age_seconds: int = Field(default=10, ge=1, le=60)

    @model_validator(mode="after")
    def ordered(self):
        if not self.release_seconds <= self.observation_seconds <= self.confirmation_seconds <= self.normalized_seconds:
            raise ValueError("News windows must be ordered")
        if set(self.pre_seconds) != {"HIGH", "MEDIUM", "LOW"} or set(self.lock_seconds) != set(self.pre_seconds):
            raise ValueError("All impact windows are required")
        if self.spread_elevated >= self.spread_extreme or self.volatility_elevated >= self.volatility_extreme:
            raise ValueError("Thresholds must be ordered")
        if any(v <= 0 or v > 3600 for v in self.reaction_seconds) or self.reaction_seconds != sorted(
            set(self.reaction_seconds)
        ):
            raise ValueError("Reaction windows must be unique ordered seconds within one hour")
        if any(
            k not in self.pre_seconds or not 0 <= v <= self.pre_seconds[k] <= 7200 for k, v in self.lock_seconds.items()
        ):
            raise ValueError("Invalid pre/lock windows")
        if set(self.impact_relevance) != {"HIGH", "MEDIUM", "LOW"} or any(
            value not in range(4) for value in self.impact_relevance.values()
        ):
            raise ValueError("Invalid impact relevance")
        if any(len(channels) > 4 for channels in self.macro_channels.values()):
            raise ValueError("Too many macro channels")
        if any(v < 0 or v > 10 for v in self.weights.values()) or any(
            v not in range(4) for v in self.relevance.values()
        ):
            raise ValueError("Invalid weights or relevance")
        return self


class Surprise(Model):
    event_id: str
    raw: Number | None
    relative: Number | None
    normalized: Number | None = None
    normalized_method: Literal["UNAVAILABLE_NO_DISTRIBUTION"] = "UNAVAILABLE_NO_DISTRIBUTION"
    direction: Literal["ABOVE", "BELOW", "INLINE", "UNAVAILABLE"]
    magnitude: Literal["LARGE", "SMALL", "ZERO", "UNAVAILABLE"]
    usd_direction: Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN"]
    revision_delta: Number | None
    reason_code: str


class ReleaseGroup(Model):
    group_id: str
    event_ids: list[str]
    alignment: Literal["ALL_ALIGNED", "MOSTLY_ALIGNED", "MIXED", "CONFLICTING", "UNAVAILABLE"]
    bias: Bias
    score: Number
    completeness: Literal["COMPLETE", "PARTIAL"]
    surprises: list[Surprise]


class ReactionWindow(UTCModel):
    seconds: int
    status: Literal["READY", "WAITING", "REACTION_UNAVAILABLE"]
    cutoff: AwareDatetime
    price_before: Number | None = None
    price_after: Number | None = None
    return_percent: Number | None = None
    move_atr: Number | None = None
    range_atr: Number | None = None
    tick_activity_ratio: Number | None = None
    classification: Literal[
        "STRONG_DIRECTIONAL",
        "WHIPSAW",
        "LIQUIDITY_SWEEP_REVERSAL",
        "BREAKOUT",
        "FAILED_BREAKOUT",
        "MUTED",
        "UNCONFIRMED",
    ] = "UNCONFIRMED"


class StructureContext(UTCModel):
    status: Literal["ALIGNED", "CONFLICTING", "WAITING", "STRUCTURE_UNAVAILABLE"]
    upstream_input_id: str | None
    upstream_config_id: str | None
    upstream_algorithm_version: str | None
    upstream_as_of: AwareDatetime | None
    upstream_window_start: AwareDatetime | None
    absence_means: Literal["NOT_INCLUDED_UNKNOWN"] = "NOT_INCLUDED_UNKNOWN"
    references: dict[str, str]  # Explicit present lifecycle only; never infer invalidation from disappearance.


class EventRelevance(Model):
    affected_currency: str
    score: int = Field(ge=0, le=3)
    channels: list[str]


class NewsMarketContext(UTCModel):
    symbol: Literal["XAUUSD"] = "XAUUSD"
    as_of: AwareDatetime
    market_as_of: AwareDatetime | None
    news_engine_version: str = NEWS_VERSION
    config_id: str
    fingerprint: str
    source: str
    source_mode: Mode
    calendar_state: Literal["AVAILABLE", "CALENDAR_UNAVAILABLE"]
    view: Literal["current", "pre", "release", "post", "none"]
    events: list[EconomicEvent] = Field(max_length=200)
    xauusd_relevance: dict[str, EventRelevance]
    upcoming_events: list[EconomicEvent] = Field(max_length=200)
    active_group: ReleaseGroup | None
    active_event_id: str | None
    news_regime: Regime
    macro_bias: Bias
    macro_strength: Literal["STRONG", "MODERATE", "MIXED", "UNKNOWN"]
    multiple_event_risk: bool
    reaction_windows: list[ReactionWindow]
    reaction_state: str
    spread_state: Literal["SPREAD_NORMAL", "SPREAD_ELEVATED", "SPREAD_EXTREME", "UNAVAILABLE"]
    baseline_spread: Number | None
    current_spread: Number | None
    spread_ratio: Number | None
    volatility_state: Literal["NORMAL", "ELEVATED", "EXTREME", "UNAVAILABLE"]
    structure_confirmation: StructureContext
    trade_policy_state: Literal["INFORMATIONAL", "CAUTION", "RESTRICTED"]
    strategy_eligibility: dict[str, Literal["ALLOWED", "CAUTION", "BLOCKED", "WAITING", "ELIGIBLE"]]
    reason_codes: list[str]
    market_source: str | None


class NewsStrategyContext(NewsMarketContext):
    """Dedicated event dependency consumed only by STRAT05/06."""

    release_status: Literal["NO_EVENT", "PRE_NEWS", "WAITING_FOR_ACTUAL", "WAITING_FOR_RELEASE", "RELEASED"] = (
        "NO_EVENT"
    )
    data_quality: Literal["COMPLETE", "PARTIAL", "CONFLICT", "UNAVAILABLE"] = "UNAVAILABLE"


class NewsResponse(NewsStrategyContext):
    generated_at: AwareDatetime
    served_at: AwareDatetime
    cache_age_seconds: float = Field(ge=0)


class CalendarPage(UTCModel):
    events: list[EconomicEvent] = Field(max_length=200)
    source: str
    source_mode: Mode
    state: Literal["AVAILABLE", "CALENDAR_UNAVAILABLE"]
    as_of: AwareDatetime
    generated_at: AwareDatetime
    truncated: bool


class EventDetail(UTCModel):
    event: EconomicEvent
    revisions: list[EconomicEvent] = Field(max_length=100)
    as_of: AwareDatetime


class ObservedQuote(UTCModel):
    timestamp: AwareDatetime
    observed_at: AwareDatetime
    bid: Number
    ask: Number
    source: str

    @model_validator(mode="after")
    def spread_valid(self):
        if self.bid <= 0 or self.ask < self.bid:
            raise ValueError("Invalid quote spread")
        return self
