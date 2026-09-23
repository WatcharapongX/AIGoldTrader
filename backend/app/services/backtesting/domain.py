"""Immutable Batch D1 configuration, coverage, provenance, and lifecycle contracts."""

import datetime as dt
import re
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.services.backtesting.fingerprint import config_fingerprint, coverage_fingerprint, resource_policy_fingerprint
from app.services.backtesting.policy import (
    MAX_REQUESTED_PERIOD_DAYS,
    BacktestResourcePolicy,
    ResourceRejectionCode,
)
from app.services.market_data.domain import Timeframe

BACKTEST_CONTRACT_VERSION = "backtest-contract-1.0.0"
BACKTEST_FINGERPRINT_VERSION = "backtest-fingerprint-1.0.0"
REPLAY_ENGINE_VERSION = "replay-engine-1.0.0"

_TIMEFRAME_ORDER = {timeframe: index for index, timeframe in enumerate(Timeframe)}

StrategyId = Literal["STRAT01", "STRAT02", "STRAT03", "STRAT04", "STRAT05", "STRAT06"]
ProfileId = Literal["research", "smc", "trend", "liquidity", "breakout", "range", "news"]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
BoundedReference = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:/-]+$")]
NonNegativeMoney = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=8, allow_inf_nan=False)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8, allow_inf_nan=False)]


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(dt.UTC)


