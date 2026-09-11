"""One lazy, bounded DEV feed per application. Publication follows successful DB commit."""

import asyncio
import datetime as dt
import logging
from contextlib import suppress
from contextvars import Context

from sqlalchemy import select

from app.core.logging import safe_exception
from app.db.seed import XAUUSD_DEFAULTS
from app.models import EventCategory, EventSeverity, Symbol, SystemEvent
from app.services.market_data.aggregation import CandleEngine
from app.services.market_data.domain import MarketDataStatus, Quote, Tick, Timeframe, bucket
from app.services.market_data.provider import create_provider
from app.services.market_data.repository import prune, save_tick, upsert_candles

logger = logging.getLogger(__name__)


class LocalMarketBus:
    """Replaceable single-instance pub/sub; slow consumers must reconnect for a fresh snapshot."""

    def __init__(self):
        self.queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        if len(self.queues) >= 128:
            raise ValueError("Market connection capacity reached")
        queue: asyncio.Queue = asyncio.Queue(maxsize=16)
        self.queues.add(queue)
        return queue

    def unsubscribe(self, queue) -> None:
        self.queues.discard(queue)

    def publish(self, value) -> None:
        for queue in tuple(self.queues):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self.queues.discard(queue)
            else:
                queue.put_nowait(value)


