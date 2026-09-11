"""Replay feed with periodic synthetic M1 history; no external credentials or execution."""

import asyncio
import datetime as dt
import math
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from decimal import Decimal
from functools import lru_cache

from app.services.market_data.domain import SECONDS, Candle, Tick, Timeframe, bucket


def price(second: int) -> Decimal:
    second %= 86400
    cents = 235000 + round(
        math.sin(second * math.tau / 600) * 180
        + math.sin(second * math.tau / 7200) * 950
        + math.sin(second * math.tau / 86400) * 2300
    )
    return Decimal(cents) / 100


@lru_cache(maxsize=1440)
def minute_values(minute: int) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    values = [price(minute * 60 + second) for second in range(60)]
    return values[0], max(values), min(values), values[-1]


def synthetic_candle(symbol: str, timeframe: Timeframe, start: dt.datetime, end: dt.datetime) -> Candle:
    """Fold canonical M1 blocks; exploit the replay's daily period for long history.
    end is exclusive: never includes a future second or the first live tick.
    """
    first, stop = int(start.timestamp()), int(end.timestamp())
    if stop <= first:
        raise ValueError("Empty candle interval")
    points: list[Decimal] = []
    full_start = (first + 59) // 60
    full_stop = stop // 60
    for second in range(first, min(stop, full_start * 60)):
        points.append(price(second))
    # Every complete synthetic day has exactly the same M1 extrema.
    for minute in range(full_start, min(full_stop, full_start + 1440)):
        _, high, low, _ = minute_values(minute % 1440)
        points.extend((high, low))
    for second in range(max(first, full_stop * 60), stop):
        points.append(price(second))
    opening, closing = price(first), price(stop - 1)
    points.extend((opening, closing))
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=start,
        open=opening,
        high=max(points),
        low=min(points),
        close=closing,
        volume=Decimal(stop - first),
        bid_close=closing,
        ask_close=closing + Decimal("0.30"),
        source="simulated",
        is_closed=stop >= first + SECONDS[timeframe],
    )


class MarketDataProvider(ABC):
    source = "simulated"
    mode = "SIMULATED"
    digits: int | None = None
    tick_size: Decimal | None = None
    provider_symbol: str | None = None
    authoritative_candles = False
    description = "Deterministic replay; not live market prices"

    @property
    def broker_server(self) -> str | None:
        return None

    async def candle_updates(self, now: dt.datetime) -> list[Candle]:
        return []

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def subscribe_ticks(self, symbol: str) -> AsyncIterator[Tick]: ...

    @abstractmethod
    def get_historical_candles(
        self, symbol: str, timeframe: Timeframe, now: dt.datetime, limit: int = 300
    ) -> list[Candle]: ...

    @abstractmethod
    def health(self) -> bool: ...

    def get_symbol_spec(self, symbol: str = "XAUUSD"):
        from app.services.risk.domain import default_gold_spec

        return default_gold_spec(source=self.source)


class ReplayProvider(MarketDataProvider):
    def __init__(self):
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    def health(self) -> bool:
        return self.connected

    def get_symbol_spec(self, symbol: str = "XAUUSD"):
        from app.services.risk.domain import default_gold_spec

        return default_gold_spec(source="simulated")

    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[Tick]:
        if symbol != "XAUUSD":
            raise ValueError("Replay source only supplies XAUUSD")
        last = -1
        while self.connected:
            now = int(dt.datetime.now(dt.UTC).timestamp())
            if now > last:
                last = now
                bid = price(now)
                yield Tick(
                    symbol=symbol,
                    timestamp=dt.datetime.fromtimestamp(now, dt.UTC),
                    bid=bid,
                    ask=bid + Decimal("0.30"),
                    volume=Decimal(1),
                    source="simulated",
                )
            await asyncio.sleep(0.2)

    def get_historical_candles(
        self, symbol: str, timeframe: Timeframe, now: dt.datetime, limit: int = 300
    ) -> list[Candle]:
        if symbol != "XAUUSD":
            raise ValueError("Replay source only supplies XAUUSD")
        start = bucket(now, timeframe)
        seconds = SECONDS[timeframe]
        candles = []
        for index in range(limit, -1, -1):
            begin = start - dt.timedelta(seconds=seconds * index)
            end = min(begin + dt.timedelta(seconds=seconds), now.replace(microsecond=0))
            if end > begin:
                candles.append(synthetic_candle(symbol, timeframe, begin, end))
        return candles[-limit:]


PROVIDERS: dict[str, type[MarketDataProvider]] = {"simulated": ReplayProvider}


def create_provider(name: str, settings=None) -> MarketDataProvider:
    if name == "mt5":
        from app.core.config import Settings
        from app.services.market_data.mt5 import MT5MarketDataProvider

        return MT5MarketDataProvider(settings or Settings())

    if name not in PROVIDERS:
        raise ValueError("Unsupported MARKET_DATA_PROVIDER")
    return PROVIDERS[name]()
