"""Canonical UTC market contracts. Prices serialize as exact decimal strings."""

import datetime as dt
import enum
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Price = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=5, allow_inf_nan=False)]
Amount = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=5, allow_inf_nan=False)]
SymbolName = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]{2,19}$")]
Source = Annotated[str, StringConstraints(pattern=r"^(simulated|mt5_(demo|live)_[a-z0-9_]{1,16})$")]


class Timeframe(str, enum.Enum):
    M1 = "M1"
    M3 = "M3"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"


SECONDS = dict(zip(Timeframe, (60, 180, 300, 900, 1800, 3600, 14400, 86400, 604800), strict=True))


def bucket(timestamp: dt.datetime, timeframe: Timeframe) -> dt.datetime:
    if timestamp.tzinfo is None:
        raise ValueError("Timezone required")
    seconds = int(timestamp.timestamp())
    offset = 345600 if timeframe == Timeframe.W1 else 0  # Monday 1970-01-05 UTC
    start = (seconds - offset) // SECONDS[timeframe] * SECONDS[timeframe] + offset
    return dt.datetime.fromtimestamp(start, dt.UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "timestamp", "open_time", "last_quote", "server_time", "next_cursor", "last_candle", check_fields=False
    )
    @classmethod
    def canonical_utc(cls, value):
        return value.astimezone(dt.UTC) if value is not None else None


class Tick(Contract):
    symbol: SymbolName
    timestamp: AwareDatetime
    bid: Price
    ask: Price
    volume: Amount
    source: Source

    @model_validator(mode="after")
    def valid_spread(self):
        if self.ask < self.bid:
            raise ValueError("Ask below bid")
        return self


class Quote(Tick):
    mode: Literal["SIMULATED", "DEMO", "LIVE"] = "SIMULATED"
    spread: Amount
    status: Literal["CONNECTED", "STALE", "DISCONNECTED", "ERROR"]

    @model_validator(mode="after")
    def exact_spread(self):
        expected = "SIMULATED" if self.source == "simulated" else self.source.split("_")[1].upper()
        if self.mode != expected:
            raise ValueError("Quote source mode mismatch")
        if self.spread != self.ask - self.bid:
            raise ValueError("Incorrect spread")
        return self


class Candle(Contract):
    symbol: SymbolName
    timeframe: Timeframe
    open_time: AwareDatetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Amount
    bid_close: Price
    ask_close: Price | None
    source: Source
    is_closed: bool

    @model_validator(mode="after")
    def valid_ohlc(self):
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("Invalid OHLC")
        if (self.ask_close is not None and self.ask_close < self.bid_close) or self.open_time != bucket(
            self.open_time, self.timeframe
        ):
            raise ValueError("Invalid candle boundary or spread")
        return self


class MarketDataStatus(Contract):
    source: Source
    mode: Literal["SIMULATED", "DEMO", "LIVE", "UNCONFIRMED"]
    status: Literal["CONNECTING", "CONNECTED", "STALE", "DISCONNECTED", "ERROR"]
    last_quote: AwareDatetime | None
    server_time: AwareDatetime
    stale_after_seconds: int
    detail: str
    subscriptions: int
    history_counts: dict[Timeframe, int] = Field(default_factory=dict)
    history_complete: bool = False
    digits: int | None = Field(default=None, ge=0, le=5)
    tick_size: Price | None = None
    provider_symbol: str | None = None
    market_state: Literal["OPEN", "CLOSED", "UNKNOWN"] = "UNKNOWN"
    last_candle: AwareDatetime | None = None
    volume_kind: Literal["synthetic", "tick_count"] = "synthetic"

    @model_validator(mode="after")
    def valid_source_mode(self):
        if self.source == "simulated" and self.mode != "SIMULATED":
            raise ValueError("Simulated source mode mismatch")
        if self.source != "simulated" and self.mode not in ("UNCONFIRMED", self.source.split("_")[1].upper()):
            raise ValueError("Real source mode mismatch")
        return self


class CandlePage(Contract):
    candles: list[Candle]
    next_cursor: AwareDatetime | None


class SymbolInput(Contract):
    name: SymbolName
    asset_class: str = Field(default="METAL", min_length=1, max_length=30)
    digits: int = Field(default=2, ge=0, le=5)
    contract_size: Price = Decimal("100")
    tick_value: Price = Decimal("1")
    default_spread: Amount = Decimal("0.30")
    session_hours: dict[str, list[str]] = Field(default_factory=dict)


class SymbolInfo(SymbolInput):
    is_active: bool
    source_available: bool


class WsCommand(Contract):
    type: Literal["subscribe", "unsubscribe", "ping"]
    symbol: SymbolName = "XAUUSD"
    timeframe: Timeframe = Timeframe.M5


class WsAuth(Contract):
    type: Literal["auth"]
    token: str = Field(min_length=1, max_length=8192)


class MarketMessage(Contract):
    type: Literal["snapshot", "update", "status", "heartbeat", "error"]
    symbol: SymbolName
    timeframe: Timeframe
    sequence: int = Field(ge=0)
    quote: Quote | None
    candles: list[Candle]
    status: MarketDataStatus
    error: str | None
