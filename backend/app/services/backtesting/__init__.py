"""Pure D1 contracts and D2A causal replay; no risk or execution behavior."""

from app.services.backtesting.domain import (
    BACKTEST_CONTRACT_VERSION,
    BACKTEST_FINGERPRINT_VERSION,
    REPLAY_ENGINE_VERSION,
)

__all__ = ["BACKTEST_CONTRACT_VERSION", "BACKTEST_FINGERPRINT_VERSION", "REPLAY_ENGINE_VERSION"]
