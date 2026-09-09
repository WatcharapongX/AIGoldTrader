import asyncio
import datetime as dt

import pytest
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.services.news.public_calendar import normalize
from app.services.news.repository import event_vintages, store_observations

pytestmark = pytest.mark.integration


def test_public_observed_vintages_survive_postgres_reconnect(isolated_postgres):  # noqa: F811
    _alembic("upgrade", "head")

    async def check():
        now = dt.datetime(2026, 9, 9, 14, tzinfo=dt.UTC)
        data = {
            "source": "xoomar.com",
            "updatedAt": "2026-09-09T12:00:00Z",
            "data": [
                {
                    "source": "bls",
                    "eventName": "Nonfarm Payrolls (Employment Situation)",
                    "importance": "high",
                    "scheduledAt": "2026-09-04T12:30:00Z",
                    "periodLabel": "August 2026",
                    "actual": "162",
                    "previous": "21",
                    "forecast": None,
                }
            ],
        }
        async with get_session_factory()() as session:
            assert await store_observations(session, normalize(data, now)) == 1
            await session.commit()
        async with get_session_factory()() as session:
            assert await store_observations(session, normalize(data, now + dt.timedelta(minutes=5))) == 0
            data["data"][0]["actual"] = "163"
            assert await store_observations(session, normalize(data, now + dt.timedelta(minutes=10))) == 1
            await session.commit()
            assert not await event_vintages(session, "xoomar_calendar", now - dt.timedelta(seconds=1))
            assert (await event_vintages(session, "xoomar_calendar", now))[0].actual == 162
            assert (await event_vintages(session, "xoomar_calendar", now + dt.timedelta(minutes=20)))[
                0
            ].revision_version == 2
        await dispose_engine()

    with asyncio.Runner(loop_factory=new_event_loop) as runner:
        runner.run(check())
