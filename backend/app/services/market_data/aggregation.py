"""M1 replacement-safe higher-timeframe aggregation with bounded current windows."""

import datetime as dt
from decimal import Decimal

from app.services.market_data.domain import Candle, Tick, Timeframe, bucket


def merge(left: Candle | None, right: Candle, timeframe: Timeframe) -> Candle:
    return Candle(
        symbol=right.symbol,
        timeframe=timeframe,
        open_time=bucket(right.open_time, timeframe),
        open=left.open if left else right.open,
        high=max(left.high, right.high) if left else right.high,
        low=min(left.low, right.low) if left else right.low,
        close=right.close,
        volume=(left.volume if left else Decimal(0)) + right.volume,
        bid_close=right.bid_close,
        ask_close=right.ask_close,
        source=right.source,
        is_closed=False,
    )


class CandleEngine:
    def __init__(self):
        self.base: Candle | None = None
        self.prefix: dict[Timeframe, Candle] = {}
        self.current: dict[Timeframe, Candle] = {}
        self.last_tick: dt.datetime | None = None

    def seed(self, bases: list[Candle]) -> None:
        for base in bases:
            self._replace_base(base)

    def _replace_base(self, base: Candle) -> list[Candle]:
        closed = []
        previous = self.base
        for timeframe in Timeframe:
            start = bucket(base.open_time, timeframe)
            current = self.current.get(timeframe)
            if current and current.open_time != start:
                closed.append(current.model_copy(update={"is_closed": True}))
                self.prefix.pop(timeframe, None)
            elif previous and previous.open_time != base.open_time and timeframe != Timeframe.M1:
                self.prefix[timeframe] = merge(self.prefix.get(timeframe), previous, timeframe)
            self.current[timeframe] = merge(self.prefix.get(timeframe), base, timeframe)
        self.base = base
        return closed

    def ingest(self, tick: Tick) -> list[Candle]:
        if self.last_tick and tick.timestamp <= self.last_tick:
            raise ValueError("Duplicate or out-of-order tick")
        self.last_tick = tick.timestamp
        start = bucket(tick.timestamp, Timeframe.M1)
        old = self.base if self.base and self.base.open_time == start else None
        base = Candle(
            symbol=tick.symbol,
            timeframe=Timeframe.M1,
            open_time=start,
            open=old.open if old else tick.bid,
            high=max(old.high, tick.bid) if old else tick.bid,
            low=min(old.low, tick.bid) if old else tick.bid,
            close=tick.bid,
            volume=(old.volume if old else Decimal(0)) + tick.volume,
            bid_close=tick.bid,
            ask_close=tick.ask,
            source=tick.source,
            is_closed=False,
        )
        return self._replace_base(base) + list(self.current.values())
