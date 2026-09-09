"""Explicit SMA-seeded EMA/MACD and slow stochastic; no synthetic warmup values."""

from decimal import Decimal

from app.services.market_data.domain import Candle
from app.services.strategy.domain import Indicator, StrategyConfig

D = Decimal


def ema(values: list[Decimal], period: int) -> list[Decimal | None]:
    result: list[Decimal | None] = []
    current: Decimal | None = None
    alpha = D(2) / D(period + 1)
    for index, value in enumerate(values):
        if index + 1 < period:
            result.append(None)
            continue
        current = sum(values[:period], D(0)) / period if current is None else current + alpha * (value - current)
        result.append(current)
    return result


def calculate(candles: list[Candle], config: StrategyConfig) -> tuple[Indicator, ...]:
    close = [c.close for c in candles]
    fast, slow = ema(close, config.macd_fast), ema(close, config.macd_slow)
    macd = [a - b for a, b in zip(fast, slow, strict=True) if a is not None and b is not None]
    signals = ema(macd, config.macd_signal)
    signal = signals[-1] if signals else None
    kvals: list[Decimal | None] = []
    for index in range(config.stochastic_period - 1, len(candles)):
        window = candles[index - config.stochastic_period + 1 : index + 1]
        high, low = max(c.high for c in window), min(c.low for c in window)
        kvals.append(D(100) * (window[-1].close - low) / (high - low) if high > low else None)
    recent = kvals[-config.stochastic_smooth :]
    smooth = (
        sum((v for v in recent if v is not None), D(0)) / config.stochastic_smooth
        if len(recent) == config.stochastic_smooth and all(v is not None for v in recent)
        else None
    )
    pairs = (
        ("MACD", macd[-1] if macd else None, config.macd_slow),
        ("MACD_SIGNAL", signal, config.macd_slow + config.macd_signal - 1),
        (
            "MACD_HISTOGRAM",
            macd[-1] - signal if macd and signal is not None else None,
            config.macd_slow + config.macd_signal - 1,
        ),
        ("STOCHASTIC_K", kvals[-1] if kvals else None, config.stochastic_period),
        ("STOCHASTIC_D", smooth, config.stochastic_period + config.stochastic_smooth - 1),
    )
    return tuple(
        Indicator(
            name=name,
            value=value,
            minimum_bars=minimum,
            status="READY" if value is not None else "WARMUP" if len(candles) < minimum else "UNAVAILABLE",
        )
        for name, value, minimum in pairs
    )
