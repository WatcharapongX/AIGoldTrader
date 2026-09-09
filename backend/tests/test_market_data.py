import asyncio
import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.models import MarketCandle, MarketTick, Symbol, SystemEvent
from app.services.market_data.aggregation import CandleEngine
from app.services.market_data.domain import Candle, Quote, Tick, Timeframe, bucket
from app.services.market_data.provider import ReplayProvider, create_provider, price, synthetic_candle
from app.services.market_data.repository import candles_query, upsert_candles
from app.services.market_data.service import LocalMarketBus, MarketService

NOW = dt.datetime(2026, 9, 9, 12, 0, 0, tzinfo=dt.UTC)


def tick(second=0, bid="2350", ask="2350.30"):
    return Tick(symbol="XAUUSD", timestamp=NOW + dt.timedelta(seconds=second), bid=bid,
                ask=ask, volume="1", source="simulated")


@pytest.mark.parametrize("bid,ask", [("NaN", "1"), ("1", "Infinity"), ("0", "1"), ("2", "1"), ("-1", "1")])
def test_invalid_quotes_rejected(bid, ask):
    with pytest.raises(ValidationError):
        tick(bid=bid, ask=ask)


def test_quote_spread_exact():
    with pytest.raises(ValidationError):
        Quote(**tick().model_dump(), spread="0.31", status="CONNECTED")


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_utc_buckets_and_replay_history(timeframe):
    provider = ReplayProvider()
    now = NOW + dt.timedelta(minutes=17, seconds=23)
    candles = provider.get_historical_candles("XAUUSD", timeframe, now, 300)
    assert len(candles) == 300
    assert all(c.open_time.tzinfo == dt.UTC for c in candles)
    assert all(c.open_time == bucket(c.open_time, timeframe) for c in candles)
    assert candles[-1].close == price(int(now.timestamp()) - 1)
    assert all(a.open_time < b.open_time for a, b in zip(candles, candles[1:], strict=False))
    assert candles == provider.get_historical_candles("XAUUSD", timeframe, now, 300)
    if timeframe == Timeframe.W1:
        assert candles[-1].open_time.weekday() == 0


