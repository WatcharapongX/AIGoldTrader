"""Authenticated bounded command-center aggregation; card failures are isolated."""

import asyncio
import datetime as dt
import time
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, Field
from sqlalchemy import text

from app.api.analysis import service as analysis_service
from app.api.deps import get_current_user
from app.api.market import find_symbol, started
from app.api.news import context as news_context
from app.api.news import service as news_service
from app.api.strategy import current as strategy_current
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import User
from app.services.analysis.domain import History, LiquidityLevel, StructureEvent
from app.services.market_data.domain import SECONDS, MarketDataStatus, Quote, Timeframe
from app.services.market_data.repository import candles_query
from app.services.news.domain import EconomicEvent, NewsResponse, UTCModel
from app.services.news.public_calendar import ProviderHealth
from app.services.news.repository import event_vintages
from app.services.strategy.domain import (
    KeyLevel,
    SetupCandidate,
    StrategyDefinition,
    TradePlanSuggestion,
    TraderProfile,
)
from app.services.strategy.engine import DEFINITIONS

router = APIRouter(tags=["dashboard"])


class DashboardHealth(UTCModel):
    module: str
    state: Literal["HEALTHY", "DEGRADED", "STALE", "UNAVAILABLE", "UNKNOWN", "DISABLED"]
    detail_th: str


class StructureSummary(UTCModel):
    timeframe: Timeframe
    input_id: str
    as_of: AwareDatetime | None
    internal_state: str
    external_state: str
    regime: str
    history: History
    latest_event: StructureEvent | None
    liquidity: list[LiquidityLevel] = Field(max_length=4)


class DashboardSummary(UTCModel):
    generated_at: AwareDatetime
    served_at: AwareDatetime
    refresh_seconds: Literal[30] = 30
    symbol: Literal["XAUUSD"] = "XAUUSD"
    trading_mode: Literal["PAPER"] = "PAPER"
    live_auto_trading: Literal[False] = False
    broker_execution: Literal["DISABLED"] = "DISABLED"
    risk_engine: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"
    market: MarketDataStatus | None
    quote: Quote | None
    structure: list[StructureSummary] = Field(max_length=4)
    analysis_generated_at: AwareDatetime | None
    current_session: str | None
    key_levels: list[KeyLevel] = Field(max_length=12)
    news: NewsResponse | None
    news_provider: ProviderHealth | None
    calendar_events: list[EconomicEvent] = Field(max_length=12)
    strategies: list[StrategyDefinition] = Field(max_length=6)
    profiles: list[TraderProfile] = Field(max_length=7)
    candidates: list[SetupCandidate] = Field(max_length=13)
    strategy_market_context_id: str | None = None
    strategy_context_id: str | None
    strategy_generated_at: AwareDatetime | None
    strategy_as_of: AwareDatetime | None
    strategy_stale: bool
    current_plan: TradePlanSuggestion | None
    adaptive_status: Literal["RESERVED_DISABLED"] = "RESERVED_DISABLED"
    health: list[DashboardHealth] = Field(max_length=10)


async def analysis_card(request: Request):
    at = dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
    market = await started(request)
    rows = []
    async with get_session_factory()() as session:
        symbol = await find_symbol(session, "XAUUSD")
        config = get_settings().analysis_config.model_copy(
            update={"tick_size": market.status().tick_size or get_settings().analysis_config.tick_size}
        )
        for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5):
            candles = await candles_query(
                session, symbol.id, "XAUUSD", tf, end=at, limit=300, source=market.provider.source
            )
            candles = [c for c in candles if c.is_closed and c.open_time + dt.timedelta(seconds=SECONDS[tf]) <= at]
            snapshot = await analysis_service(request.app).snapshot(
                candles, "XAUUSD", tf, market.provider.source, 300, config
            )
            rows.append(
                StructureSummary(
                    timeframe=tf,
                    input_id=snapshot.input_id,
                    as_of=snapshot.as_of,
                    internal_state=snapshot.internal_state,
                    external_state=snapshot.external_state,
                    regime=snapshot.regime,
                    history=snapshot.history,
                    latest_event=max(snapshot.events, key=lambda e: e.confirmed_at, default=None),
                    liquidity=[e for e in snapshot.liquidity if e.status == "ACTIVE"][-4:],
                )
            )
    return rows


async def news_card(request: Request):
    provider = await news_service(request)
    async with get_session_factory()() as session:
        context = await news_context(request, as_of=None, view="current", session=session)
        at = dt.datetime.now(dt.UTC)
        events = await event_vintages(session, provider.provider.source, at)
        recent = sorted(
            [e for e in events if at - dt.timedelta(days=7) <= e.scheduled_at <= at],
            key=lambda e: e.scheduled_at,
            reverse=True,
        )[:4]
        upcoming = sorted(
            [e for e in events if at < e.scheduled_at <= at + dt.timedelta(days=30)], key=lambda e: e.scheduled_at
        )[:8]
    return context, provider.health(), recent + upcoming


async def database_card():
    async with get_session_factory()() as session:
        await session.execute(text("SELECT 1"))
        return session.get_bind().dialect.name


async def bounded(coroutine):
    try:
        return await asyncio.wait_for(coroutine, timeout=25)
    except Exception:
        # Never serialize exception text: SQL/HTTP exceptions may contain credentials.
        return None


