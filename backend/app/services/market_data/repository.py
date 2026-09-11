import datetime as dt
import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import MarketCandle, MarketTick
from app.services.market_data.domain import SECONDS, Candle, Tick, Timeframe


def candle_row(symbol_id: uuid.UUID, candle: Candle) -> dict:
    row = candle.model_dump(exclude={"symbol", "open_time"})
    row.update(symbol_id=symbol_id, bucket_start=candle.open_time, timeframe=candle.timeframe.value)
    return row


async def upsert_candles(session, symbol_id: uuid.UUID, candles: list[Candle]) -> None:
    if not candles:
        return
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    for offset in range(0, len(candles), 100):
        stmt = insert(MarketCandle).values([candle_row(symbol_id, c) for c in candles[offset : offset + 100]])
        columns = ("symbol_id", "source", "timeframe", "bucket_start")
        stmt = stmt.on_conflict_do_update(
            index_elements=list(columns),
            set_={
                c.name: getattr(stmt.excluded, c.name) for c in MarketCandle.__table__.columns if c.name not in columns
            },
        )
        await session.execute(stmt)


async def save_tick(session, symbol_id: uuid.UUID, tick: Tick) -> None:
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    await session.execute(
        insert(MarketTick)
        .values(
            symbol_id=symbol_id,
            source=tick.source,
            ts=tick.timestamp,
            bid=tick.bid,
            ask=tick.ask,
            spread=tick.ask - tick.bid,
            volume=tick.volume,
        )
        .on_conflict_do_nothing()
    )


async def prune(session, symbol_id: uuid.UUID, now: dt.datetime) -> None:
    # Bound only this simulated source's data, never user/account or other provider records.
    await session.execute(
        delete(MarketTick).where(
            MarketTick.symbol_id == symbol_id,
            MarketTick.source == "simulated",
            MarketTick.ts < now - dt.timedelta(days=1),
        )
    )
    for timeframe, seconds in SECONDS.items():
        await session.execute(
            delete(MarketCandle).where(
                MarketCandle.symbol_id == symbol_id,
                MarketCandle.source == "simulated",
                MarketCandle.timeframe == timeframe.value,
                MarketCandle.bucket_start < now - dt.timedelta(seconds=seconds * 1000),
            )
        )


async def candles_query(
    session, symbol_id, symbol, timeframe, start=None, end=None, limit=300, source="simulated"
) -> list[Candle]:
    query = select(MarketCandle).where(
        MarketCandle.symbol_id == symbol_id,
        MarketCandle.source == source,
        MarketCandle.timeframe == timeframe.value,
    )
    if start:
        query = query.where(MarketCandle.bucket_start >= start)
    if end:
        query = query.where(MarketCandle.bucket_start < end)
    rows = (await session.scalars(query.order_by(MarketCandle.bucket_start.desc()).limit(limit))).all()
    return [
        Candle(
            symbol=symbol,
            timeframe=Timeframe(row.timeframe),
            open_time=row.bucket_start.replace(tzinfo=dt.UTC) if row.bucket_start.tzinfo is None else row.bucket_start,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            bid_close=row.bid_close,
            ask_close=row.ask_close,
            source=row.source,
            is_closed=row.is_closed,
        )
        for row in reversed(rows)
    ]
