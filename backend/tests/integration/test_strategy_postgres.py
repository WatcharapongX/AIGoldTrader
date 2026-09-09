"""Phase 4 migration, preservation and idempotence against isolated PostgreSQL."""

import asyncio
import datetime as dt

import pytest
from psycopg import sql
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.services.analysis.domain import AnalysisConfig
from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as news_context
from app.services.strategy.context import build_context
from app.services.strategy.domain import StrategyConfig
from app.services.strategy.engine import evaluate
from app.services.strategy.repository import persist

CONFIG = StrategyConfig()


def context(at=dt.datetime(2026, 9, 7, tzinfo=dt.UTC)):
    news = news_context(
        events=[],
        as_of=at,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    return build_context(
        candles={},
        symbol="XAUUSD",
        source="simulated",
        at=at,
        news=news,
        tick_size=None,
        config=CONFIG,
        analysis_config=AnalysisConfig(),
        replay=True,
    )


pytestmark = pytest.mark.integration


def test_strategy_migration_history_idempotence_and_preservation(isolated_postgres):  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0005_economic_events")
    conn.execute("INSERT INTO symbols (id,name) VALUES ('00000000-0000-0000-0000-000000000046','KEEP')")
    original = conn.execute("SELECT to_jsonb(s) FROM symbols s").fetchall()
    _alembic("upgrade", "head")
    _alembic("check")
    assert conn.execute("SELECT to_jsonb(s) FROM symbols s").fetchall() == original
    _alembic("downgrade", "0005_economic_events")
    _alembic("upgrade", "head")
    _alembic("check")

    async def check():
        first = evaluate(context(), CONFIG)
        second = evaluate(context(at=first.context.as_of + dt.timedelta(minutes=1)), CONFIG)
        try:
            async with get_session_factory()() as session:
                generated = await persist(session, first)
                await session.commit()
                assert await persist(session, first) == generated
                await persist(session, second)
                await session.commit()
                await persist(session, second)
                await session.commit()
        finally:
            await dispose_engine()

    asyncio.run(check(), loop_factory=new_event_loop)
    assert conn.execute("SELECT count(*) FROM strategy_evaluations").fetchone()[0] == 26
    assert conn.execute("SELECT count(*) FROM trader_profiles").fetchone()[0] == 7
    assert conn.execute("SELECT count(*) FROM trade_candidates").fetchone()[0] == 26
    assert conn.execute("SELECT count(*) FROM candidate_transitions").fetchone()[0] == 13
    history = conn.execute("SELECT payload_hash FROM strategy_evaluations ORDER BY id").fetchall()
    _alembic("downgrade", "0005_economic_events", success=False)
    assert conn.execute("SELECT payload_hash FROM strategy_evaluations ORDER BY id").fetchall() == history
    assert conn.execute("SELECT to_jsonb(s) FROM symbols s").fetchall() == original
    _alembic("check")