async def assemble(request: Request) -> DashboardSummary:
    market, news, structures, strategy, database = await asyncio.gather(
        bounded(started(request)),
        bounded(news_card(request)),
        bounded(analysis_card(request)),
        bounded(strategy_current(request, None)),
        bounded(database_card()),
    )
    now = dt.datetime.now(dt.UTC)
    status = market.status() if market else None
    evaluation = strategy.evaluation if strategy else None
    context = evaluation.context if evaluation else None
    candidates = list(evaluation.candidates) if evaluation else []
    stale = strategy.stale if strategy else True
    # Same immutable candidates as Phase 4. Stable score/id ordering; never elevate a blocked candidate.
    ready = sorted(
        [c for c in candidates if c.status == "READY" and c.plan and c.expires_at > now], key=lambda c: (-c.score, c.id)
    )
    health = [
        DashboardHealth(module="backend", state="HEALTHY", detail_th="API ตอบสนอง"),
        DashboardHealth(
            module="database",
            state="HEALTHY" if database else "UNAVAILABLE",
            detail_th="PostgreSQL"
            if database == "postgresql"
            else "ฐานข้อมูลทดสอบ"
            if database
            else "ตรวจฐานข้อมูลไม่สำเร็จ",
        ),
        DashboardHealth(
            module="market",
            state="HEALTHY" if status and status.status == "CONNECTED" else "DEGRADED",
            detail_th="ตรวจจาก provider ราคาจริงและเวลา quote",
        ),
        DashboardHealth(
            module="news",
            state=news[1].state if news else "UNAVAILABLE",
            detail_th=news[1].detail_th if news else "โหลดข่าวไม่สำเร็จ",
        ),
        DashboardHealth(
            module="analysis",
            state="HEALTHY" if structures and all(r.history.closed >= 60 for r in structures) else "DEGRADED",
            detail_th="โครงสร้างจากแท่งปิด H4/H1/M15/M5",
        ),
        DashboardHealth(
            module="strategy",
            state="UNAVAILABLE" if not strategy else "STALE" if stale else "HEALTHY",
            detail_th="สถานะการคำนวณ ไม่ใช่สิทธิ์ส่งคำสั่งซื้อขาย",
        ),
        DashboardHealth(module="websocket", state="UNKNOWN", detail_th="ตรวจการเชื่อมต่อจากหน้านี้"),
        DashboardHealth(module="broker_execution", state="DISABLED", detail_th="ไม่มีการส่งคำสั่ง"),
    ]
    levels = (
        []
        if not context
        else [
            k
            for k in context.key_levels
            if k.kind in ("PDH", "PDL", "PWH", "PWL", "ASIA_HIGH", "ASIA_LOW", "SESSION_HIGH", "SESSION_LOW")
        ]
    )
    # Most recently confirmed levels, bounded; no arbitrary generated levels.
    levels = sorted(levels, key=lambda k: (k.valid_from, k.id), reverse=True)[:12]
    return DashboardSummary(
        generated_at=now,
        served_at=now,
        market=status,
        quote=market.quote if market else None,
        structure=structures or [],
        analysis_generated_at=now if structures else None,
        current_session=context.current_session if context else None,
        key_levels=levels,
        news=news[0] if news else None,
        news_provider=news[1] if news else None,
        calendar_events=news[2] if news else [],
        strategies=list(DEFINITIONS),
        profiles=list(evaluation.profiles) if evaluation else [],
        candidates=candidates,
        strategy_market_context_id=context.market_context_id if context else None,
        strategy_context_id=context.id if context else None,
        strategy_generated_at=strategy.generated_at if strategy else None,
        strategy_as_of=context.as_of if context else None,
        strategy_stale=stale,
        current_plan=ready[0].plan if ready and not stale else None,
        health=health,
    )


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def summary(request: Request, user: User = Depends(get_current_user)):
    if not hasattr(request.app.state, "dashboard_lock"):
        request.app.state.dashboard_lock = asyncio.Lock()
    async with request.app.state.dashboard_lock:
        cached = getattr(request.app.state, "dashboard_cached", None)
        if cached is None or time.monotonic() - cached[0] >= 30:
            value = await assemble(request)
            request.app.state.dashboard_cached = (time.monotonic(), value)
        else:
            value = cached[1]
        # Market/news health ages independently of the expensive summary cache.
        provider = getattr(request.app.state, "news", None)
        market = getattr(request.app.state, "market", None)
        updates: dict = {"served_at": dt.datetime.now(dt.UTC)}
        if provider:
            updates["news_provider"] = provider.health()
        if market:
            updates.update(market=market.status(), quote=market.quote)
        now = updates["served_at"]
        if value.current_plan and (
            value.current_plan.expires_at <= now
            or provider
            and not provider.available
            and any(
                c.id == value.current_plan.candidate_id and c.strategy_id in ("STRAT05", "STRAT06")
                for c in value.candidates
            )
            or market
            and market.status().status != "CONNECTED"
        ):
            updates.update(current_plan=None, strategy_stale=True)
        health = list(value.health)
        if provider:
            current_health = provider.health()
            health = [
                h.model_copy(update={"state": current_health.state, "detail_th": current_health.detail_th})
                if h.module == "news"
                else h
                for h in health
            ]
        if market:
            health = [
                h.model_copy(update={"state": "HEALTHY" if market.status().status == "CONNECTED" else "DEGRADED"})
                if h.module == "market"
                else h
                for h in health
            ]
        updates["health"] = health
        return value.model_copy(update=updates)
