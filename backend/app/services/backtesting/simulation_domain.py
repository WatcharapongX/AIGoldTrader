"""D3/D4 deterministic simulated fills, evolving state, ledgers, and metrics.

Simulation only: no broker, OMS, paper execution, or live position authority.
Entry is eligible only on candles strictly after plan creation; a plan cannot
fill from its creation candle. SL wins same-candle ambiguity (worst case).
"""

from decimal import Decimal
from enum import Enum

from pydantic import AwareDatetime, Field

from app.services.backtesting.domain import FrozenContract, ProfileId, Sha256, StrategyId

SIMULATION_VERSION = "simulation-1.0.0"
METRICS_VERSION = "metrics-1.0.0"


class TradeStatus(str, Enum):
    FILLED_CLOSED = "FILLED_CLOSED"
    EXPIRED_UNFILLED = "EXPIRED_UNFILLED"
    NOT_FILLED_CONCURRENT = "NOT_FILLED_CONCURRENT"
    RISK_BLOCKED = "RISK_BLOCKED"
    NO_PLAN = "NO_PLAN"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    END_OF_RUN = "END_OF_RUN"
    NONE = "NONE"


class SimulatedTrade(FrozenContract):
    trade_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    plan_id: str | None = Field(default=None, max_length=128)
    strategy_id: StrategyId
    profile_id: ProfileId
    direction: str | None = None
    status: TradeStatus
    exit_reason: ExitReason = ExitReason.NONE
    ambiguous_sl_tp: bool = False
    planned_at: AwareDatetime
    entry_at: AwareDatetime | None = None
    exit_at: AwareDatetime | None = None
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    position_size: Decimal = Decimal("0")
    approved_risk_amount: Decimal = Decimal("0")
    gross_pnl: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    r_multiple: Decimal | None = None


class EquityPoint(FrozenContract):
    at: AwareDatetime
    balance: Decimal
    equity: Decimal
    drawdown: Decimal
    drawdown_pct: Decimal


class SimulationResult(FrozenContract):
    simulation_version: str = SIMULATION_VERSION
    risk_replay_fingerprint: Sha256
    simulation_fingerprint: Sha256
    initial_balance: Decimal
    final_balance: Decimal
    trades: tuple[SimulatedTrade, ...]
    equity_points: tuple[EquityPoint, ...]
    max_concurrent_positions: int = Field(default=1, ge=0, le=1)


class BacktestMetrics(FrozenContract):
    metrics_version: str = METRICS_VERSION
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: Decimal | None
    loss_rate: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal
    profit_factor: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    average_r: Decimal | None
    expectancy: Decimal | None
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    return_pct: Decimal
    consecutive_wins: int
    consecutive_losses: int
    long_trades: int
    short_trades: int
    by_strategy: dict[str, int]
