"""D5 bounded in-process backtest runner with persistence and ownership.

Synchronous bounded execution (no Celery/Redis/Kafka). Cancellation is
cooperative: only CREATED/RUNNING runs can transition to CANCELLED, which a
synchronous run never leaves observable, so cancel of a terminal run fails.
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models.backtest import BacktestEquityPointRecord, BacktestRunRecord, BacktestTradeRecord
from app.services.backtesting.domain import RunLifecycle
from app.services.backtesting.metrics import compute_metrics
from app.services.backtesting.replay_domain import ReplayInputs
from app.services.backtesting.risk_replay_domain import RiskReplayConfig
from app.services.backtesting.simulation import simulate


async def execute_and_persist(
    session: AsyncSession, *, owner_id: str, inputs: ReplayInputs, config: RiskReplayConfig
) -> BacktestRunRecord:
    now = dt.datetime.now(dt.UTC)
    run_id = f"bt_run_{uuid.uuid4().hex[:24]}"
    try:
        result = simulate(inputs, config)
        metrics = compute_metrics(result)
        status, failure = RunLifecycle.COMPLETED.value, None
        payload = {
            "simulation": result.model_dump(mode="json"),
            "metrics": metrics.model_dump(mode="json"),
            "config": inputs.manifest.config.model_dump(mode="json"),
            "provenance": {
                "risk_replay_fingerprint": result.risk_replay_fingerprint,
                "simulation_fingerprint": result.simulation_fingerprint,
                "data_fingerprint": inputs.manifest.coverage.data_fingerprint,
            },
        }
    except Exception as error:  # stable failure record; details stay server-side
        result, status, failure = None, RunLifecycle.FAILED.value, type(error).__name__
        payload = {"error_type": failure}
    record = BacktestRunRecord(
        id=run_id,
        owner_id=owner_id,
        status=status,
        symbol=inputs.manifest.config.symbol,
        strategy_id=inputs.manifest.config.strategy_id,
        profile_id=inputs.manifest.config.profile_id,
        simulation_fingerprint=result.simulation_fingerprint if result else None,
        failure_code=failure,
        created_at=now,
        completed_at=dt.datetime.now(dt.UTC),
        payload=payload,
    )
    session.add(record)
    if result is not None:
        for trade in result.trades:
            session.add(
                BacktestTradeRecord(
                    id=f"{run_id}:{trade.trade_id}",
                    run_id=run_id,
                    candidate_id=trade.candidate_id,
                    status=trade.status.value,
                    planned_at=trade.planned_at,
                    payload=trade.model_dump(mode="json"),
                )
            )
        for index, point in enumerate(result.equity_points):
            session.add(
                BacktestEquityPointRecord(
                    id=f"{run_id}:{index}", run_id=run_id, at=point.at, payload=point.model_dump(mode="json")
                )
            )
    await session.commit()
    await session.refresh(record)
    return record


async def get_owned_run(session: AsyncSession, *, owner_id: str, run_id: str) -> BacktestRunRecord:
    record = await session.scalar(
        select(BacktestRunRecord).where(BacktestRunRecord.id == run_id, BacktestRunRecord.owner_id == owner_id)
    )
    if record is None:
        raise NotFoundError("Backtest run not found")
    return record


async def cancel_run(session: AsyncSession, *, owner_id: str, run_id: str) -> BacktestRunRecord:
    record = await get_owned_run(session, owner_id=owner_id, run_id=run_id)
    if record.status not in (RunLifecycle.CREATED.value, RunLifecycle.RUNNING.value):
        raise ValidationError(f"Run in status {record.status} cannot be cancelled")
    record.status = RunLifecycle.CANCELLED.value
    record.failure_code = "CANCELLED_BY_OWNER"
    record.completed_at = dt.datetime.now(dt.UTC)
    await session.commit()
    await session.refresh(record)
    return record