class RunLifecycle(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunFailureCode(str, Enum):
    COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"
    COVERAGE_INVALID = "COVERAGE_INVALID"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    CANCELLED_BY_OWNER = "CANCELLED_BY_OWNER"
    CANCELLED_BY_SYSTEM = "CANCELLED_BY_SYSTEM"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class CoverageStatus(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    INVALID = "INVALID"


class GapExpectation(str, Enum):
    EXPECTED_SCHEDULED_CLOSURE = "EXPECTED_SCHEDULED_CLOSURE"
    UNEXPECTED = "UNEXPECTED"


class CoverageGapCode(str, Enum):
    SCHEDULED_MARKET_CLOSURE = "SCHEDULED_MARKET_CLOSURE"
    MISSING_CANDLES = "MISSING_CANDLES"
    SOURCE_OUTAGE = "SOURCE_OUTAGE"
    STALE_DATA = "STALE_DATA"


class CostAssumptions(FrozenContract):
    """Scenario costs in absolute XAUUSD price and USD/lot units."""

    spread_price: NonNegativeMoney
    slippage_price_per_side: NonNegativeMoney
    commission_usd_per_lot_per_side: NonNegativeMoney


class BacktestRunConfig(FrozenContract):
    symbol: Literal["XAUUSD"] = "XAUUSD"
    start: AwareDatetime
    end: AwareDatetime
    timeframe: Timeframe
    strategy_id: StrategyId
    profile_id: ProfileId
    initial_balance: PositiveMoney
    costs: CostAssumptions

    @field_validator("start", "end")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_period(self):
        if self.end <= self.start:
            raise ValueError("Backtest end must be after start")
        if self.end - self.start > dt.timedelta(days=MAX_REQUESTED_PERIOD_DAYS):
            raise ValueError(ResourceRejectionCode.PERIOD_LIMIT_EXCEEDED.value)
        return self


class CoverageGap(FrozenContract):
    timeframe: Timeframe
    gap_start: AwareDatetime
    gap_end: AwareDatetime
    code: CoverageGapCode
    expectation: GapExpectation

    @field_validator("gap_start", "gap_end")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_gap(self):
        if self.gap_end <= self.gap_start:
            raise ValueError("Gap end must be after gap start")
        if (
            self.expectation == GapExpectation.EXPECTED_SCHEDULED_CLOSURE
            and self.code != CoverageGapCode.SCHEDULED_MARKET_CLOSURE
        ):
            raise ValueError("Expected gaps must be scheduled closures")
        return self


class TimeframeCoverage(FrozenContract):
    timeframe: Timeframe
    available_start: AwareDatetime
    available_end: AwareDatetime
    requested_events: int = Field(ge=0)
    available_events: int = Field(ge=0)
    source: BoundedReference

    @field_validator("available_start", "available_end")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_range(self):
        if self.available_end <= self.available_start:
            raise ValueError("Timeframe coverage end must be after start")
        return self


class NewsVintageCoverage(FrozenContract):
    required: bool
    available: bool
    source: BoundedReference | None = None
    vintage_start: AwareDatetime | None = None
    vintage_end: AwareDatetime | None = None
    availability_verified_at: AwareDatetime | None = None

    @field_validator("vintage_start", "vintage_end", "availability_verified_at")
    @classmethod
    def utc_clock(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value) if value is not None else None

    @model_validator(mode="after")
    def valid_vintages(self):
        values = (self.source, self.vintage_start, self.vintage_end, self.availability_verified_at)
        if self.available and any(value is None for value in values):
            raise ValueError("Available news vintages require source, range, and verification time")
        if self.vintage_start is not None and self.vintage_end is not None and self.vintage_end <= self.vintage_start:
            raise ValueError("News vintage end must be after start")
        if self.required and not self.available:
            return self
        return self


class DataCoverage(FrozenContract):
    requested_start: AwareDatetime
    requested_end: AwareDatetime
    warmup_start: AwareDatetime
    usable_start: AwareDatetime
    usable_end: AwareDatetime
    symbol: Literal["XAUUSD"] = "XAUUSD"
    timeframe: Timeframe
    source: BoundedReference
    requested_primary_events: int = Field(ge=0)
    available_primary_events: int = Field(ge=0)
    total_candle_inputs: int = Field(ge=0)
    required_timeframes: tuple[Timeframe, ...]
    timeframe_coverage: tuple[TimeframeCoverage, ...]
    gaps: tuple[CoverageGap, ...] = ()
    news_vintages: NewsVintageCoverage
    data_fingerprint: Sha256
    status: CoverageStatus

    @field_validator("requested_start", "requested_end", "warmup_start", "usable_start", "usable_end")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)

    @field_validator("required_timeframes")
    @classmethod
    def canonical_required_timeframes(cls, value: tuple[Timeframe, ...]) -> tuple[Timeframe, ...]:
        return tuple(sorted(value, key=_TIMEFRAME_ORDER.__getitem__))

    @field_validator("timeframe_coverage")
    @classmethod
    def canonical_timeframe_coverage(
        cls, value: tuple[TimeframeCoverage, ...]
    ) -> tuple[TimeframeCoverage, ...]:
        return tuple(sorted(value, key=lambda item: _TIMEFRAME_ORDER[item.timeframe]))

    @field_validator("gaps")
    @classmethod
    def canonical_gaps(cls, value: tuple[CoverageGap, ...]) -> tuple[CoverageGap, ...]:
        return tuple(
            sorted(
                value,
                key=lambda gap: (
                    _TIMEFRAME_ORDER[gap.timeframe],
                    gap.gap_start,
                    gap.gap_end,
                    gap.code.value,
                    gap.expectation.value,
                ),
            )
        )

    @model_validator(mode="after")
    def valid_coverage(self):
        if not self.warmup_start <= self.usable_start <= self.requested_start < self.usable_end <= self.requested_end:
            raise ValueError("Malformed requested, warmup, or usable coverage range")
        if not self.required_timeframes or len(set(self.required_timeframes)) != len(self.required_timeframes):
            raise ValueError("Required timeframes must be unique and non-empty")
        covered = tuple(item.timeframe for item in self.timeframe_coverage)
        if len(set(covered)) != len(covered) or set(covered) != set(self.required_timeframes):
            raise ValueError("Timeframe coverage must match required timeframes exactly")
        if self.timeframe not in self.required_timeframes:
            raise ValueError("Primary timeframe must be present in required timeframes")
        primary = next(item for item in self.timeframe_coverage if item.timeframe == self.timeframe)
        if (
            primary.requested_events != self.requested_primary_events
            or primary.available_events != self.available_primary_events
        ):
            raise ValueError("Primary event counts must match primary timeframe coverage")
        if self.total_candle_inputs < sum(item.available_events for item in self.timeframe_coverage):
            raise ValueError("Total candle inputs cannot be below available timeframe inputs")
        if any(item.source != self.source for item in self.timeframe_coverage):
            raise ValueError("Mixed market data sources are not valid coverage")
        if any(
            item.available_start > self.usable_start or item.available_end < self.usable_end
            for item in self.timeframe_coverage
        ):
            raise ValueError("Per-timeframe coverage must contain the usable period")
        if any(
            gap.timeframe not in self.required_timeframes
            or gap.gap_start < self.warmup_start
            or gap.gap_end > self.requested_end
            for gap in self.gaps
        ):
            raise ValueError("Coverage gap is outside the required timeframe/range")
        if self.news_vintages.required and self.news_vintages.available:
            if (
                self.news_vintages.vintage_start is None
                or self.news_vintages.vintage_end is None
                or self.news_vintages.vintage_start > self.requested_start
                or self.news_vintages.vintage_end < self.requested_end
            ):
                raise ValueError("Required news vintages must cover the requested period")
        unexpected = any(gap.expectation == GapExpectation.UNEXPECTED for gap in self.gaps)
        frame_shortfall = any(item.available_events < item.requested_events for item in self.timeframe_coverage)
        insufficient = (
            self.available_primary_events < self.requested_primary_events
            or frame_shortfall
            or unexpected
            or (self.news_vintages.required and not self.news_vintages.available)
        )
        if self.status == CoverageStatus.SUFFICIENT and insufficient:
            raise ValueError("SUFFICIENT coverage cannot contain a causal coverage shortfall")
        return self


class BacktestProvenance(FrozenContract):
    market_source: BoundedReference
    symbol: Literal["XAUUSD"] = "XAUUSD"
    timeframes: tuple[Timeframe, ...]
    requested_start: AwareDatetime
    requested_end: AwareDatetime
    usable_start: AwareDatetime
    usable_end: AwareDatetime
    strategy_id: StrategyId
    strategy_version: BoundedReference
    profile_id: ProfileId
    risk_policy_version: BoundedReference
    backtest_contract_version: Literal["backtest-contract-1.0.0"] = BACKTEST_CONTRACT_VERSION
    replay_engine_version: Literal["replay-engine-1.0.0"] = REPLAY_ENGINE_VERSION
    costs: CostAssumptions
    data_coverage_fingerprint: Sha256
    data_fingerprint: Sha256
    configuration_fingerprint: Sha256

    @field_validator("requested_start", "requested_end", "usable_start", "usable_end")
    @classmethod
    def utc_clock(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)

    @field_validator("timeframes")
    @classmethod
    def canonical_timeframes(cls, value: tuple[Timeframe, ...]) -> tuple[Timeframe, ...]:
        return tuple(sorted(value, key=_TIMEFRAME_ORDER.__getitem__))

    @model_validator(mode="after")
    def valid_ranges(self):
        if self.requested_end <= self.requested_start or self.usable_end <= self.usable_start:
            raise ValueError("Provenance ranges must be increasing")
        if not self.timeframes or len(set(self.timeframes)) != len(self.timeframes):
            raise ValueError("Provenance timeframes must be unique and non-empty")
        return self


class BacktestRunManifest(FrozenContract):
    config: BacktestRunConfig
    coverage: DataCoverage
    provenance: BacktestProvenance
    resource_policy_fingerprint: Sha256
    contract_version: Literal["backtest-contract-1.0.0"] = BACKTEST_CONTRACT_VERSION
    fingerprint_version: Literal["backtest-fingerprint-1.0.0"] = BACKTEST_FINGERPRINT_VERSION

    @model_validator(mode="after")
    def fail_closed_and_consistent(self):
        if self.coverage.status != CoverageStatus.SUFFICIENT:
            raise ValueError("Executable manifest requires SUFFICIENT coverage")
        if self.config.symbol != self.coverage.symbol or self.config.symbol != self.provenance.symbol:
            raise ValueError("Manifest symbol mismatch")
        if (
            self.config.strategy_id != self.provenance.strategy_id
            or self.config.profile_id != self.provenance.profile_id
        ):
            raise ValueError("Manifest strategy/profile mismatch")
        if self.config.costs != self.provenance.costs:
            raise ValueError("Manifest cost assumptions mismatch")
        if self.config.start != self.coverage.requested_start or self.config.end != self.coverage.requested_end:
            raise ValueError("Manifest requested period mismatch")
        if self.config.start != self.provenance.requested_start or self.config.end != self.provenance.requested_end:
            raise ValueError("Manifest provenance period mismatch")
        if self.config.timeframe != self.coverage.timeframe:
            raise ValueError("Configuration and coverage primary timeframes must match")
        if self.provenance.market_source != self.coverage.source:
            raise ValueError("Manifest market source mismatch")
        if set(self.provenance.timeframes) != set(self.coverage.required_timeframes):
            raise ValueError("Manifest timeframe provenance mismatch")
        if (
            self.provenance.usable_start != self.coverage.usable_start
            or self.provenance.usable_end != self.coverage.usable_end
        ):
            raise ValueError("Manifest usable period mismatch")
        if self.provenance.configuration_fingerprint != config_fingerprint(self.config):
            raise ValueError("Configuration fingerprint does not match config")
        if self.provenance.data_coverage_fingerprint != coverage_fingerprint(self.coverage):
            raise ValueError("Coverage fingerprint does not match coverage")
        if self.provenance.data_fingerprint != self.coverage.data_fingerprint:
            raise ValueError("Data fingerprint mismatch")
        expected_policy = resource_policy_fingerprint(BacktestResourcePolicy())
        if self.resource_policy_fingerprint != expected_policy:
            raise ValueError("Resource policy fingerprint is not the governed D1 policy")
        if self.contract_version != self.provenance.backtest_contract_version:
            raise ValueError("Backtest contract version mismatch")
        if self.config.strategy_id in ("STRAT05", "STRAT06"):
            news = self.coverage.news_vintages
            if not news.required or not news.available:
                raise ValueError("News strategies require causal historical news vintages")
            if (
                news.source is None
                or news.vintage_start is None
                or news.vintage_end is None
                or news.availability_verified_at is None
                or news.vintage_start > self.config.start
                or news.vintage_end < self.config.end
            ):
                raise ValueError("News strategies require vintages covering the requested period")
        return self


class BacktestRunEnvelope(FrozenContract):
    """Lifecycle metadata only; this is not a performance result."""

    run_id: Annotated[str, StringConstraints(pattern=r"^bt_run_[a-z0-9][a-z0-9_-]{7,63}$")]
    semantic_fingerprint: Sha256
    status: RunLifecycle
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    failure_code: RunFailureCode | None = None

    @field_validator("created_at", "started_at", "completed_at")
    @classmethod
    def utc_clock(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value) if value is not None else None

    @model_validator(mode="after")
    def valid_lifecycle_metadata(self):
        cancellation_codes = (
            RunFailureCode.CANCELLED_BY_OWNER,
            RunFailureCode.CANCELLED_BY_SYSTEM,
        )
        if self.status == RunLifecycle.CREATED:
            if self.started_at is not None or self.completed_at is not None or self.failure_code is not None:
                raise ValueError("CREATED cannot have start, completion, or failure metadata")
        elif self.status == RunLifecycle.RUNNING:
            if self.started_at is None or self.completed_at is not None or self.failure_code is not None:
                raise ValueError("RUNNING requires only started_at")
        elif self.status == RunLifecycle.COMPLETED:
            if self.started_at is None or self.completed_at is None or self.failure_code is not None:
                raise ValueError("COMPLETED requires start and completion without failure")
        elif self.status == RunLifecycle.FAILED:
            if self.completed_at is None or self.failure_code is None or self.failure_code in cancellation_codes:
                raise ValueError("FAILED requires completion and a non-cancellation failure code")
        elif self.status == RunLifecycle.CANCELLED:
            if self.completed_at is None or self.failure_code not in cancellation_codes:
                raise ValueError("CANCELLED requires completion and cancellation provenance")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at cannot precede created_at")
        if self.completed_at is not None and self.completed_at < (self.started_at or self.created_at):
            raise ValueError("completed_at cannot precede run start")
        return self


def is_backtest_identity(value: str) -> bool:
    return re.fullmatch(r"bt_(?:run|manifest)_[a-z0-9][a-z0-9_-]{7,63}", value) is not None
