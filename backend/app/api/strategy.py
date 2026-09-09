"""Authenticated analysis-only strategy reads; one repeatable-read context for all traders."""

import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.market import find_symbol, started
from app.api.news import cutoff
from app.api.news import service as news_service
from app.core.config import get_settings
from app.db.session import get_session, get_session_factory
from app.models import User
from app.models.strategy import StrategyEvaluationRecord
from app.services.analysis.engine import analyze
from app.services.market_data.domain import SECONDS, Timeframe
from app.services.market_data.repository import candles_query
from app.services.news.domain import NewsStrategyContext
from app.services.news.repository import event_vintages
from app.services.strategy.context import build_context
from app.services.strategy.domain import (
    SetupCandidate,
    StrategyDefinition,
    StrategyResponse,
    TraderProfile,
    Transition,
)
from app.services.strategy.engine import DEFINITIONS, EvaluationCache, evaluate, profiles
from app.services.strategy.repository import candidate_history, persist, transitions

router = APIRouter(tags=["strategy"])


async def current(request: Request, value: dt.datetime | None) -> StrategyResponse:
    at = cutoff(value).replace(second=0, microsecond=0)
    settings = get_settings()
    market = await started(request)
    news = await news_service(request)
    if not hasattr(request.app.state, "strategy_lock"):
        request.app.state.strategy_lock = asyncio.Lock()
        request.app.state.strategy_cache = EvaluationCache()
    async with request.app.state.strategy_lock:
        async with get_session_factory()() as session:
            async with session.begin():
                if session.get_bind().dialect.name == "postgresql":
                    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                symbol = await find_symbol(session, "XAUUSD")
                source = market.provider.source
                status = market.status()
                inputs = {}
                for tf in Timeframe:
                    inputs[tf] = await candles_query(
                        session,
                        symbol.id,
                        "XAUUSD",
                        tf,
                        end=at,
                        limit=1000 if tf in (Timeframe.M1, Timeframe.M5) else 300,
                        source=source,
                    )
                # Only the read-only provider's verified tick size is admitted to geometry.
                analysis_config = settings.analysis_config.model_copy(
                    update={"tick_size": status.tick_size or settings.analysis_config.tick_size}
                )
                m5 = [
                    c
                    for c in inputs[Timeframe.M5]
                    if c.is_closed and c.open_time + dt.timedelta(seconds=SECONDS[Timeframe.M5]) <= at
                ]
                snapshot = await asyncio.to_thread(
                    analyze, m5[-300:], "XAUUSD", Timeframe.M5, source, 300, analysis_config
                )
                events = await event_vintages(session, news.provider.source, at)
                events = [e for e in events if at - dt.timedelta(days=7) <= e.scheduled_at <= at + dt.timedelta(days=7)]
                response = await news.context(
                    events=events,
                    as_of=at,
                    candles=inputs[Timeframe.M1],
                    structure=snapshot,
                    view="current",
                    market_source=source,
                )
                news_context = NewsStrategyContext.model_validate(
                    response.model_dump(exclude={"generated_at", "served_at", "cache_age_seconds"})
                )
                context = await asyncio.to_thread(
                    build_context,
                    candles=inputs,
                    symbol="XAUUSD",
                    source=source,
                    at=at,
                    news=news_context,
                    tick_size=status.tick_size,
                    config=settings.strategy_config,
                    analysis_config=analysis_config,
                    replay=False,
                    quotes=tuple(news.quotes),
                )
                result = await asyncio.to_thread(
                    evaluate, context, settings.strategy_config, cache=request.app.state.strategy_cache
                )
                generated = await persist(session, result)
        now = dt.datetime.now(dt.UTC)
        return StrategyResponse(
            evaluation=result,
            generated_at=generated,
            served_at=now,
            stale=(now - at).total_seconds() > 120 or status.status not in ("CONNECTED",),
        )


@router.get("/strategy/context", response_model=StrategyResponse)
@router.get("/trade-plan/current", response_model=StrategyResponse)
async def current_context(request: Request, as_of: AwareDatetime | None = None, user: User = Depends(get_current_user)):
    return await current(request, as_of)


@router.get("/strategies", response_model=list[StrategyDefinition])
async def definitions(user: User = Depends(get_current_user)):
    return list(DEFINITIONS)


@router.get("/trader-profiles", response_model=list[TraderProfile])
async def trader_profiles(request: Request, user: User = Depends(get_current_user)):
    result = await current(request, None)
    return list(profiles(get_settings().strategy_config, result.evaluation.context.config_id))


@router.get("/strategy/evaluations", response_model=list[StrategyResponse])
async def evaluations(
    limit: int = Query(10, ge=1, le=25),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.scalars(
            select(StrategyEvaluationRecord)
            .order_by(StrategyEvaluationRecord.as_of.desc(), StrategyEvaluationRecord.generated_at.desc())
            .limit(limit)
        )
    ).all()
    from app.services.strategy.domain import Evaluation

    now = dt.datetime.now(dt.UTC)
    return [
        StrategyResponse(
            evaluation=Evaluation.model_validate(row.payload), generated_at=row.generated_at, served_at=now, stale=True
        )
        for row in rows
    ]


@router.get("/trade-candidates", response_model=list[SetupCandidate])
async def candidates(
    limit: int = Query(50, ge=1, le=100),
    profile_id: str | None = Query(None, max_length=64, pattern="^[a-z0-9_-]+$"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await candidate_history(session, limit=limit, profile_id=profile_id)


@router.get("/trade-candidates/{candidate_id}/transitions", response_model=list[Transition])
async def candidate_transitions(
    candidate_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    if len(candidate_id) != 64 or any(c not in "0123456789abcdef" for c in candidate_id):
        return []
    return await transitions(session, candidate_id)
