"""Explicit real MT5 acceptance: LIVE_EXTERNAL_TEST=true pytest -m live_external -o addopts= -q."""

import asyncio
import datetime as dt
import os

import pytest

from app.core.config import Settings
from app.services.market_data.domain import Timeframe
from app.services.market_data.mt5 import MT5MarketDataProvider

pytestmark = pytest.mark.live_external


def real_provider():
    if os.environ.get("LIVE_EXTERNAL_TEST") != "true":
        pytest.fail("BLOCKED BY REAL DATA PROVIDER PREREQUISITE: explicit opt-in required", pytrace=False)
    settings = Settings()
    if settings.market_data_provider != "mt5":
        pytest.fail("BLOCKED BY REAL DATA PROVIDER PREREQUISITE: MARKET_DATA_PROVIDER=mt5 required", pytrace=False)
    return MT5MarketDataProvider(settings)


@pytest.mark.parametrize("timeframe", list(Timeframe))
async def test_real_mt5_history_300(timeframe):
    provider = real_provider()
    try:
        await provider.connect()
        bars = await asyncio.to_thread(
            provider.get_historical_candles, "XAUUSD", timeframe, dt.datetime.now(dt.UTC), 300
        )
        assert len(bars) == 300, f"INSUFFICIENT REAL HISTORY: {timeframe.value} has {len(bars)}/300 bars"
        assert all(c.source == provider.source and c.source != "simulated" for c in bars)
    finally:
        await provider.disconnect()


async def test_real_mt5_quotes_disconnect_and_reconnect():
    provider = real_provider()
    try:
        for _ in range(2):
            await provider.connect()
            assert provider.health() and provider.mode in ("DEMO", "LIVE")
            stream = provider.subscribe_ticks("XAUUSD")
            try:
                first = await asyncio.wait_for(anext(stream), 30)
                second = await asyncio.wait_for(anext(stream), 30)
                assert second.timestamp > first.timestamp
                age = (dt.datetime.now(dt.UTC) - second.timestamp).total_seconds()
                assert -provider.settings.mt5_future_tolerance_seconds <= age <= provider.settings.market_stale_seconds
                assert first.ask >= first.bid and second.ask >= second.bid
            finally:
                await stream.aclose()
            await provider.disconnect()
            assert not provider.health()
    finally:
        await provider.disconnect()
