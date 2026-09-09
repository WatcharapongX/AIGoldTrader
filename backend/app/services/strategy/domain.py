"""Frozen strategy contracts; nested upstream payloads are immutable canonical JSON."""

import datetime as dt
import hashlib
import json
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.services.analysis.domain import AnalysisSnapshot, Model, Number
from app.services.market_data.domain import Candle, Timeframe
from app.services.news.domain import EconomicEvent, NewsStrategyContext

VERSION = "strategy-1.2.1"
EVALUATION_VERSION = "evaluation-2.0.0"
Style = Literal["SCALP", "DAY_TRADE", "SWING", "RUN_TREND"]
Direction = Literal["LONG", "SHORT", "NO_TRADE"]
State = Literal[
    "DETECTED", "WAITING_CONFIRMATION", "READY", "BLOCKED_CONTEXT", "NO_TRADE", "INVALIDATED", "EXPIRED", "SUPERSEDED"
]


def fingerprint(value: object) -> str:
    def encode(item: object) -> object:
        if isinstance(item, Model):
            return item.model_dump(mode="json")
        if isinstance(item, (dt.datetime, dt.date)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return format(item, "f")
        raise TypeError(type(item).__name__)

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode, ensure_ascii=False).encode()
    ).hexdigest()


class SessionConfig(Model):
    name: Literal["ASIA", "LONDON", "NEW_YORK"]
    timezone: str
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def valid(self):
        ZoneInfo(self.timezone)
        if self.start_hour >= self.end_hour:
            raise ValueError("Session must be a same-local-day interval")
        return self


class TimeframeMap(Model):
    style: Style
    context: Timeframe
    bias: Timeframe
    setup: Timeframe
    trigger: Timeframe
    minimum_bars: int = Field(default=60, ge=35, le=300)


def default_maps() -> tuple[TimeframeMap, ...]:
    return (
        TimeframeMap(style="SCALP", context=Timeframe.H1, bias=Timeframe.M15, setup=Timeframe.M5, trigger=Timeframe.M1),
        TimeframeMap(
            style="DAY_TRADE", context=Timeframe.H4, bias=Timeframe.H1, setup=Timeframe.M15, trigger=Timeframe.M5
        ),
        TimeframeMap(style="SWING", context=Timeframe.W1, bias=Timeframe.D1, setup=Timeframe.H4, trigger=Timeframe.H1),
        TimeframeMap(
            style="RUN_TREND", context=Timeframe.D1, bias=Timeframe.H4, setup=Timeframe.H1, trigger=Timeframe.M15
        ),
    )


class StrategyConfig(Model):
    version: str = VERSION
    maps: tuple[TimeframeMap, ...] = Field(default_factory=default_maps)
    sessions: tuple[SessionConfig, ...] = (
        SessionConfig(name="ASIA", timezone="Asia/Tokyo", start_hour=9, end_hour=17),
        SessionConfig(name="LONDON", timezone="Europe/London", start_hour=8, end_hour=17),
        SessionConfig(name="NEW_YORK", timezone="America/New_York", start_hour=8, end_hour=17),
    )
    tolerance_atr: Number = Field(default=Decimal(".15"), gt=0, le=1)
    stop_atr_buffer: Number = Field(default=Decimal(".2"), ge=0, le=3)
    minimum_rr: Number = Field(default=Decimal("1.5"), gt=0, le=10)
    expiry_trigger_bars: int = Field(default=12, ge=1, le=100)
    event_lookback_bars: int = Field(default=24, ge=3, le=100)
    pattern_lookback_bars: int = Field(default=100, ge=30, le=300)
    pattern_min_separation: int = Field(default=2, ge=1, le=20)
    macd_fast: int = Field(default=12, ge=2, le=50)
    macd_slow: int = Field(default=26, ge=3, le=100)
    macd_signal: int = Field(default=9, ge=2, le=30)
    stochastic_period: int = Field(default=14, ge=2, le=50)
    stochastic_smooth: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def valid(self):
        if self.macd_fast >= self.macd_slow:
            raise ValueError("MACD fast must be below slow")
        if {m.style for m in self.maps} != {"SCALP", "DAY_TRADE", "SWING", "RUN_TREND"} or len(self.maps) != 4:
            raise ValueError("Exactly one mapping per style required")
        if len({s.name for s in self.sessions}) != len(self.sessions):
            raise ValueError("Duplicate session")
        return self


