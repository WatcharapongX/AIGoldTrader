"""D1/D2A version exports; stateless D2C Risk replay requires an explicit module import."""

from app.services.backtesting.domain import (
    BACKTEST_CONTRACT_VERSION,
    BACKTEST_FINGERPRINT_VERSION,
    REPLAY_ENGINE_VERSION,
)

__all__ = ["BACKTEST_CONTRACT_VERSION", "BACKTEST_FINGERPRINT_VERSION", "REPLAY_ENGINE_VERSION"]
