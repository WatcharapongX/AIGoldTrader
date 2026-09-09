"""Single-process bounded provider worker. Browsers never poll external providers."""

import asyncio
import datetime as dt
import logging
import time
from collections import OrderedDict, deque
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.services.market_data.service import MarketService
from app.services.news.domain import NewsResponse, ObservedQuote
from app.services.news.engine import build_context
from app.services.news.forex_factory import ForexFactoryCalendarProvider
from app.services.news.provider import (
    EconomicCalendarProvider,
    EconomicCalendarReplayProvider,
    UnavailableCalendarProvider,
)
from app.services.news.public_calendar import ProviderHealth, PublicCalendarProvider, RateLimited
from app.services.news.repository import store_events, store_observations

logger = logging.getLogger(__name__)


class NewsService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], settings: Settings, market: MarketService):
        self.factory, self.settings, self.market = factory, settings, market
        self.provider: EconomicCalendarProvider = (
            EconomicCalendarReplayProvider()
            if settings.news_calendar_provider == "fixture"
            else ForexFactoryCalendarProvider()
            if settings.news_calendar_provider == "forex_factory"
            else PublicCalendarProvider()
            if settings.news_calendar_provider == "xoomar"
            else UnavailableCalendarProvider()
        )
        self.quotes: deque[ObservedQuote] = deque(maxlen=3600)
        self.task: asyncio.Task | None = None
        self.poll_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.last_success: float | None = None
        self.next_poll = 0.0
        self.failures = 0
        self.last_sync_at: dt.datetime | None = None
        self.event_count = 0
        self.last_reason = "NOT_SYNCED"
        self.cache: OrderedDict[str, NewsResponse] = OrderedDict()

    @property
    def available(self) -> bool:
        return (
            self.failures == 0
            and not getattr(self.provider, "limited_coverage", False)
            and self.last_success is not None
            and time.monotonic() - self.last_success <= self.settings.news_config.provider_stale_seconds
        )

    @property
    def poll_seconds(self) -> int:
        return (
            self.settings.news_real_poll_seconds
            if self.provider.mode == "LIVE"
            else self.settings.news_config.provider_poll_seconds
        )

    def health(self) -> ProviderHealth:
        now = dt.datetime.now(dt.UTC)
        stale = self.last_success is not None and time.monotonic() - self.last_success > max(
            self.settings.news_config.provider_stale_seconds, self.poll_seconds * 2
        )
        limited = bool(getattr(self.provider, "limited_coverage", False))
        state = (
            "UNAVAILABLE"
            if self.last_success is None
            else "STALE"
            if stale
            else "DEGRADED"
            if self.failures or limited or self.provider.mode == "FIXTURE"
            else "HEALTHY"
        )
        detail = (
            "ข้อมูลจริงครอบคลุมบางส่วน ไม่มีคาดการณ์ และผลประกาศอาจช้าถึงหนึ่งชั่วโมง จึงยังใช้อนุมัติกลยุทธ์ไม่ได้"
            if limited
            else "ข้อมูลสาธิต ไม่ใช่ข่าวจริง"
            if self.provider.mode == "FIXTURE"
            else "Forex Factory: ปฏิทิน USD รายสัปดาห์; Actual อาจไม่มี ต้องรอผลจริงสำหรับกลยุทธ์ข่าว"
            if isinstance(self.provider, ForexFactoryCalendarProvider)
            else "ผู้ให้บริการข่าวไม่พร้อม"
        )
        return ProviderHealth.model_validate(
            dict(
                source=self.provider.source,
                source_mode=self.provider.mode,
                state=state,
                connected=self.last_success is not None and self.failures == 0 and not stale,
                coverage="LIMITED"
                if limited or isinstance(self.provider, ForexFactoryCalendarProvider)
                else "FIXTURE"
                if self.provider.mode == "FIXTURE"
                else "NONE",
                calendar_usable_for_trading=self.available and self.provider.mode == "LIVE",
                provider_updated_at=getattr(self.provider, "provider_updated_at", None),
                received_at=getattr(self.provider, "received_at", self.last_sync_at),
                snapshot_clock_skew_seconds=(
                    (self.provider.provider_updated_at - self.provider.received_at).total_seconds()
                    if isinstance(self.provider, PublicCalendarProvider)
                    and self.provider.provider_updated_at
                    and self.provider.received_at
                    else 0
                ),
                last_sync_at=self.last_sync_at,
                next_poll_at=now + dt.timedelta(seconds=max(0, self.next_poll - time.monotonic())),
                event_count=self.event_count,
                failures=self.failures,
                poll_seconds=self.poll_seconds,
                reason_code=self.last_reason
                if self.failures
                else "LIMITED_COVERAGE"
                if limited
                else "FIXTURE"
                if self.provider.mode == "FIXTURE"
                else "SCHEDULE_FORECAST_ONLY"
                if isinstance(self.provider, ForexFactoryCalendarProvider) and self.last_success is not None
                else "NOT_SYNCED",
                detail_th=detail,
            )
        )

    async def start(self) -> None:
        async with self.lock:
            if self.task is None:
                await self.poll()
                self.task = asyncio.create_task(self.run(), name="economic-calendar")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        if self.poll_task is not None:
            self.poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.poll_task
            self.poll_task = None

    async def poll(self) -> None:
        now = dt.datetime.now(dt.UTC)
        retry_after = 0
        try:
            events = await asyncio.wait_for(
                self.provider.fetch(
                    now - dt.timedelta(days=7 if self.provider.mode == "LIVE" else 1),
                    now + dt.timedelta(days=30 if self.provider.mode == "LIVE" else 1),
                    now,
                ),
                timeout=15,
            )
            async with self.factory() as session:
                if self.provider.mode == "LIVE":
                    await store_observations(session, events)
                else:
                    await store_events(session, events)
                await session.commit()
            self.last_success, self.failures = time.monotonic(), 0
            self.last_sync_at, self.event_count = dt.datetime.now(dt.UTC), len(events)
            self.last_reason = "SYNCED"
        except Exception as exc:
            self.failures += 1
            self.last_reason = "RATE_LIMITED" if isinstance(exc, RateLimited) else "PROVIDER_FAILURE"
            retry_after = exc.seconds if isinstance(exc, RateLimited) else 0
            logger.warning("economic_provider_poll failed (%s)", type(exc).__name__)
        delay = max(retry_after, min(3600, self.poll_seconds * 2 ** min(self.failures, 4)))
        self.next_poll = time.monotonic() + delay

    async def run(self) -> None:
        while True:
            quote = self.market.quote
            now = dt.datetime.now(dt.UTC)
            if quote is not None and (not self.quotes or quote.timestamp > self.quotes[-1].timestamp):
                self.quotes.append(
                    ObservedQuote(
                        timestamp=quote.timestamp, observed_at=now, bid=quote.bid, ask=quote.ask, source=quote.source
                    )
                )
            # A slow calendar endpoint must never pause market quote observations.
            if time.monotonic() >= self.next_poll and (self.poll_task is None or self.poll_task.done()):
                self.poll_task = asyncio.create_task(self.poll(), name="economic-calendar-poll")
            await asyncio.sleep(1)

    async def context(self, **inputs) -> NewsResponse:
        value = await asyncio.to_thread(
            build_context,
            config=self.settings.news_config,
            quotes=list(self.quotes),
            source=self.provider.source,
            mode=self.provider.mode,
            calendar_available=self.available,
            **inputs,
        )
        now = dt.datetime.now(dt.UTC)
        old = self.cache.get(value.fingerprint)
        generated = old.generated_at if old else now
        result = NewsResponse(
            **value.model_dump(),
            generated_at=generated,
            served_at=now,
            cache_age_seconds=max(0, (now - generated).total_seconds()),
        )
        self.cache[value.fingerprint] = result
        self.cache.move_to_end(value.fingerprint)
        if len(self.cache) > 32:
            self.cache.popitem(last=False)
        return result