class Evidence(Model):
    code: str
    description_th: str
    source_ids: tuple[str, ...] = ()
    confirmed_at: AwareDatetime | None = None
    weight: int = Field(default=0, ge=-100, le=100)


class KeyLevel(Model):
    id: str
    symbol: str
    timeframe: Timeframe
    kind: str
    price: Number
    upper: Number | None = None
    origin: AwareDatetime
    confirmed_at: AwareDatetime | None
    valid_from: AwareDatetime
    status: Literal["CONFIRMED", "PROVISIONAL", "SWEPT", "INVALIDATED"]
    source_ids: tuple[str, ...]
    input_id: str


class SessionRange(Model):
    id: str
    name: str
    timezone: str
    start: AwareDatetime
    end: AwareDatetime
    high: Number
    low: Number
    status: Literal["CONFIRMED", "PROVISIONAL"]
    complete_coverage: bool


class Indicator(Model):
    name: str
    value: Number | None
    minimum_bars: int
    status: Literal["READY", "WARMUP", "UNAVAILABLE"]


class PatternPoint(Model):
    id: str
    time: AwareDatetime
    confirmed_at: AwareDatetime
    price: Number
    kind: Literal["HIGH", "LOW"]


class Pattern(Model):
    id: str
    kind: str
    direction: Direction
    status: Literal["FORMING", "CANDIDATE", "CONFIRMED", "FAILED", "INVALIDATED", "EXPIRED"]
    points: tuple[PatternPoint, ...]
    neckline: Number
    upper: Number
    lower: Number
    confirmed_at: AwareDatetime | None
    detected_at: AwareDatetime
    expires_at: AwareDatetime
    source_ids: tuple[str, ...]
    reason_th: str


class Frame(Model):
    timeframe: Timeframe
    input_id: str
    config_id: str
    algorithm_version: str
    window_start: AwareDatetime | None
    as_of: AwareDatetime | None
    bars: int
    requested: int
    candles_json: str
    analysis_json: str
    indicators: tuple[Indicator, ...]
    patterns: tuple[Pattern, ...]

    @property
    def candles(self) -> list[Candle]:
        return [Candle.model_validate(c) for c in json.loads(self.candles_json)]

    @property
    def analysis(self) -> AnalysisSnapshot:
        return AnalysisSnapshot.model_validate_json(self.analysis_json)


class MarketSafetyContext(Model):
    """Market-only quote and closed-bar safety; never derived from an event."""

    spread_state: Literal["SPREAD_NORMAL", "SPREAD_ELEVATED", "SPREAD_EXTREME", "UNAVAILABLE"] = "UNAVAILABLE"
    volatility_state: Literal["NORMAL", "ELEVATED", "EXTREME", "UNAVAILABLE"] = "UNAVAILABLE"
    current_spread: Number | None = None
    baseline_spread: Number | None = None
    quote_as_of: AwareDatetime | None = None
    source_ids: tuple[str, ...] = ()


class StrategyMarketContext(Model):
    id: str
    symbol: str
    source: str
    mode: Literal["ACTUAL", "REPLAY"]
    as_of: AwareDatetime
    config_id: str
    strategy_config_json: str
    analysis_config_json: str
    engine_version: str = VERSION
    tick_size: Number | None
    frames: tuple[Frame, ...]
    key_levels: tuple[KeyLevel, ...] = Field(max_length=4096)
    sessions: tuple[SessionRange, ...]
    current_session: str
    market_context_id: str = ""
    market_safety: MarketSafetyContext = Field(default_factory=MarketSafetyContext)
    news_json: str | None
    news_fingerprint: str | None
    absence_means: Literal["NOT_INCLUDED_UNKNOWN"] = "NOT_INCLUDED_UNKNOWN"
    execution: Literal["ANALYSIS_ONLY"] = "ANALYSIS_ONLY"

    @property
    def news(self) -> NewsStrategyContext:
        if self.news_json is None:
            raise ValueError("News is not a dependency of this persisted projection")
        return NewsStrategyContext.model_validate_json(self.news_json)

    def dependency_id(self, strategy_id: str) -> str:
        return self.id if strategy_id in ("STRAT05", "STRAT06") else self.market_context_id

    def dependency_projection(self, strategy_id: str) -> "StrategyMarketContext":
        if strategy_id in ("STRAT05", "STRAT06"):
            return self
        return self.model_copy(
            update={"id": self.dependency_id(strategy_id), "news_json": None, "news_fingerprint": None}
        )

    def frame(self, timeframe: Timeframe) -> Frame | None:
        return next((f for f in self.frames if f.timeframe == timeframe), None)


