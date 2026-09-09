import asyncio
import datetime as dt

import pytest
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.services.news.forex_factory import SOURCE, normalize
from app.services.news.repository import event_vintages, store_observations

pytestmark = pytest.mark.integration


def test_ff_observation_dedup_revisions_and_restart(isolated_postgres):  # noqa: F811
    _alembic("upgrade", "head")

    async def check():
        now = dt.datetime(2026, 9, 10, 13, tzinfo=dt.UTC)
        row = dict(
            title="Unemployment Claims",
            country="USD",
            date="2026-09-10T08:30:00-04:00",
            impact="Medium",
            forecast="205K",
            previous="206K",
        )
        async with get_session_factory()() as session:
            assert await store_observations(session, normalize([row], now)) == 1
            await session.commit()
        await dispose_engine()
        async with get_session_factory()() as session:
            assert await store_observations(session, normalize([row], now + dt.timedelta(minutes=5))) == 0
            row["actual"] = "200K"
            assert await store_observations(session, normalize([row], now + dt.timedelta(minutes=10))) == 1
            await session.commit()
            first = (await event_vintages(session, SOURCE, now))[0]
            assert first.actual is None and first.forecast == 205
            second = (await event_vintages(session, SOURCE, now + dt.timedelta(minutes=10)))[0]
            assert second.actual == 200 and second.revision_version == 2
            assert second.available_at == now + dt.timedelta(minutes=10)
            assert second.field_provenance["actual"] == SOURCE
            row["previous"] = "210K"
            assert await store_observations(session, normalize([row], now + dt.timedelta(minutes=15))) == 1
            latest = (await event_vintages(session, SOURCE, now + dt.timedelta(minutes=15)))[0]
            from app.services.news.domain import NewsConfig
            from app.services.news.engine import surprise

            assert surprise(latest, NewsConfig()).revision_delta == 4
            assert await store_observations(session, []) == 0  # omission is never cancellation
        await dispose_engine()

    with asyncio.Runner(loop_factory=new_event_loop) as runner:
        runner.run(check())
