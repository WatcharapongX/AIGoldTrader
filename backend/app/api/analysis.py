"""Authenticated descriptive analysis over the existing canonical candle repository."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.market import find_symbol, started
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.db.session import get_session
from app.models import User
from app.services.analysis.domain import (
    ALGORITHM_VERSION,
    AnalysisResponse,
    ContextRow,
    MultiTimeframeContext,
)
from app.services.analysis.engine import AnalysisInputError
from app.services.analysis.service import AnalysisService
from app.services.market_data.domain import Timeframe
from app.services.market_data.repository import candles_query

router = APIRouter(prefix="/analysis", tags=["analysis"])


def service(app):
    if not hasattr(app.state, "analysis"):
        app.state.analysis = AnalysisService()
    return app.state.analysis


async def snapshot(request, session, selected, current, timeframe, limit):
    candles = await candles_query(
        session, selected.id, selected.name, timeframe, limit=limit, source=current.provider.source
    )
    tick = current.status().tick_size or Decimal(10) ** -selected.digits
    config = get_settings().analysis_config.model_copy(update={"tick_size": tick})
    try:
        return await service(request.app).response(
            candles, selected.name, timeframe, current.provider.source, limit, config
        )
    except AnalysisInputError:
        raise ValidationError("Canonical analysis input is invalid") from None


@router.get("/structure", response_model=AnalysisResponse)
async def structure(
    request: Request,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.M5,
    limit: int = Query(300, ge=1, le=1000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    selected = await find_symbol(session, symbol)
    if symbol != "XAUUSD":
        raise NotFoundError("No configured source for this symbol")
    return await snapshot(request, session, selected, await started(request), timeframe, limit)


@router.get("/context", response_model=MultiTimeframeContext)
async def context(
    request: Request,
    symbol: str = "XAUUSD",
    limit: int = Query(300, ge=1, le=1000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    selected = await find_symbol(session, symbol)
    if symbol != "XAUUSD":
        raise NotFoundError("No configured source for this symbol")
    current = await started(request)
    rows = []
    for tf in Timeframe:
        value = await snapshot(request, session, selected, current, tf, limit)
        rows.append(
            ContextRow(
                timeframe=tf,
                state=value.external_state,
                history=value.history,
                status=value.modules["external_structure"].status,
                as_of=value.as_of,
            )
        )
    directional = {row.state for row in rows if row.state in ("BULLISH", "BEARISH")}
    bias = (
        "MIXED"
        if len(directional) == 2
        else next(iter(directional))
        if directional
        else "NEUTRAL"
        if any(row.state == "NEUTRAL" for row in rows)
        else "UNKNOWN"
    )
    return MultiTimeframeContext(
        symbol=symbol, source=current.provider.source, algorithm_version=ALGORITHM_VERSION, bias=bias, timeframes=rows
    )
