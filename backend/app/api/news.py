"""Authenticated calendar and descriptive macro context, using point-in-time revisions."""

import datetime as dt
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.analysis import service as analysis_service
from app.api.deps import get_current_user
from app.api.market import find_symbol, started
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.db.session import get_session, get_session_factory
from app.models import User
from app.services.market_data.domain import SECONDS, Timeframe
from app.services.market_data.repository import candles_query
from app.services.news.domain import CalendarPage, Category, EventDetail, Impact, NewsResponse
from app.services.news.engine import relevance_score
from app.services.news.public_calendar import ProviderHealth
from app.services.news.repository import event_vintages, revisions
from app.services.news.service import NewsService

router = APIRouter(tags=["news"])


async def service(request: Request) -> NewsService:
    market = await started(request)
    if not hasattr(request.app.state, "news"):
        request.app.state.news = NewsService(get_session_factory(), get_settings(), market)
    current = request.app.state.news
    await current.start()
    return current


def cutoff(value: dt.datetime | None) -> dt.datetime:
    now = dt.datetime.now(dt.UTC)
    if value is not None and value > now:
        raise ValidationError("Future knowledge cutoff is not permitted")
    return value.astimezone(dt.UTC) if value else now.replace(microsecond=0)


@router.get("/calendar/economic", response_model=CalendarPage)
async def calendar(
    request: Request,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    as_of: AwareDatetime | None = None,
    currency: str | None = Query(None, pattern="^[A-Z]{3}$"),
    impact: Impact | None = None,
    category: Category | None = None,
    status: Literal["upcoming", "released"] | None = None,
    relevant_only: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    at = cutoff(as_of)
    first, last = start or at - dt.timedelta(days=1), end or at + dt.timedelta(days=1)
    if last <= first or last - first > dt.timedelta(days=7):
        raise ValidationError("Calendar range must be positive and at most seven days")
    current = await service(request)
    values = await event_vintages(session, current.provider.source, at)
    # Choose latest known vintage BEFORE filtering its schedule: reschedules cannot resurrect old dates.
    filtered = [
        e
        for e in values
        if first <= e.scheduled_at < last
        and (currency is None or e.currency == currency)
        and (impact is None or e.impact == impact)
        and (category is None or e.category == category)
        and (not relevant_only or relevance_score(e, current.settings.news_config) >= 2)
        and (
            status is None
            or status == "upcoming"
            and e.scheduled_at > at
            and e.status != "CANCELLED"
            or status == "released"
            and e.status in ("RELEASED", "REVISED")
        )
    ]
    filtered.sort(key=lambda e: (e.scheduled_at, e.id))
    return CalendarPage(
        events=filtered[:200],
        source=current.provider.source,
        source_mode=current.provider.mode,
        state="AVAILABLE" if current.available else "CALENDAR_UNAVAILABLE",
        as_of=at,
        generated_at=dt.datetime.now(dt.UTC),
        truncated=len(filtered) > 200 or len(values) >= 1000,
    )


@router.get("/news/events/{event_id}", response_model=EventDetail)
async def detail(
    request: Request,
    event_id: str,
    as_of: AwareDatetime | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    at = cutoff(as_of)
    if len(event_id) > 100:
        raise NotFoundError("Event not found")
    current = await service(request)
    values = await revisions(session, current.provider.source, event_id, at)
    if not values:
        raise NotFoundError("Event not found at this cutoff")
    return EventDetail(event=values[-1], revisions=values, as_of=at)


@router.get("/news/context", response_model=NewsResponse)
async def context(
    request: Request,
    as_of: AwareDatetime | None = None,
    view: Literal["current", "pre", "release", "post", "none"] = "current",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    at = cutoff(as_of)
    current = await service(request)
    if view != "current":
        if current.provider.mode != "FIXTURE":
            raise ValidationError("Replay views require the fixture provider")
        anchor = at.replace(minute=30, second=0, microsecond=0) - dt.timedelta(hours=1)
        at = anchor + dt.timedelta(seconds={"pre": -1200, "release": 20, "post": 360, "none": 0}[view])
    values = await event_vintages(session, current.provider.source, at)
    values = [e for e in values if at - dt.timedelta(days=7) <= e.scheduled_at <= at + dt.timedelta(days=7)]
    selected = await find_symbol(session, "XAUUSD")
    market = await started(request)
    candles = await candles_query(
        session, selected.id, "XAUUSD", Timeframe.M1, end=at, limit=1000, source=market.provider.source
    )
    structural = await candles_query(
        session, selected.id, "XAUUSD", Timeframe.M5, end=at, limit=300, source=market.provider.source
    )
    structural = [
        c for c in structural if c.is_closed and c.open_time + dt.timedelta(seconds=SECONDS[c.timeframe]) <= at
    ]
    config = get_settings().analysis_config.model_copy(
        update={"tick_size": market.status().tick_size or Decimal(10) ** -selected.digits}
    )
    snapshot = await analysis_service(request.app).snapshot(
        structural, "XAUUSD", Timeframe.M5, market.provider.source, 300, config
    )
    return await current.context(
        events=values, as_of=at, candles=candles, structure=snapshot, view=view, market_source=market.provider.source
    )


@router.get("/news/provider/status", response_model=ProviderHealth)
async def provider_status(request: Request, user: User = Depends(get_current_user)):
    return (await service(request)).health()
