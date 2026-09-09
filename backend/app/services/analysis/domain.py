"""Versioned analysis contracts: timestamps record when information became available."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer, WithJsonSchema, model_validator

from app.services.market_data.domain import Price, Source, SymbolName, Timeframe

ALGORITHM_VERSION = "structure-1.0.0"
Number = Annotated[
    Decimal,
    Field(allow_inf_nan=False),
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": r"^-?\d+(?:\.\d+)?$"}, mode="serialization"),
]
State = Literal["BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"]
Direction = Literal["BULLISH", "BEARISH"]
Scope = Literal["INTERNAL", "EXTERNAL"]
Status = Literal["READY", "PARTIAL_HISTORY", "INSUFFICIENT_DATA", "NO_STRUCTURE", "ERROR"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnalysisConfig(Model):
    internal_left: int = Field(default=2, ge=1, le=10)
    internal_right: int = Field(default=2, ge=1, le=10)
    external_left: int = Field(default=5, ge=1, le=20)
    external_right: int = Field(default=5, ge=1, le=20)
    tick_size: Price = Decimal("0.01")
    equal_ticks: int = Field(default=1, ge=0, le=20)
    minimum_gap_ticks: int = Field(default=2, ge=1, le=100)
    atr_period: int = Field(default=14, ge=2, le=50)
    average_period: int = Field(default=20, ge=2, le=100)
    displacement_atr: Number = Field(default=Decimal("1.5"), gt=0, le=10)
    displacement_close_fraction: Number = Field(default=Decimal(".75"), gt=Decimal(".5"), le=1)
    ob_lookback: int = Field(default=20, ge=1, le=100)
    adx_trend_threshold: Number = Field(default=Decimal(25), gt=0, le=100)
    high_volatility_ratio: Number = Field(default=Decimal(".02"), gt=0, le=1)
    low_volatility_ratio: Number = Field(default=Decimal(".001"), gt=0, le=1)
    session_hours: dict[str, list[int]] = Field(
        default_factory=lambda: {"ASIA": [0, 8], "LONDON": [7, 16], "NEW_YORK": [12, 21]}
    )
    max_objects: int = Field(default=128, ge=32, le=256)

    @model_validator(mode="after")
    def valid_windows(self):
        if self.low_volatility_ratio >= self.high_volatility_ratio:
            raise ValueError("Volatility thresholds must be ordered")
        if len(self.session_hours) > 6 or any(
            len(v) != 2 or not 0 <= v[0] < v[1] <= 24 for v in self.session_hours.values()
        ):
            raise ValueError("Sessions must be bounded same-day UTC hour windows")
        return self


class History(Model):
    requested: int
    returned: int
    closed: int
    status: Literal["COMPLETE", "PARTIAL", "EMPTY"]


class ModuleStatus(Model):
    status: Status
    minimum_bars_required: int
    available_bars: int
    reason: str


class SwingPoint(Model):
    id: str
    scope: Scope
    kind: Literal["HIGH", "LOW"]
    label: Literal["SH", "SL", "HH", "HL", "LH", "LL", "EQH", "EQL"]
    price: Number
    swing_time: AwareDatetime
    confirmed_at: AwareDatetime
    confirmation: Literal["CONFIRMED"] = "CONFIRMED"


class StructureEvent(Model):
    id: str
    scope: Scope
    kind: Literal["BOS", "CHOCH", "MSS"]
    direction: Direction
    price: Number
    swing_id: str
    swing_time: AwareDatetime
    occurred_at: AwareDatetime
    confirmed_at: AwareDatetime
    displacement: bool
    parent_event_id: str | None = None
    confirmation: Literal["CONFIRMED"] = "CONFIRMED"


class LiquidityLevel(Model):
    id: str
    kind: Literal["BSL", "SSL", "EQH", "EQL", "PDH", "PDL", "PWH", "PWL", "SESSION_HIGH", "SESSION_LOW"]
    side: Literal["HIGH", "LOW"]
    price: Number
    created_at: AwareDatetime
    confirmed_at: AwareDatetime
    source_ids: list[str]
    status: Literal["ACTIVE", "SWEPT", "INVALIDATED"] = "ACTIVE"
    swept_at: AwareDatetime | None = None
    sweep_price: Number | None = None
    ended_at: AwareDatetime | None = None


class Zone(Model):
    id: str
    kind: Literal["FVG", "IFVG", "OB", "BREAKER"]
    direction: Direction
    lower_bound: Number
    upper_bound: Number
    occurred_at: AwareDatetime
    confirmed_at: AwareDatetime
    status: Literal["OPEN", "PARTIALLY_FILLED", "FILLED", "ACTIVE", "MITIGATED", "INVALIDATED"]
    source_event_id: str | None = None
    fill_fraction: Number = Decimal(0)
    ended_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def bounds(self):
        if self.lower_bound >= self.upper_bound or not 0 <= self.fill_fraction <= 1:
            raise ValueError("Invalid zone")
        return self


class DealingRange(Model):
    lower_bound: Number
    equilibrium: Number
    upper_bound: Number
    origin_time: AwareDatetime
    confirmed_at: AwareDatetime
    direction: Direction
    swing_ids: list[str]
    location: Literal["PREMIUM", "DISCOUNT", "EQUILIBRIUM"]
    retracement_62: Number
    retracement_79: Number


class IndicatorValue(Model):
    value: Number | None
    minimum_bars_required: int
    status: Literal["READY", "INSUFFICIENT_DATA"]


class SessionRange(Model):
    name: str
    start: AwareDatetime
    end: AwareDatetime
    high: Number
    low: Number
    confirmed_at: AwareDatetime


class RetentionPolicy(Model):
    mode: Literal["BOUNDED_SNAPSHOT"] = "BOUNDED_SNAPSHOT"
    absence_means: Literal["NOT_INCLUDED_UNKNOWN"] = "NOT_INCLUDED_UNKNOWN"
    absence_is_invalidation: Literal[False] = False


class AnalysisSnapshot(Model):
    symbol: SymbolName
    timeframe: Timeframe
    source: Source
    algorithm_version: str
    config_id: str
    retention: RetentionPolicy = Field(default_factory=RetentionPolicy)
    input_id: str
    window_start: AwareDatetime | None
    history: History
    as_of: AwareDatetime | None
    modules: dict[str, ModuleStatus]
    internal_state: State
    external_state: State
    swings: list[SwingPoint] = Field(max_length=256)
    events: list[StructureEvent] = Field(max_length=256)
    liquidity: list[LiquidityLevel] = Field(max_length=256)
    zones: list[Zone] = Field(max_length=256)
    dealing_range: DealingRange | None
    indicators: dict[str, IndicatorValue]
    sessions: list[SessionRange] = Field(max_length=32)
    current_sessions: list[str]
    regime: Literal[
        "TRENDING_UP",
        "TRENDING_DOWN",
        "RANGING",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "BREAKOUT",
        "PULLBACK",
        "UNKNOWN",
    ]
    news_context: Literal["UNKNOWN"] = "UNKNOWN"
    confluence_counts: dict[str, int]


class ContextRow(Model):
    timeframe: Timeframe
    state: State
    history: History
    status: Status
    as_of: AwareDatetime | None


class MultiTimeframeContext(Model):
    symbol: SymbolName
    source: Source
    algorithm_version: str
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL", "MIXED", "UNKNOWN"]
    timeframes: list[ContextRow] = Field(max_length=9)


class AnalysisResponse(AnalysisSnapshot):
    generated_at: AwareDatetime
    served_at: AwareDatetime
    cache_age_seconds: float = Field(ge=0)
