"""Immutable D2C stateless policy-evidence contracts; no execution authority."""

import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.services.backtesting.domain import FrozenContract, ProfileId, Sha256, StrategyId
from app.services.backtesting.policy import MAX_CANDIDATES_PER_RUN
from app.services.risk.domain import RiskPolicy
from app.services.risk.policy_domain import PureRiskResult

RISK_REPLAY_INTEGRATION_VERSION = "risk-replay-1.0.0"
SpecNumber = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8, allow_inf_nan=False)]
RequestedRisk = Annotated[Decimal, Field(ge=0, le=100, max_digits=12, decimal_places=8, allow_inf_nan=False)]


class RiskReplayFailureCode(str, Enum):
    INPUT_INVALID = "RISK_REPLAY_INPUT_INVALID"
    CONFIGURATION_INVALID = "RISK_REPLAY_CONFIGURATION_INVALID"
    NEWS_UNAVAILABLE = "RISK_NEWS_UNAVAILABLE"
    SYMBOL_SPEC_INVALID = "RISK_SYMBOL_SPEC_INVALID"
    CAUSALITY_VIOLATION = "RISK_CAUSALITY_VIOLATION"
    RESOURCE_LIMIT_EXCEEDED = "RISK_RESOURCE_LIMIT_EXCEEDED"
    POLICY_EVALUATION_FAILED = "RISK_POLICY_EVALUATION_FAILED"


class RiskReplayError(ValueError):
    """Stable public integration failure; chained diagnostics are internal."""

    def __init__(self, code: RiskReplayFailureCode):
        self.code = code
        super().__init__(code.value)


class BacktestSymbolSpecAssumption(FrozenContract):
    """Explicit scenario economics, never a historically observed broker spec."""

    symbol: Literal["XAUUSD"] = "XAUUSD"
    source: Literal["BACKTEST_ASSUMPTION"] = "BACKTEST_ASSUMPTION"
    tick_size: SpecNumber
    tick_value: SpecNumber
    contract_size: SpecNumber
    volume_min: SpecNumber
    volume_max: SpecNumber
    volume_step: SpecNumber
    digits: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def valid_volumes(self):
        if self.volume_min > self.volume_max or self.volume_step > self.volume_min:
            raise ValueError("Invalid scenario volume bounds")
        return self


class RiskReplayConfig(FrozenContract):
    policy: RiskPolicy
    symbol_specification: BacktestSymbolSpecAssumption
    caller_requested_risk_pct: RequestedRisk | None = None


class RiskEvaluationStatus(str, Enum):
    EVALUATED = "EVALUATED"
    NOT_EVALUATED_NO_PLAN = "NOT_EVALUATED_NO_PLAN"


class ReplayRiskEvent(FrozenContract):
    as_of: AwareDatetime
    profile_id: ProfileId
    strategy_id: StrategyId
    candidate_id: str = Field(min_length=1, max_length=128)
    plan_id: str | None = Field(default=None, max_length=128)
    replay_strategy_event_fingerprint: Sha256
    risk_evaluation_status: RiskEvaluationStatus
    risk_input_fingerprint: Sha256 | None = None
    pure_risk_result: PureRiskResult | None = None
    pure_risk_fingerprint: Sha256 | None = None
    quote_timestamp: AwareDatetime | None = None
    quote_observed_at: AwareDatetime | None = None
    risk_event_fingerprint: Sha256

    @field_validator("as_of", "quote_timestamp", "quote_observed_at")
    @classmethod
    def utc_clock(cls, value: dt.datetime | None):
        return value.astimezone(dt.UTC) if value is not None else None

    @model_validator(mode="after")
    def consistent_disposition(self):
        evidence = (self.plan_id, self.risk_input_fingerprint, self.pure_risk_result, self.pure_risk_fingerprint)
        if self.risk_evaluation_status == RiskEvaluationStatus.EVALUATED:
            if any(value is None for value in evidence):
                raise ValueError("Evaluated event requires plan and pure Risk evidence")
            if self.pure_risk_fingerprint != self.pure_risk_result.semantic_fingerprint:
                raise ValueError("Pure fingerprint mismatch")
        elif any(value is not None for value in (*evidence, self.quote_timestamp, self.quote_observed_at)):
            raise ValueError("No-plan event cannot contain Risk evidence")
        if (self.quote_timestamp is None) != (self.quote_observed_at is None):
            raise ValueError("Quote requires both timestamp and observation evidence")
        if any(value is not None and value > self.as_of for value in (self.quote_timestamp, self.quote_observed_at)):
            raise ValueError("Future quote evidence")
        return self


class RiskReplayResult(FrozenContract):
    integration_version: Literal["risk-replay-1.0.0"] = RISK_REPLAY_INTEGRATION_VERSION
    evaluation_model: Literal["STATELESS_BASELINE_POLICY_EVIDENCE"] = "STATELESS_BASELINE_POLICY_EVIDENCE"
    source_replay_input_fingerprint: Sha256
    source_replay_fingerprint: Sha256
    risk_configuration_fingerprint: Sha256
    risk_replay_input_fingerprint: Sha256
    cutoff: AwareDatetime
    strategy_events_seen: int = Field(ge=0, le=MAX_CANDIDATES_PER_RUN)
    risk_events_evaluated: int = Field(ge=0, le=MAX_CANDIDATES_PER_RUN)
    no_plan_events: int = Field(ge=0, le=MAX_CANDIDATES_PER_RUN)
    events: tuple[ReplayRiskEvent, ...] = Field(max_length=MAX_CANDIDATES_PER_RUN)
    risk_replay_fingerprint: Sha256

    @field_validator("cutoff")
    @classmethod
    def utc_clock(cls, value: dt.datetime):
        return value.astimezone(dt.UTC)

    @model_validator(mode="after")
    def consistent_events(self):
        keys = [(e.as_of, e.profile_id, e.strategy_id, e.candidate_id) for e in self.events]
        evaluated = sum(e.risk_evaluation_status == RiskEvaluationStatus.EVALUATED for e in self.events)
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("Risk events must be unique and canonically ordered")
        if (
            self.strategy_events_seen != len(self.events)
            or self.risk_events_evaluated != evaluated
            or self.no_plan_events != len(self.events) - evaluated
            or any(e.as_of > self.cutoff for e in self.events)
        ):
            raise ValueError("Risk replay counters or cutoff mismatch")
        return self
