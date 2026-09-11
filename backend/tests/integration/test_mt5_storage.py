"""Real PostgreSQL storage checks with OFFLINE price fixtures (not live acceptance)."""

import uuid

import pytest
from psycopg import sql
from test_postgres import _alembic, isolated_postgres  # noqa: F401

pytestmark = pytest.mark.integration


def test_unknown_ask_migration_preserves_sources_and_refuses_lossy_downgrade(isolated_postgres):  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")
    symbol = uuid.uuid4()
    conn.execute("INSERT INTO symbols (id,name) VALUES (%s,'XAUUSD')", (symbol,))
    for source, ask in (("simulated", "2350.30"), ("mt5_demo_fixture", None), ("mt5_live_fixture", None)):
        conn.execute(
            "INSERT INTO candles (symbol_id,source,timeframe,bucket_start,open,high,low,close,volume,"
            "bid_close,ask_close,is_closed) VALUES (%s,%s,'M1','2026-09-09T12:00:00Z',"
            "2350,2351,2349,2350,7,2350,%s,true)",
            (symbol, source, ask),
        )
    before = conn.execute("SELECT source,ask_close FROM candles ORDER BY source").fetchall()
    assert len(before) == 3 and sum(row[1] is None for row in before) == 2
    _alembic("check")
    _alembic("downgrade", "0003_phase2_market_data", success=False)
    assert conn.execute("SELECT source,ask_close FROM candles ORDER BY source").fetchall() == before
    assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0007_risk_engine",)
    # In this owned disposable fixture only, provide known asks to exercise reversible DDL.
    conn.execute("UPDATE candles SET ask_close=2350.30 WHERE ask_close IS NULL")
    known = conn.execute("SELECT * FROM candles ORDER BY source").fetchall()
    _alembic("downgrade", "0003_phase2_market_data")
    _alembic("upgrade", "head")
    assert conn.execute("SELECT * FROM candles ORDER BY source").fetchall() == known
    _alembic("check")
