"""Decimal streaming indicators. ATR/RSI use p changes; ADX uses p subsequent DX values."""

from collections import deque
from decimal import Decimal

from app.services.analysis.domain import AnalysisConfig, IndicatorValue
from app.services.market_data.domain import Candle


def rounded(value):
    return None if value is None else value.quantize(Decimal(".00000001"))


class Indicators:
    def __init__(self, config: AnalysisConfig):
        self.p, self.average = config.atr_period, config.average_period
        self.previous: Candle | None = None
        self.n = 0
        self.trs: list[Decimal] = []
        self.gains: list[Decimal] = []
        self.losses: list[Decimal] = []
        self.plus: list[Decimal] = []
        self.minus: list[Decimal] = []
        self.atr: Decimal | None = None
        self.gain: Decimal | None = None
        self.loss: Decimal | None = None
        self.pdm: Decimal | None = None
        self.mdm: Decimal | None = None
        self.adx: Decimal | None = None
        self.ema: Decimal | None = None
        self.dx: list[Decimal] = []
        self.closes: deque = deque(maxlen=self.average)
        self.volumes: deque = deque(maxlen=self.average)

    def feed(self, candle: Candle):
        self.n += 1
        self.closes.append(candle.close)
        self.volumes.append(candle.volume)
        if len(self.closes) == self.average:
            self.ema = (
                sum(self.closes) / self.average
                if self.ema is None
                else self.ema + (candle.close - self.ema) * Decimal(2) / (self.average + 1)
            )
        if self.previous is not None:
            old = self.previous
            delta = candle.close - old.close
            up, down = candle.high - old.high, old.low - candle.low
            values = [
                max(candle.high - candle.low, abs(candle.high - old.close), abs(candle.low - old.close)),
                max(delta, Decimal(0)),
                max(-delta, Decimal(0)),
                up if up > down and up > 0 else Decimal(0),
                down if down > up and down > 0 else Decimal(0),
            ]
            for name, seed, value in zip(
                ("atr", "gain", "loss", "pdm", "mdm"),
                (self.trs, self.gains, self.losses, self.plus, self.minus),
                values,
                strict=True,
            ):
                previous = getattr(self, name)
                if previous is None:
                    seed.append(value)
                    if len(seed) == self.p:
                        setattr(self, name, sum(seed) / self.p)
                        seed.clear()
                else:
                    setattr(self, name, (previous * (self.p - 1) + value) / self.p)
            if self.atr is not None:
                assert self.pdm is not None and self.mdm is not None
                denominator = self.pdm + self.mdm
                dx = Decimal(0) if denominator == 0 else 100 * abs(self.pdm - self.mdm) / denominator
                if self.adx is None:
                    self.dx.append(dx)
                    if len(self.dx) == self.p:
                        self.adx = sum(self.dx, Decimal(0)) / self.p
                        self.dx.clear()
                else:
                    self.adx = (self.adx * (self.p - 1) + dx) / self.p
        self.previous = candle

    def values(self):
        def item(value, minimum):
            return IndicatorValue(
                value=rounded(value),
                minimum_bars_required=minimum,
                status="READY" if value is not None else "INSUFFICIENT_DATA",
            )

        sma = sum(self.closes) / self.average if len(self.closes) == self.average else None
        sd = None if sma is None else (sum((v - sma) ** 2 for v in self.closes) / self.average).sqrt()
        rsi = None
        if self.gain is not None:
            assert self.loss is not None
            rsi = (
                Decimal(50)
                if self.gain == self.loss == 0
                else Decimal(100)
                if self.loss == 0
                else 100 - 100 / (1 + self.gain / self.loss)
            )
        return {
            "ATR": item(self.atr, self.p + 1),
            "RSI": item(rsi, self.p + 1),
            "ADX": item(self.adx, self.p * 2),
            "EMA": item(self.ema, self.average),
            "SMA": item(sma, self.average),
            "BOLLINGER_UPPER": item(None if sd is None else sma + 2 * sd, self.average),
            "BOLLINGER_LOWER": item(None if sd is None else sma - 2 * sd, self.average),
            "VOLUME_AVERAGE": item(None if sma is None else sum(self.volumes) / self.average, self.average),
        }
