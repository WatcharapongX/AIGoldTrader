"""Declarative D1 simulation/live isolation boundary."""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class ForbiddenSideEffect(str, Enum):
    LIVE_ACCOUNT_MUTATION = "LIVE_ACCOUNT_MUTATION"
    RISK_RESERVATION_MUTATION = "RISK_RESERVATION_MUTATION"
    KILL_SWITCH_MUTATION = "KILL_SWITCH_MUTATION"
    STRATEGY_CANDIDATE_PERSISTENCE = "STRATEGY_CANDIDATE_PERSISTENCE"
    LIVE_ORDER_MUTATION = "LIVE_ORDER_MUTATION"
    LIVE_POSITION_MUTATION = "LIVE_POSITION_MUTATION"
    BROKER_STATE_MUTATION = "BROKER_STATE_MUTATION"
    LIVE_RISK_ENGINE_CALL = "LIVE_RISK_ENGINE_CALL"
    EXTERNAL_AI_CALL = "EXTERNAL_AI_CALL"


class BacktestIsolationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace_prefix: str = "bt_"
    allowed_inputs: tuple[str, ...] = (
        "IMMUTABLE_MARKET_DOMAIN",
        "IMMUTABLE_STRATEGY_IDENTITY",
        "IMMUTABLE_RISK_POLICY_REFERENCE",
        "IMMUTABLE_COVERAGE_PROVENANCE",
    )
    forbidden_side_effects: tuple[ForbiddenSideEffect, ...] = tuple(ForbiddenSideEffect)
    persistence_allowed: bool = False
    network_allowed: bool = False
    wall_clock_allowed: bool = False


D1_ISOLATION_POLICY = BacktestIsolationPolicy()