class MarketService:
    def __init__(self, factory, settings):
        self.factory = factory
        self.settings = settings
        self.provider = create_provider(settings.market_data_provider, settings)
        self.engine = CandleEngine()
        self.bus = LocalMarketBus()
        self.quote: Quote | None = None
        self.sequence = 0
        self.state = "CONNECTING"
        self.detail = "Starting configured market feed"
        self.last_candle = None
        self.history_counts: dict[Timeframe, int] = {}
        self.symbol_id = None
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.event_times: dict[str, dt.datetime] = {}

    def status(self, now=None) -> MarketDataStatus:
        now = now or dt.datetime.now(dt.UTC)
        state = self.state
        if (
            state == "CONNECTED"
            and self.quote
            and (now - self.quote.timestamp).total_seconds() > self.settings.market_stale_seconds
        ):
            state = "STALE"
        return MarketDataStatus(
            source=self.provider.source,
            mode=self.provider.mode,
            status=state,
            digits=self.provider.digits,
            tick_size=self.provider.tick_size,
            provider_symbol=self.provider.provider_symbol,
            last_candle=self.last_candle,
            history_counts=self.history_counts,
            history_complete=len(self.history_counts) == 9 and min(self.history_counts.values()) >= 300,
            market_state="OPEN" if state == "CONNECTED" else "UNKNOWN",
            volume_kind="tick_count" if self.provider.authoritative_candles else "synthetic",
            last_quote=self.quote.timestamp if self.quote else getattr(self.provider, "last_quote", None),
            server_time=now,
            stale_after_seconds=self.settings.market_stale_seconds,
            detail=self.detail if state != "STALE" else "No fresh quote received",
            subscriptions=len(self.bus.queues),
        )

    async def start(self) -> None:
        async with self.lock:
            if not self.task or self.task.done():
                self.task = asyncio.create_task(self.run(), name="market-data", context=Context())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        await self.provider.disconnect()
        self.state = "DISCONNECTED"

    async def event(self, code: str) -> None:
        now = dt.datetime.now(dt.UTC)
        if code in self.event_times and (now - self.event_times[code]).total_seconds() < 60:
            return
        self.event_times[code] = now
        async with self.factory() as session:
            session.add(
                SystemEvent(
                    category=EventCategory.DATA,
                    severity=EventSeverity.WARNING,
                    code=code,
                    message=code.replace("_", " "),
                    payload={"source": self.provider.source},
                )
            )
            await session.commit()
        logger.warning("market_data_event", extra={"event_code": code})

    async def initialize(self) -> None:
        self.state = "CONNECTING"
        await self.provider.connect()
        self.quote = None
        now = dt.datetime.now(dt.UTC).replace(microsecond=0)
        async with self.factory() as session:
            symbol = await session.scalar(select(Symbol).where(Symbol.name == "XAUUSD"))
            if symbol is None:
                symbol = Symbol(**XAUUSD_DEFAULTS)
                session.add(symbol)
                await session.flush()
            self.symbol_id = symbol.id
            if not symbol.is_active:
                raise ValueError("Symbol is inactive")
            for timeframe in Timeframe:
                history = await asyncio.to_thread(self.provider.get_historical_candles, "XAUUSD", timeframe, now)
                self.history_counts[timeframe] = len(history)
                if not history or (not self.provider.authoritative_candles and len(history) < 300):
                    raise ValueError("Insufficient provider history; at least 300 bars per timeframe required")
                await upsert_candles(session, symbol.id, history)
            if not self.provider.authoritative_candles:
                await prune(session, symbol.id, now)
            await session.commit()
        if self.provider.authoritative_candles:
            self.state = "STALE"
            self.detail = "Waiting for a fresh provider quote; market session unknown"
            return
        self.engine = CandleEngine()
        # At most one current UTC week of M1 contributions: finite and consistent across timeframes.
        count = int((now - bucket(now, Timeframe.W1)).total_seconds() // 60) + 1
        bases = self.provider.get_historical_candles("XAUUSD", Timeframe.M1, now, count)
        self.engine.seed(bases)
        self.state = "CONNECTING"

    async def ingest(self, tick: Tick, now=None) -> bool:
        now = now or dt.datetime.now(dt.UTC)
        age = (now - tick.timestamp).total_seconds()
        code = None
        if tick.source != self.provider.source:
            code = "MARKET_SOURCE_MISMATCH"
        elif tick.symbol != "XAUUSD":
            code = "MARKET_UNSUPPORTED_SYMBOL"
        elif age > self.settings.market_stale_seconds or age < -(
            self.settings.mt5_future_tolerance_seconds if self.provider.authoritative_candles else 2
        ):
            code = "MARKET_INVALID_TIME"
        elif self.quote and tick.timestamp <= self.quote.timestamp:
            code = "MARKET_DUPLICATE_OR_OUT_OF_ORDER"
        elif self.quote and abs(tick.bid / self.quote.bid - 1) > self.settings.market_max_jump_ratio:
            code = "MARKET_ABNORMAL_PRICE"
        elif tick.ask - tick.bid > self.settings.market_max_spread:
            code = "MARKET_ABNORMAL_SPREAD"
        if code:
            if code == "MARKET_INVALID_TIME" and age > self.settings.market_stale_seconds:
                self.state = "STALE"
            await self.event(code)
            return False
        if (
            self.provider.authoritative_candles
            and self.quote
            and (tick.timestamp - self.quote.timestamp).total_seconds()
            > max(self.settings.market_stale_seconds, self.settings.mt5_poll_seconds * 2)
        ):
            raise ValueError("Provider gap requires historical resnapshot")
        candles = (
            await self.provider.candle_updates(now) if self.provider.authoritative_candles else self.engine.ingest(tick)
        )
        if any(c.source != self.provider.source or c.symbol != tick.symbol for c in candles):
            raise ValueError("Provider candle source mismatch")
        async with self.factory() as session:
            symbol = await session.get(Symbol, self.symbol_id)
            if symbol is None or not symbol.is_active:
                raise ValueError("Symbol inactive")
            if not self.provider.authoritative_candles or self.settings.market_archive_real_ticks:
                await save_tick(session, self.symbol_id, tick)
            await upsert_candles(session, self.symbol_id, candles)
            if self.sequence % 60 == 0 and not self.provider.authoritative_candles:
                await prune(session, self.symbol_id, now)
            await session.commit()
        self.quote = Quote(**tick.model_dump(), spread=tick.ask - tick.bid, status="CONNECTED", mode=self.provider.mode)
        self.state, self.detail = "CONNECTED", self.provider.description
        if self.history_counts and min(self.history_counts.values()) < 300:
            self.detail += "; PARTIAL HISTORY: fewer than 300 bars available for some timeframes"
        if candles:
            self.last_candle = max(c.open_time for c in candles)
        self.sequence += 1
        self.bus.publish(candles)
        return True

    async def run(self) -> None:
        delay = 1
        while True:
            try:
                await self.initialize()
                stream = self.provider.subscribe_ticks("XAUUSD").__aiter__()
                pending = asyncio.create_task(anext(stream))
                try:
                    while True:
                        done, _ = await asyncio.wait({pending}, timeout=1)
                        if not done:
                            if self.status().status == "STALE":
                                await self.event("MARKET_STALE")
                            continue
                        tick = pending.result()
                        await self.ingest(tick)
                        delay = 1
                        pending = asyncio.create_task(anext(stream))
                finally:
                    pending.cancel()
                    with suppress(asyncio.CancelledError, StopAsyncIteration):
                        await pending
                    await stream.aclose()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state, self.detail = "ERROR", "Market source or persistence unavailable; retrying"
                self.bus.publish(None)  # Reconnect clients to the rebuilt authoritative history.
                logger.error("market_data_worker failed", extra=safe_exception(exc))
                with suppress(Exception):
                    await self.event("MARKET_UNAVAILABLE")
                with suppress(Exception):
                    await self.provider.disconnect()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