class TraderProfile(Model):
    id: str
    name: str
    description_th: str
    style: Style
    enabled: bool = True
    allowed_strategies: tuple[str, ...]
    timeframe_map: TimeframeMap
    config_id: str
    candidate_policy: Literal["ALL_EXPLAINED"] = "ALL_EXPLAINED"
    execution_mode: Literal["ANALYSIS_ONLY"] = "ANALYSIS_ONLY"
    created_at: AwareDatetime = dt.datetime(2026, 9, 9, tzinfo=dt.UTC)
    updated_at: AwareDatetime = dt.datetime(2026, 9, 9, tzinfo=dt.UTC)


class StrategyDefinition(Model):
    id: str
    name: str
    version: str = VERSION
    category: str
    styles: tuple[Style, ...]
    required_context: tuple[str, ...]
    minimum_bars: int = 60
    description_th: str


class Target(Model):
    name: str
    price: Number
    source_id: str
    rr: Number


class TradePlanSuggestion(Model):
    id: str
    candidate_id: str
    symbol: str
    direction: Literal["LONG", "SHORT"]
    entry_type: Literal["MARKET_REFERENCE", "LIMIT_ZONE", "RETEST_ZONE", "BREAKOUT_RETEST"]
    entry_lower: Number
    entry_upper: Number
    entry_source_id: str
    stop_loss: Number
    stop_source_id: str
    invalidation_th: str
    targets: tuple[Target, ...]
    score: int = Field(ge=0, le=100)
    evidence: tuple[Evidence, ...]
    warnings_th: tuple[str, ...]
    news_state: str
    status: Literal["SUGGESTION_ONLY"] = "SUGGESTION_ONLY"
    as_of: AwareDatetime
    context_id: str
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def geometry(self):
        low, high, stop = self.entry_lower, self.entry_upper, self.stop_loss
        if low <= 0 or stop <= 0 or low > high or self.expires_at <= self.as_of or len(self.targets) < 2:
            raise ValueError("Invalid plan geometry or lifetime")
        if not (stop < low if self.direction == "LONG" else stop > high):
            raise ValueError("Stop must be outside the whole entry zone")
        last = high if self.direction == "LONG" else low
        for target in self.targets:
            if (
                target.rr <= 0
                or not target.source_id
                or not (target.price > last if self.direction == "LONG" else 0 < target.price < last)
            ):
                raise ValueError("Targets must be positive and ordered beyond entry")
            last = target.price
        return self


class NewsCandidateProvenance(Model):
    context_fingerprint: str
    source: str
    as_of: AwareDatetime
    news_engine_version: str
    event_vintages: tuple[EconomicEvent, ...] = Field(max_length=200)
    phase3_input_ids: tuple[str, ...]


class SetupCandidate(Model):
    id: str
    profile_id: str
    strategy_id: str
    strategy_version: str = VERSION
    symbol: str
    direction: Direction
    status: State
    score: int = Field(ge=0, le=100)
    detected_at: AwareDatetime
    confirmed_at: AwareDatetime | None
    expires_at: AwareDatetime
    context_id: str
    upstream_ids: tuple[str, ...]
    news_provenance: NewsCandidateProvenance | None = None
    evidence: tuple[Evidence, ...]
    missing_conditions: tuple[str, ...]
    conflicts: tuple[str, ...]
    invalidation_th: str
    plan: TradePlanSuggestion | None


class Transition(Model):
    id: str
    candidate_id: str
    context_id: str
    from_status: State
    to_status: State
    as_of: AwareDatetime
    reason_th: str


class Evaluation(Model):
    id: str
    identity_version: str = "legacy-aggregate-v1"
    scope: Literal["LEGACY", "REQUEST", "STRATEGY", "EMPTY"] = "LEGACY"
    component_ids: dict[str, str] = Field(default_factory=dict)
    context: StrategyMarketContext
    profiles: tuple[TraderProfile, ...]
    strategies: tuple[StrategyDefinition, ...]
    candidates: tuple[SetupCandidate, ...]
    modes: tuple[str, ...] = ("SINGLE_STRATEGY", "MULTI_STRATEGY", "MULTI_TRADER")
    adaptive_status: Literal["RESERVED_DISABLED"] = "RESERVED_DISABLED"


class StrategyResponse(Model):
    evaluation: Evaluation
    generated_at: AwareDatetime
    served_at: AwareDatetime
    stale: bool

    @field_validator("generated_at", "served_at")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return value.astimezone(dt.UTC)
