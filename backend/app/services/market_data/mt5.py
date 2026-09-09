"""Official MetaTrader5 IPC, market data only. No execution API is exposed.

Quote snapshots are sampled once per configured interval. Authoritative broker
rates (not sampled quotes) supply OHLC/tick volume, so missed quote changes cannot
corrupt candle extrema. M3 is folded from M1 using canonical UTC buckets.
"""
import asyncio
import datetime as dt
import importlib
import threading
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.market_data.domain import SECONDS, Candle, Tick, Timeframe, bucket
from app.services.market_data.provider import MarketDataProvider

# Provider constants stay in this adapter, never in domain/service/frontend.
RATE_TIMEFRAMES = {tf: "TIMEFRAME_" + tf.value for tf in Timeframe if tf != Timeframe.M3}
READ_METHODS = frozenset({
    "initialize", "shutdown", "terminal_info", "account_info", "symbol_select",
    "symbol_info", "symbol_info_tick", "copy_rates_from",
})


class MT5Unavailable(RuntimeError):
    """Only stable non-sensitive reason codes may cross this boundary."""


class ReadOnlyMT5:
    def __init__(self, sdk):
        self._sdk = sdk
        self._lock = threading.RLock()

    def call(self, name, *args, **kwargs):
        if name not in READ_METHODS:
            raise MT5Unavailable("MT5_READ_ONLY_GUARD")
        with self._lock:
            try:
                return getattr(self._sdk, name)(*args, **kwargs)
            except Exception:
                # Do not call last_error or expose SDK exception/account/server text.
                raise MT5Unavailable("MT5_IPC_UNAVAILABLE") from None

    def timeframe(self, timeframe: Timeframe):
        if timeframe not in RATE_TIMEFRAMES:
            raise MT5Unavailable("MT5_TIMEFRAME_UNSUPPORTED")
        return getattr(self._sdk, RATE_TIMEFRAMES[timeframe])


def aggregate_rates(bases: list[Candle], timeframe: Timeframe, now: dt.datetime) -> list[Candle]:
    groups: dict[dt.datetime, Candle] = {}
    for base in bases:
        key = bucket(base.open_time, timeframe)
        previous = groups.get(key)
        if previous is None:
            groups[key] = base.model_copy(update={
                "timeframe": timeframe, "open_time": key,
                "is_closed": key + dt.timedelta(seconds=SECONDS[timeframe]) <= now,
            })
        else:
            if base.source != previous.source or base.symbol != previous.symbol:
                raise MT5Unavailable("MT5_MIXED_SOURCE")
            groups[key] = previous.model_copy(update={
                "high": max(previous.high, base.high), "low": min(previous.low, base.low),
                "close": base.close, "bid_close": base.bid_close, "ask_close": base.ask_close,
                "volume": previous.volume + base.volume,
            })
    # The oldest requested bucket may have a truncated prefix; never publish it.
    if bases and bases[0].open_time != bucket(bases[0].open_time, timeframe):
        groups.pop(bucket(bases[0].open_time, timeframe), None)
    return list(groups.values())


