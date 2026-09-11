"""Real PostgreSQL -> native Uvicorn -> authenticated WS -> query/reconnect gate."""

import asyncio
import json
import time

import pytest
from launch_support import launch_commands, log_records, native_server
from psycopg import sql
from test_postgres import _alembic, isolated_postgres  # noqa: F401 — shared owned-schema fixture
from websockets.sync.client import connect

from app.core.event_loop import new_event_loop
from app.db.seed import seed_admin, seed_symbols
from app.db.session import dispose_engine
from app.services.market_data.domain import MarketMessage

pytestmark = pytest.mark.integration


def test_live_market_database_websocket_stale_and_recovery(isolated_postgres, tmp_path):  # noqa: F811
    conn, schema = isolated_postgres
    _alembic("upgrade", "head")

    async def seed():
        await seed_symbols()
        await seed_admin("market@example.com", "market-fixture-pass")
        await dispose_engine()

    asyncio.run(seed(), loop_factory=new_event_loop)
    # Test-only local control module: never installed into the application routes.
    probe = tmp_path / "market_probe.py"
    probe.write_text(
        """
from app.main import create_app
from app.api.market import service
from app.services.market_data.provider import ReplayProvider
from fastapi import Request
import asyncio
app = create_app()
class PausableReplay(ReplayProvider):
    paused = False
    async def subscribe_ticks(self, symbol):
        async for tick in super().subscribe_ticks(symbol):
            while self.paused:
                await asyncio.sleep(0.1)
            yield tick
service(app).provider = PausableReplay()
@app.post("/_gate/pause")
async def pause(request: Request):
    service(request.app).provider.paused = True
    return {"paused": True}
@app.post("/_gate/resume")
async def resume(request: Request):
    service(request.app).provider.paused = False
    return {"resumed": True}
""",
        encoding="utf-8",
    )
    log = tmp_path / "market.log"
    with native_server(
        launch_commands()["docker-compose.yml"],
        log,
        app_module="market_probe:app",
        extra_env={"PYTHONPATH": str(tmp_path), "CORS_ORIGINS": "http://localhost:3000"},
    ) as client:
        assert client.get("/api/market/status").status_code == 401
        login = client.post("/api/auth/login", json={"email": "market@example.com", "password": "market-fixture-pass"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        for _ in range(40):
            status = client.get("/api/market/status", headers=headers).json()
            if status["status"] == "CONNECTED":
                break
            time.sleep(0.5)
        assert status["status"] == "CONNECTED"
        assert client.get("/healthz").status_code == 200
        url = str(client.base_url).replace("http://", "ws://").rstrip("/") + "/ws/market"

        def receive(ws, kind=None):
            for _ in range(20):
                message = MarketMessage.model_validate_json(ws.recv(timeout=8))
                if kind is None or message.type == kind:
                    return message
            raise AssertionError("Expected WS message not received")

        for timeframe in ("M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1", "W1"):
            response = client.get(
                "/api/market/candles",
                params={"symbol": "XAUUSD", "timeframe": timeframe, "limit": 300},
                headers=headers,
            )
            assert response.status_code == 200 and len(response.json()["candles"]) == 300
            assert all(c["open_time"].endswith("Z") for c in response.json()["candles"])
        with connect(url, origin="http://localhost:3000", proxy=None) as ws:
            ws.send(json.dumps({"type": "auth", "token": token}))
            ws.send(json.dumps({"type": "subscribe", "symbol": "XAUUSD", "timeframe": "M5"}))
            snapshot = receive(ws, "snapshot")
            assert len(snapshot.candles) == 300
            update = receive(ws, "update")
            assert update.sequence > snapshot.sequence
            assert update.quote.bid <= update.quote.ask
            assert update.candles[-1].open_time >= snapshot.candles[-1].open_time
            ws.send(json.dumps({"type": "subscribe", "symbol": "XAUUSD", "timeframe": "H1"}))
            assert receive(ws, "snapshot").timeframe.value == "H1"
            ws.send(json.dumps({"type": "ping"}))
            assert receive(ws, "heartbeat").timeframe.value == "H1"
            client.post("/_gate/pause")
            for _ in range(8):
                stale = receive(ws)
                if stale.status.status == "STALE":
                    break
            assert stale.status.status == "STALE"
            assert client.get("/healthz").status_code == 200
            client.post("/_gate/resume")
            assert receive(ws, "update").status.status == "CONNECTED"
        # New transport receives an authoritative snapshot after disconnect.
        with connect(url, origin="http://localhost:3000", proxy=None) as ws:
            ws.send(json.dumps({"type": "auth", "token": token}))
            ws.send(json.dumps({"type": "subscribe", "symbol": "XAUUSD", "timeframe": "M5"}))
            assert len(receive(ws, "snapshot").candles) == 300
        client.post("/api/auth/logout", headers=headers)
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    assert conn.execute("SELECT count(*) FROM ticks").fetchone()[0] >= 2
    assert conn.execute("SELECT count(DISTINCT timeframe) FROM candles").fetchone()[0] == 9
    events = conn.execute("SELECT count(*) FROM system_events WHERE code = %s", ("MARKET_STALE",)).fetchone()
    assert events[0] >= 1
    invalid = conn.execute("SELECT count(*) FROM candles WHERE high < low OR high < close OR low > open").fetchone()
    assert invalid[0] == 0
    assert token not in log.read_text(encoding="utf-8")
    assert "market-fixture-pass" not in log.read_text(encoding="utf-8")
    assert not [r for r in log_records(log) if r.get("level") == "ERROR"]
    _alembic("check")
