"""D5 Backtesting API: authenticated, owner-scoped, bounded pagination.

Runs execute synchronously in-process over already-governed replay inputs.
No risk-bypass control exists here; simulation has no execution authority.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import User
from app.models.backtest import BacktestEquityPointRecord, BacktestRunRecord, BacktestTradeRecord
from app.services.backtesting import runner
from app.services.backtesting.replay_domain import ReplayInputs
from app.services.backtesting.risk_replay_domain import RiskReplayConfig

router = APIRouter(prefix="/backtests", tags=["backtests"])

MAX_PAGE_SIZE = 500


class CreateBacktestRequest(BaseModel):
    inputs: ReplayInputs
    config: RiskReplayConfig


class BacktestRunOut(BaseModel):
    id: str
    status: str
    symbol: str
    strategy_id: str
    profile_id: str
    simulation_fingerprint: str | None
    failure_code: str | None
    payload: dict


def _out(record) -> BacktestRunOut:
    return BacktestRunOut(
        id=record.id,
        status=record.status,
        symbol=record.symbol,
        strategy_id=record.strategy_id,
        profile_id=record.profile_id,
        simulation_fingerprint=record.simulation_fingerprint,
        failure_code=record.failure_code,
        payload=record.payload,
    )


@router.post("", response_model=BacktestRunOut)
async def create_backtest(
    body: CreateBacktestRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    record = await runner.execute_and_persist(session, owner_id=str(user.id), inputs=body.inputs, config=body.config)
    return _out(record)


@router.get("", response_model=list[BacktestRunOut])
async def list_backtests(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.scalars(
            select(BacktestRunRecord)
            .where(BacktestRunRecord.owner_id == str(user.id))
            .order_by(BacktestRunRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [_out(r) for r in rows]


@router.get("/{run_id}", response_model=BacktestRunOut)
async def get_backtest(
    run_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return _out(await runner.get_owned_run(session, owner_id=str(user.id), run_id=run_id))


@router.get("/{run_id}/trades")
async def get_trades(
    run_id: str,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await runner.get_owned_run(session, owner_id=str(user.id), run_id=run_id)
    rows = (
        await session.scalars(
            select(BacktestTradeRecord)
            .where(BacktestTradeRecord.run_id == run_id)
            .order_by(BacktestTradeRecord.planned_at)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    total = await session.scalar(
        select(func.count()).select_from(BacktestTradeRecord).where(BacktestTradeRecord.run_id == run_id)
    )
    return {"total": total, "items": [r.payload for r in rows]}


@router.get("/{run_id}/equity")
async def get_equity(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await runner.get_owned_run(session, owner_id=str(user.id), run_id=run_id)
    rows = (
        await session.scalars(
            select(BacktestEquityPointRecord)
            .where(BacktestEquityPointRecord.run_id == run_id)
            .order_by(BacktestEquityPointRecord.at)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {"items": [r.payload for r in rows]}


@router.post("/{run_id}/cancel", response_model=BacktestRunOut)
async def cancel_backtest(
    run_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return _out(await runner.cancel_run(session, owner_id=str(user.id), run_id=run_id))
