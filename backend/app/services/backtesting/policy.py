"""Server-owned Batch D resource ceilings and pure rejection semantics."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_REQUESTED_PERIOD_DAYS = 366
MAX_PRIMARY_REPLAY_EVENTS = 250_000
MAX_TOTAL_CANDLE_INPUTS = 1_000_000
MAX_ACTIVE_RUNS_PER_USER = 1
MAX_ACTIVE_RUNS_SYSTEM = 2
MAX_PENDING_RUNS = 8
MAX_CANDIDATES_PER_RUN = 100_000
MAX_TRADES_PER_RUN = 100_000
MAX_EQUITY_POINTS_PER_RUN = 250_000
MAX_ESTIMATED_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_API_PAGE_SIZE = 500


class ResourceRejectionCode(str, Enum):
    PERIOD_LIMIT_EXCEEDED = "PERIOD_LIMIT_EXCEEDED"
    PRIMARY_EVENT_LIMIT_EXCEEDED = "PRIMARY_EVENT_LIMIT_EXCEEDED"
    TOTAL_CANDLE_LIMIT_EXCEEDED = "TOTAL_CANDLE_LIMIT_EXCEEDED"
    CANDIDATE_LIMIT_EXCEEDED = "CANDIDATE_LIMIT_EXCEEDED"
    TRADE_LIMIT_EXCEEDED = "TRADE_LIMIT_EXCEEDED"
    EQUITY_POINT_LIMIT_EXCEEDED = "EQUITY_POINT_LIMIT_EXCEEDED"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    ACTIVE_RUN_LIMIT_EXCEEDED = "ACTIVE_RUN_LIMIT_EXCEEDED"
    SYSTEM_RUN_LIMIT_EXCEEDED = "SYSTEM_RUN_LIMIT_EXCEEDED"
    QUEUE_LIMIT_EXCEEDED = "QUEUE_LIMIT_EXCEEDED"


class BacktestResourcePolicy(BaseModel):
    """Immutable server authority; every field is fixed to the governed value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_requested_period_days: Literal[366] = MAX_REQUESTED_PERIOD_DAYS
    max_primary_replay_events: Literal[250_000] = MAX_PRIMARY_REPLAY_EVENTS
    max_total_candle_inputs: Literal[1_000_000] = MAX_TOTAL_CANDLE_INPUTS
    max_active_runs_per_user: Literal[1] = MAX_ACTIVE_RUNS_PER_USER
    max_active_runs_system: Literal[2] = MAX_ACTIVE_RUNS_SYSTEM
    max_pending_runs: Literal[8] = MAX_PENDING_RUNS
    max_candidates_per_run: Literal[100_000] = MAX_CANDIDATES_PER_RUN
    max_trades_per_run: Literal[100_000] = MAX_TRADES_PER_RUN
    max_equity_points_per_run: Literal[250_000] = MAX_EQUITY_POINTS_PER_RUN
    max_estimated_output_bytes: Literal[134_217_728] = MAX_ESTIMATED_OUTPUT_BYTES
    max_api_page_size: Literal[500] = MAX_API_PAGE_SIZE


class ResourceUsage(BaseModel):
    """Declared counters for future enforcement; it allocates no run output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    primary_replay_events: int = Field(ge=0)
    total_candle_inputs: int = Field(ge=0)
    active_runs_for_user: int = Field(ge=0)
    active_runs_system: int = Field(ge=0)
    pending_runs: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    equity_point_count: int = Field(ge=0)
    estimated_output_bytes: int = Field(ge=0)


class ResourceValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    rejection_codes: tuple[ResourceRejectionCode, ...] = ()


def validate_resource_usage(
    usage: ResourceUsage, policy: BacktestResourcePolicy | None = None
) -> ResourceValidationResult:
    """Return all stable rejection codes without infrastructure side effects."""

    limits = policy or BacktestResourcePolicy()
    checks = (
        (
            usage.primary_replay_events > limits.max_primary_replay_events,
            ResourceRejectionCode.PRIMARY_EVENT_LIMIT_EXCEEDED,
        ),
        (usage.total_candle_inputs > limits.max_total_candle_inputs, ResourceRejectionCode.TOTAL_CANDLE_LIMIT_EXCEEDED),
        (usage.candidate_count > limits.max_candidates_per_run, ResourceRejectionCode.CANDIDATE_LIMIT_EXCEEDED),
        (usage.trade_count > limits.max_trades_per_run, ResourceRejectionCode.TRADE_LIMIT_EXCEEDED),
        (
            usage.equity_point_count > limits.max_equity_points_per_run,
            ResourceRejectionCode.EQUITY_POINT_LIMIT_EXCEEDED,
        ),
        (usage.estimated_output_bytes > limits.max_estimated_output_bytes, ResourceRejectionCode.OUTPUT_LIMIT_EXCEEDED),
        (
            usage.active_runs_for_user >= limits.max_active_runs_per_user,
            ResourceRejectionCode.ACTIVE_RUN_LIMIT_EXCEEDED,
        ),
        (usage.active_runs_system >= limits.max_active_runs_system, ResourceRejectionCode.SYSTEM_RUN_LIMIT_EXCEEDED),
        (usage.pending_runs >= limits.max_pending_runs, ResourceRejectionCode.QUEUE_LIMIT_EXCEEDED),
    )
    codes = tuple(code for rejected, code in checks if rejected)
    return ResourceValidationResult(accepted=not codes, rejection_codes=codes)