def test_aggregation_ohlc_volume_rollover_duplicates():
    engine = CandleEngine()
    engine.ingest(tick(0, "2350", "2350.30"))
    engine.ingest(tick(1, "2352", "2352.30"))
    engine.ingest(tick(2, "2349", "2349.30"))
    current = engine.current[Timeframe.M5]
    assert (current.open, current.high, current.low, current.close, current.volume) == (
        Decimal("2350"), Decimal("2352"), Decimal("2349"), Decimal("2349"), Decimal(3)
    )
    rollover = engine.ingest(tick(60))
    assert any(c.timeframe == Timeframe.M1 and c.is_closed for c in rollover)
    assert engine.current[Timeframe.M5].volume == 4
    for offset in (60, 59):
        with pytest.raises(ValueError, match="Duplicate"):
            engine.ingest(tick(offset))
    assert engine.current[Timeframe.M5].volume == 4


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_seed_then_live_matches_canonical_m1_fold(timeframe):
    now = NOW + dt.timedelta(minutes=17, seconds=23)
    engine = CandleEngine()
    start = bucket(now, Timeframe.W1)
    count = int((now - start).total_seconds() // 60) + 1
    engine.seed(ReplayProvider().get_historical_candles("XAUUSD", Timeframe.M1, now, count))
    value = price(int(now.timestamp()))
    engine.ingest(Tick(symbol="XAUUSD", timestamp=now, bid=value, ask=value + Decimal(".30"),
                       volume="1", source="simulated"))
    expected = synthetic_candle("XAUUSD", timeframe, bucket(now, timeframe), now + dt.timedelta(seconds=1))
    assert engine.current[timeframe] == expected


def test_invalid_candle_and_naive_time():
    c = synthetic_candle("XAUUSD", Timeframe.M1, NOW, NOW + dt.timedelta(seconds=60))
    with pytest.raises(ValidationError):
        Candle.model_validate({**c.model_dump(), "high": "1"})
    with pytest.raises(ValueError):
        bucket(NOW.replace(tzinfo=None), Timeframe.M1)


async def test_provider_lifecycle_and_registry():
    provider = create_provider("simulated")
    await provider.connect()
    stream = provider.subscribe_ticks("XAUUSD")
    value = await anext(stream)
    assert value.ask >= value.bid and provider.health()
    await stream.aclose()
    await provider.disconnect()
    assert not provider.health()
    with pytest.raises(ValueError):
        create_provider("live")


def test_bus_bounds_and_slow_consumer():
    bus = LocalMarketBus()
    queue = bus.subscribe()
    for _ in range(17):
        bus.publish([])
    assert queue.get_nowait() is None
    assert not bus.queues
    queues = [bus.subscribe() for _ in range(128)]
    with pytest.raises(ValueError):
        bus.subscribe()
    for queue in queues:
        bus.unsubscribe(queue)


async def test_ingestion_db_publication_quality_and_stale(db_session):
    session, factory = db_session
    symbol = Symbol(name="XAUUSD")
    session.add(symbol)
    await session.commit()
    market = MarketService(factory, Settings())
    market.symbol_id = symbol.id
    queue = market.bus.subscribe()
    assert await market.ingest(tick(), NOW)
    assert len(await asyncio.wait_for(queue.get(), 1)) == 9
    assert await session.scalar(select(func.count()).select_from(MarketTick)) == 1
    assert await session.scalar(select(func.count()).select_from(MarketCandle)) == 9
    assert not await market.ingest(tick(), NOW)
    assert not await market.ingest(tick(1, "9999", "9999.30"), NOW + dt.timedelta(seconds=1))
    assert not await market.ingest(tick(-60), NOW)
    assert await session.scalar(select(func.count()).select_from(SystemEvent)) == 3
    assert market.status(NOW + dt.timedelta(seconds=6)).status == "STALE"
    assert market.sequence == 1
    assert queue.empty()


async def test_history_pagination_upsert_is_idempotent(db_session):
    session, _ = db_session
    symbol = Symbol(name="XAUUSD")
    session.add(symbol)
    await session.flush()
    history = ReplayProvider().get_historical_candles("XAUUSD", Timeframe.M5, NOW, 20)
    await upsert_candles(session, symbol.id, history)
    await upsert_candles(session, symbol.id, history)
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(MarketCandle)) == 20
    first = await candles_query(session, symbol.id, symbol.name, Timeframe.M5, limit=10)
    second = await candles_query(session, symbol.id, symbol.name, Timeframe.M5, end=first[0].open_time, limit=10)
    assert first[0].open_time > second[-1].open_time
    assert len(first + second) == 20


def test_market_endpoints_auth_and_symbol_crud(client, auth_headers):
    assert client.get("/api/symbols").status_code == 401
    assert client.get("/api/market/candles").status_code == 401
    payload = {"name": "EURUSD", "asset_class": "FX", "digits": 5, "contract_size": "100000"}
    response = client.post("/api/symbols", headers=auth_headers, json=payload)
    assert response.status_code == 201
    assert response.json()["source_available"] is False
    assert client.get("/api/symbols", headers=auth_headers).json()[0]["name"] == "EURUSD"
    payload["digits"] = 4
    assert client.put("/api/symbols/EURUSD", headers=auth_headers, json=payload).json()["digits"] == 4
    assert client.get("/api/market/candles?symbol=EURUSD", headers=auth_headers).status_code == 404
    assert client.delete("/api/symbols/EURUSD", headers=auth_headers).status_code == 204
    assert client.get("/api/symbols/EURUSD", headers=auth_headers).status_code == 404


def test_websocket_origin_query_and_auth_rejected(client):
    from starlette.websockets import WebSocketDisconnect
    for url, origin in (("/ws/market", "https://evil.invalid"),
                        ("/ws/market?token=fixture", "http://localhost:3000")):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(url, headers={"origin": origin}):
                pass
    with client.websocket_connect("/ws/market", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_json({"type": "auth", "token": "invalid"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

def test_database_timezone_is_normalized_to_utc_contract():
    value = Tick(symbol="XAUUSD", timestamp="2026-09-09T19:00:00+07:00",
                 bid="2350", ask="2350.30", volume="1", source="simulated")
    assert value.model_dump(mode="json")["timestamp"] == "2026-09-09T12:00:00Z"
