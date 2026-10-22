"""D5 persistence, ownership, and cancellation semantics (SQLite disposable)."""

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import NotFoundError, ValidationError
from app.db.base import Base
from app.models.backtest import BacktestRunRecord  # noqa: F401  (registers tables)
from app.services.backtesting import runner
from tests.test_backtesting_d2a import START, inputs
from tests.test_backtesting_d2c import config


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


async def test_execute_persist_and_owner_scope(session):
    record = await runner.execute_and_persist(
        session, owner_id="owner-1", inputs=inputs(), config=config()
    )
    assert record.status == "COMPLETED"
    assert record.simulation_fingerprint
    assert record.payload["metrics"]["total_trades"] == 0
    assert record.payload["provenance"]["data_fingerprint"]

    found = await runner.get_owned_run(session, owner_id="owner-1", run_id=record.id)
    assert found.id == record.id
    with pytest.raises(NotFoundError):
        await runner.get_owned_run(session, owner_id="owner-2", run_id=record.id)


async def test_cancel_terminal_run_fails_closed(session):
    record = await runner.execute_and_persist(
        session, owner_id="owner-1", inputs=inputs(), config=config()
    )
    with pytest.raises(ValidationError):
        await runner.cancel_run(session, owner_id="owner-1", run_id=record.id)


async def test_cancel_created_run_succeeds(session):
    record = BacktestRunRecord(
        id="bt_run_testcreated1",
        owner_id="owner-1",
        status="CREATED",
        symbol="XAUUSD",
        strategy_id="STRAT01",
        profile_id="research",
        created_at=dt.datetime.now(dt.UTC),
        payload={},
    )
    session.add(record)
    await session.commit()
    cancelled = await runner.cancel_run(session, owner_id="owner-1", run_id=record.id)
    assert cancelled.status == "CANCELLED"
    assert cancelled.failure_code == "CANCELLED_BY_OWNER"
    _ = START  # fixture anchor import sanity
