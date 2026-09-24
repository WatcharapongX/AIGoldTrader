"""Immutable contracts for the pure D2A causal replay foundation."""

import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.services.analysis.domain import AnalysisConfig, Model
from app.services.backtesting.domain import BacktestRunManifest, ProfileId, Sha256, StrategyId
from app.services.market_data.domain import Candle, Timeframe
from app.services.news.domain import EconomicEvent, NewsConfig, ObservedQuote
from app.services.strategy.domain import (
    SetupCandidate,
    State,
    StrategyConfig,
    StrategyMarketContext,
    TradePlanSuggestion,
)


class ReplayFailureCode(str, Enum):
    INPUT_INVALID = "REPLAY_INPUT_INVALID"
    NON_MONOTONIC = "REPLAY_NON_MONOTONIC"
    RESOURCE_LIMIT_EXCEEDED = "REPLAY_RESOURCE_LIMIT_EXCEEDED"
    CAUSALITY_VIOLATION = "REPLAY_CAUSALITY_VIOLATION"
    NEWS_UNAVAILABLE = "REPLAY_NEWS_UNAVAILABLE"
    STRATEGY_CONFIG_INVALID = "REPLAY_STRATEGY_CONFIG_INVALID"


class ReplayError(ValueError):
    """Stable public replay failure; chained diagnostics remain internal."""

    def __init__(self, code: ReplayFailureCode):
        self.code = code
        super().__init__(code.value)


class ReplayInputs(Model):
    manifest: BacktestRunManifest
    candles: dict[Timeframe, tuple[Candle, ...]]
    news_events: tuple[EconomicEvent, ...] = Field(default=(), max_length=2000)
    quotes: tuple[ObservedQuote, ...] = Field(default=(), max_length=3600)
    strategy_config: StrategyConfig = Field(default_factory=StrategyConfig)
    analysis_config: AnalysisConfig = Field(default_factory=AnalysisConfig)
    news_config: NewsConfig = Field(default_factory=NewsConfig)
    tick_size: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)] | None = None
    news_source: str = Field(default="historical_unavailable", min_length=1, max_length=128)
    news_mode: str = Field(default="UNAVAILABLE", pattern=r"^(FIXTURE|LIVE|UNAVAILABLE)$")
    calendar_available: bool = False

    @model_validator(mode="after")
    def bounded_collections(self):
        if len(self.candles) > len(Timeframe):
            raise ValueError("Too many timeframe inputs")
        return self


class ReplayStrategyEvent(Model):
    as_of: AwareDatetime
    profile_id: ProfileId
    strategy_id: StrategyId
    context_id: str
    candidate_id: str
    candidate_status: State
    context: StrategyMarketContext
    candidate: SetupCandidate
    trade_plan: TradePlanSuggestion | None
    event_fingerprint: Sha256

    @field_validator("as_of")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return value.astimezone(dt.UTC)

    @model_validator(mode="after")
    def consistent_identity(self):
        if (
            self.context.as_of != self.as_of
            or self.candidate.detected_at != self.as_of
            or self.candidate.id != self.candidate_id
            or self.candidate.context_id != self.context_id
            or self.context.id != self.context_id
            or self.candidate.profile_id != self.profile_id
            or self.candidate.strategy_id != self.strategy_id
            or self.candidate.status != self.candidate_status
            or self.candidate.plan != self.trade_plan
        ):
            raise ValueError("Replay event identity mismatch")
        return self


class ReplayResult(Model):
    replay_engine_version: str = Field(pattern=r"^replay-engine-\d+\.\d+\.\d+$")
    replay_input_fingerprint: Sha256
    cutoff: AwareDatetime
    primary_events_processed: int = Field(ge=0)
    events: tuple[ReplayStrategyEvent, ...]
    replay_fingerprint: Sha256

    @field_validator("cutoff")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return value.astimezone(dt.UTC)

    @model_validator(mode="after")
    def stable_order(self):
        keys = [(e.as_of, e.profile_id, e.strategy_id, e.candidate_id) for e in self.events]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("Replay events must be unique and canonically ordered")
        return self


class ReplayClock:
    """Aware-UTC clock advanced only by canonical historical event timestamps."""

    def __init__(self) -> None:
        self._current: dt.datetime | None = None

    @property
    def current(self) -> dt.datetime | None:
        return self._current

    def advance(self, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReplayError(ReplayFailureCode.INPUT_INVALID)
        value = value.astimezone(dt.UTC)
        if self._current is not None and value <= self._current:
            raise ReplayError(ReplayFailureCode.NON_MONOTONIC)
        self._current = value
        return value
