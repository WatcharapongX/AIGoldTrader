"""Synthetic canonical fixture in an owned PostgreSQL TEST schema; not real-price acceptance."""

import asyncio
import datetime as dt

import pytest
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.models import Symbol
from app.services.analysis.engine import AnalysisEngine, analyze
from app.services.market_data.domain import Timeframe
from app.services.market_data.provider import ReplayProvider
from app.services.market_data.repository import candles_query, upsert_candles

pytestmark = pytest.mark.integration


def test_analysis_postgres_all_timeframes_and_partial_week(isolated_postgres):  # noqa: F811
    _alembic("upgrade", "head")

    async def check():
        async with get_session_factory()() as session:
            symbol = Symbol(name="XAUUSD")
            session.add(symbol)
            await session.flush()
            for tf in Timeframe:
                count = 231 if tf == Timeframe.W1 else 300
                values = ReplayProvider().get_historical_candles(
                    "XAUUSD", tf, dt.datetime(2026, 9, 9, 12, tzinfo=dt.UTC), count
                )
                await upsert_candles(session, symbol.id, values)
                await session.commit()
                stored = await candles_query(session, symbol.id, "XAUUSD", tf, limit=300, source="simulated")
                assert len(stored) == count
                snapshot = analyze(stored, "XAUUSD", tf, "simulated")
                stream = AnalysisEngine("XAUUSD", tf, "simulated")
                for candle in stored:
                    if candle.is_closed:
                        stream.feed(candle)
                assert snapshot == stream.snapshot(returned=count)
                assert snapshot.history.status == ("PARTIAL" if tf == Timeframe.W1 else "COMPLETE")
                assert snapshot.modules["external_structure"].status != "INSUFFICIENT_DATA"
                assert not await candles_query(session, symbol.id, "XAUUSD", tf, source="mt5_demo_iux")
        await dispose_engine()

    asyncio.run(check(), loop_factory=new_event_loop)
    _alembic("check")
