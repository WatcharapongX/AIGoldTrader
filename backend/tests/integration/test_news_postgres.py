"""PostgreSQL economic migration and immutable vintage acceptance."""

import asyncio
import datetime as dt

import pytest
from psycopg import sql
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.services.news.provider import fixture_release
from app.services.news.repository import event_vintages, store_events

pytestmark = pytest.mark.integration


def test_news_migration_preserves_existing_rows_and_revision_history(isolated_postgres):  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0004_market_unknown_ask")
    conn.execute("INSERT INTO symbols (id,name) VALUES ('00000000-0000-0000-0000-000000000035','KEEP')")
    before = conn.execute("SELECT to_jsonb(s) FROM symbols s").fetchall()
    _alembic("upgrade", "head")
    _alembic("check")
    assert conn.execute("SELECT to_jsonb(s) FROM symbols s").fetchall() == before
    for tbl in (
        "paper_account_states",
        "data_health_records",
        "risk_policies",
        "symbol_specifications",
        "account_snapshots",
        "risk_decisions",
        "risk_reservations",
        "kill_switch_records",
    ):
        conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(tbl)))
    _alembic("downgrade", "0004_market_unknown_ask")
    _alembic("upgrade", "head")

    async def persist():
        at = dt.datetime(2026, 9, 9, 12, 30, tzinfo=dt.UTC)
        try:
            async with get_session_factory()() as session:
                values = fixture_release(at, "mixed")
                assert await store_events(session, values) == 9
                await session.commit()
                assert await store_events(session, values) == 0
                early = await event_vintages(session, "fixture_economic_v1", at)
                assert len(early) == 3 and all(e.actual is None for e in early)
        finally:
            await dispose_engine()

    asyncio.run(persist(), loop_factory=new_event_loop)
    history = conn.execute("SELECT * FROM economic_event_revisions ORDER BY event_id,revision_version").fetchall()
    assert len(history) == 9
    _alembic("downgrade", "0004_market_unknown_ask", success=False)
    assert (
        conn.execute("SELECT * FROM economic_event_revisions ORDER BY event_id,revision_version").fetchall() == history
    )
    assert conn.execute("SELECT to_jsonb(s) FROM symbols s").fetchall() == before
    _alembic("check")