class MT5MarketDataProvider(MarketDataProvider):
    authoritative_candles = True
    mode = "UNCONFIRMED"
    description = "MT5 connection unverified"

    def __init__(self, settings, sdk=None):
        self.settings = settings
        self.source = "mt5_" + settings.mt5_account_mode.lower() + "_" + (settings.mt5_feed_id or "unconfigured")
        self.provider_symbol = settings.mt5_symbol_xauusd or None
        self._gateway = ReadOnlyMT5(sdk) if sdk is not None else None
        self.connected = False
        try:
            self._timezone = ZoneInfo(settings.mt5_server_timezone)
        except ZoneInfoNotFoundError:
            raise MT5Unavailable("MT5_TIMEZONE_UNAVAILABLE") from None
        self.last_quote: dt.datetime | None = None

    async def connect(self):
        await asyncio.to_thread(self._connect)

    def _connect(self):
        s = self.settings
        self.connected = False
        self.mode = "UNCONFIRMED"
        if s.trading_mode != "PAPER" or s.live_auto_trading:
            raise MT5Unavailable("MT5_REQUIRES_PAPER_EXECUTION_DISABLED")
        if not all((s.mt5_terminal_path, s.mt5_symbol_xauusd, s.mt5_feed_id, s.mt5_expected_server)):
            raise MT5Unavailable("MT5_CONFIGURATION_REQUIRED")
        if not Path(s.mt5_terminal_path).is_file():
            raise MT5Unavailable("MT5_TERMINAL_REQUIRED")
        if self._gateway is None:
            try:
                self._gateway = ReadOnlyMT5(importlib.import_module("MetaTrader5"))
            except ImportError:
                raise MT5Unavailable("MT5_PACKAGE_REQUIRED") from None
        g = self._gateway
        if not g.call("initialize", s.mt5_terminal_path, timeout=s.mt5_timeout_ms):
            raise MT5Unavailable("MT5_SESSION_REQUIRED")
        terminal, account = g.call("terminal_info"), g.call("account_info")
        if not terminal or not terminal.connected or not account:
            raise MT5Unavailable("MT5_SESSION_REQUIRED")
        # Official ENUM_ACCOUNT_TRADE_MODE: demo=0, contest=1, real=2.
        expected = 0 if s.mt5_account_mode == "DEMO" else 2
        if account.trade_mode != expected or account.server != s.mt5_expected_server:
            raise MT5Unavailable("MT5_ACCOUNT_MISMATCH")
        if s.mt5_expected_login is not None and account.login != s.mt5_expected_login:
            raise MT5Unavailable("MT5_ACCOUNT_MISMATCH")
        if not g.call("symbol_select", self.provider_symbol, True):
            raise MT5Unavailable("MT5_SYMBOL_UNAVAILABLE")
        info = g.call("symbol_info", self.provider_symbol)
        if not info or not 0 <= info.digits <= 5:
            raise MT5Unavailable("MT5_PRECISION_UNSUPPORTED")
        self.digits = int(info.digits)
        self.tick_size = Decimal(str(info.trade_tick_size))
        point = Decimal(str(info.point))
        if (not self.tick_size.is_finite() or self.tick_size <= 0
                or point != Decimal(1).scaleb(-self.digits)
                or self.tick_size % point != 0):
            raise MT5Unavailable("MT5_PRECISION_UNSUPPORTED")
        self.mode = s.mt5_account_mode
        self.description = "Real market data / " + self.mode + " connection; PAPER execution disabled"
        self.connected = True

    async def disconnect(self):
        self.connected = False
        if self._gateway is not None:
            await asyncio.to_thread(self._gateway.call, "shutdown")

    def health(self) -> bool:
        return self.connected

    def _session(self):
        if not self.connected or self._gateway is None:
            raise MT5Unavailable("MT5_SESSION_REQUIRED")
        # Detect terminal restart, account switching or mode changes before each batch.
        terminal = self._gateway.call("terminal_info")
        account = self._gateway.call("account_info")
        expected = 0 if self.settings.mt5_account_mode == "DEMO" else 2
        if (not terminal or not terminal.connected or not account or account.trade_mode != expected
                or account.server != self.settings.mt5_expected_server
                or (self.settings.mt5_expected_login is not None
                    and account.login != self.settings.mt5_expected_login)):
            self.connected = False
            raise MT5Unavailable("MT5_SESSION_CHANGED")
        return self._gateway

    def _price(self, value) -> Decimal:
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0 or self.digits is None:
            raise MT5Unavailable("MT5_INVALID_PRICE")
        normalized = result.quantize(Decimal(1).scaleb(-self.digits))
        if abs(normalized - result) > Decimal("0.00000001"):
            raise MT5Unavailable("MT5_INVALID_PRECISION")
        return normalized

    def _utc(self, raw_seconds: float) -> dt.datetime:
        # Some broker terminals encode server wall time as Unix seconds.
        # Explicit operator policy only; never estimate timezone from a single stale quote.
        wall = dt.datetime.fromtimestamp(raw_seconds, dt.UTC).replace(tzinfo=None)
        local = wall.replace(tzinfo=self._timezone)
        alternate = wall.replace(tzinfo=self._timezone, fold=1)
        if local.utcoffset() != alternate.utcoffset():
            raise MT5Unavailable("MT5_AMBIGUOUS_OR_NONEXISTENT_TIME")
        return local.astimezone(dt.UTC)

    def get_quote(self, symbol: str) -> Tick | None:
        if symbol != "XAUUSD":
            raise MT5Unavailable("MT5_SYMBOL_UNSUPPORTED")
        value = self._session().call("symbol_info_tick", self.provider_symbol)
        if value is None:
            return None
        timestamp = self._utc(int(value.time_msc) / 1000)
        result = Tick(symbol=symbol, timestamp=timestamp, bid=self._price(value.bid),
                      ask=self._price(value.ask), volume=Decimal(0), source=self.source)
        self.last_quote = result.timestamp
        return result

    async def subscribe_ticks(self, symbol):
        last = None
        while self.connected:
            value = await asyncio.to_thread(self.get_quote, symbol)
            if value is not None and (last is None or value.timestamp > last):
                last = value.timestamp
                yield value
            await asyncio.sleep(self.settings.mt5_poll_seconds)

    def get_historical_candles(self, symbol, timeframe, now, limit=300):
        if symbol != "XAUUSD" or not 1 <= limit <= 10080 or now.tzinfo is None:
            raise MT5Unavailable("MT5_INVALID_HISTORY_REQUEST")
        g = self._session()
        native = (Timeframe.M1 if timeframe == Timeframe.M3 else
                  Timeframe.H1 if timeframe in (Timeframe.H4, Timeframe.D1, Timeframe.W1) else timeframe)
        ratio = SECONDS[timeframe] // SECONDS[native]
        count = min(100000, limit * ratio + ratio if native != timeframe else limit)
        anchor = now.astimezone(self._timezone).replace(tzinfo=dt.UTC)
        rows = g.call("copy_rates_from", self.provider_symbol, g.timeframe(native), anchor, count)
        if rows is None:
            raise MT5Unavailable("MT5_HISTORY_UNAVAILABLE")
        candles: list[Candle] = []
        for row in rows:
            start = self._utc(int(row["time"]))
            if start > now or (candles and start <= candles[-1].open_time):
                raise MT5Unavailable("MT5_INVALID_HISTORY_ORDER")
            # Reject broker bars with incompatible UTC boundaries; never relabel their OHLC.
            if start != bucket(start, native):
                raise MT5Unavailable("MT5_NONCANONICAL_BAR_BOUNDARY")
            closing = self._price(row["close"])
            candles.append(Candle(
                symbol=symbol, timeframe=native, open_time=start,
                open=self._price(row["open"]), high=self._price(row["high"]),
                low=self._price(row["low"]), close=closing, volume=Decimal(str(row["tick_volume"])),
                bid_close=closing, ask_close=None, source=self.source,
                is_closed=start + dt.timedelta(seconds=SECONDS[native]) <= now,
            ))
        if native != timeframe:
            candles = aggregate_rates(candles, timeframe, now)
        return candles[-limit:]

    async def candle_updates(self, now):
        def snapshot():
            values = []
            for timeframe in Timeframe:
                # Last closed plus forming bar: replace authoritative OHLC, never add sampled volume.
                values.extend(self.get_historical_candles("XAUUSD", timeframe, now, 2))
            return values
        return await asyncio.to_thread(snapshot)
