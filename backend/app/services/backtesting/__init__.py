"""Pure Batch D1 backtesting contracts; no replay or execution behavior."""

from app.services.backtesting.domain import BACKTEST_CONTRACT_VERSION, BACKTEST_FINGERPRINT_VERSION

__all__ = ["BACKTEST_CONTRACT_VERSION", "BACKTEST_FINGERPRINT_VERSION"]
