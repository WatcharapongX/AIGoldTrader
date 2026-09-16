"""Offline MT5 contract tests use a fake official SDK, never real prices or credentials."""

import asyncio
import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.models import MarketCandle, MarketTick, Symbol
from app.services.market_data.domain import SECONDS, MarketDataStatus, Quote, Timeframe, bucket
from app.services.market_data.mt5 import MT5MarketDataProvider, MT5Unavailable, ReadOnlyMT5
from app.services.market_data.provider import ReplayProvider
from app.services.market_data.repository import candles_query, upsert_candles
from app.services.market_data.service import MarketService

NOW = dt.datetime(2026, 9, 9, 12, 4, 25, tzinfo=dt.UTC)


class FakeSDK:
    def __init__(self):
        self.calls = []
        self.account = SimpleNamespace(trade_mode=0, server="fixture-server", login=42)
        self.info = SimpleNamespace(digits=3, trade_tick_size=0.001, point=0.001)
        self.quote = SimpleNamespace(time_msc=int(NOW.timestamp() * 1000), bid=2351.123, ask=2351.456)
        self.connected = True
        self.short = False
        self.shift = 0
        self.reverse = False
        for tf in Timeframe:
            setattr(self, "TIMEFRAME_" + tf.value, tf)

    def initialize(self, *args, **kwargs):
        self.calls.append("initialize")
        return True

    def shutdown(self):
        self.calls.append("shutdown")

    def terminal_info(self):
        return SimpleNamespace(connected=self.connected)

    def account_info(self):
        return self.account

    def symbol_select(self, symbol, selected):
        self.calls.append(("symbol_select", symbol, selected))
        return symbol == "XAUUSD"

    def symbol_info(self, symbol):
        return self.info

    def symbol_info_tick(self, symbol):
        return self.quote

    def copy_rates_from(self, symbol, timeframe, now, count):
        self.calls.append(("rates", symbol, timeframe, count))
        first = bucket(now, timeframe)
        result = [
            {
                "time": int((first - dt.timedelta(seconds=SECONDS[timeframe] * i)).timestamp()) + self.shift,
                "open": 2350.111,
                "high": 2353.333,
                "low": 2349.999,
                "close": 2351.123,
                "tick_volume": 7,
            }
            for i in range((1 if self.short else count) - 1, -1, -1)
        ]
        return list(reversed(result)) if self.reverse else result


@pytest.fixture
def configured(tmp_path):
    terminal = tmp_path / "terminal64.exe"
    terminal.touch()
    settings = Settings(
        _env_file=None,
        market_data_provider="mt5",
        mt5_terminal_path=str(terminal),
        mt5_symbol_xauusd="XAUUSD",
        mt5_feed_id="fixture",
        mt5_expected_server="fixture-server",
        mt5_expected_login=42,
    )
    sdk = FakeSDK()
    return settings, sdk, MT5MarketDataProvider(settings, sdk)


@pytest.mark.parametrize("provider_name", ["replay", "mt5"])
async def test_shared_provider_contract(configured, provider_name):
    provider = ReplayProvider() if provider_name == "replay" else configured[2]
    await provider.connect()
    assert provider.health()
    for tf in Timeframe:
        history = provider.get_historical_candles("XAUUSD", tf, NOW, 300)
        assert len(history) == 300
        assert all(c.source == provider.source and c.open_time == bucket(c.open_time, tf) for c in history)
        assert all(a.open_time < b.open_time for a, b in zip(history, history[1:], strict=False))
    stream = provider.subscribe_ticks("XAUUSD")
    value = await asyncio.wait_for(anext(stream), 2)
    assert value.source == provider.source and value.ask >= value.bid
    await stream.aclose()
    await provider.disconnect()
    assert not provider.health()


async def test_official_quote_precision_and_unknown_historical_ask(configured):
    _, _, provider = configured
    assert provider.mode == "UNCONFIRMED"
    await provider.connect()
    value = provider.get_quote("XAUUSD")
    assert value.bid == Decimal("2351.123")
    assert value.ask - value.bid == Decimal("0.333")
    assert value.timestamp == NOW and value.volume == 0  # sampled quote, no invented trade volume
    assert provider.mode == "DEMO" and provider.tick_size == Decimal(".001")
    bars = provider.get_historical_candles("XAUUSD", Timeframe.M1, NOW)
    assert all(c.ask_close is None for c in bars)
    assert bars[-1].volume == 7
    await provider.disconnect()


async def test_m3_utc_fold_extrema_volume_and_partial_prefix(configured):
    _, sdk, provider = configured
    await provider.connect()
    bars = provider.get_historical_candles("XAUUSD", Timeframe.M3, NOW, 300)
    assert len(bars) == 300
    assert all(c.open_time.minute % 3 == 0 for c in bars)
    assert bars[-1].open_time == NOW.replace(minute=3, second=0)
    assert bars[-1].volume == 14 and not bars[-1].is_closed
    assert bars[-2].volume == 21 and bars[-2].is_closed
    assert bars[-1].high == Decimal("2353.333")
    assert all(call[2] == Timeframe.M1 for call in sdk.calls if isinstance(call, tuple) and call[0] == "rates")


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("mode", "ACCOUNT_MISMATCH"),
        ("server", "ACCOUNT_MISMATCH"),
        ("login", "ACCOUNT_MISMATCH"),
        ("precision", "PRECISION_UNSUPPORTED"),
        ("point", "PRECISION_UNSUPPORTED"),
        ("terminal", "SESSION_REQUIRED"),
        ("mapping", "SYMBOL_UNAVAILABLE"),
    ],
)
async def test_connect_validates_identity_and_metadata(configured, mutation, reason):
    settings, sdk, provider = configured
    if mutation == "mode":
        sdk.account.trade_mode = 2
    elif mutation == "server":
        sdk.account.server = "wrong-fixture-server"
    elif mutation == "login":
        sdk.account.login = 43
    elif mutation == "precision":
        sdk.info.digits = 6
    elif mutation == "point":
        sdk.info.point = 0.01
    elif mutation == "terminal":
        sdk.connected = False
    else:
        provider.provider_symbol = "GOLD"
    with pytest.raises(MT5Unavailable, match=reason):
        await provider.connect()
    assert not provider.health() and provider.mode == "UNCONFIRMED"
    assert settings.mt5_expected_server not in repr(settings)


@pytest.mark.parametrize("trading_mode,live", [("LIVE", False), ("PAPER", True)])
async def test_execution_guard(configured, trading_mode, live):
    settings, sdk, provider = configured
    settings.trading_mode, settings.live_auto_trading = trading_mode, live
    with pytest.raises(MT5Unavailable, match="REQUIRES_PAPER"):
        await provider.connect()
    assert sdk.calls == []


async def test_missing_prerequisites_no_silent_replay():
    provider = MT5MarketDataProvider(Settings(_env_file=None))
    with pytest.raises(MT5Unavailable, match="CONFIGURATION_REQUIRED"):
        await provider.connect()
    assert provider.source != "simulated" and provider.mode == "UNCONFIRMED"


def test_gateway_allowlist_and_error_masking():
    sdk = FakeSDK()
    gateway = ReadOnlyMT5(sdk)
    for name in ("order_send", "order_check", "positions_get", "login", "last_error"):
        with pytest.raises(MT5Unavailable, match="READ_ONLY_GUARD"):
            gateway.call(name)

    def fail(*args, **kwargs):
        raise RuntimeError("private-account-password-fixture")

    sdk.initialize = fail
    with pytest.raises(MT5Unavailable) as error:
        gateway.call("initialize")
    assert str(error.value) == "MT5_IPC_UNAVAILABLE"
    assert "private-account" not in str(error.value)


async def test_account_switch_and_disconnect_detected(configured):
    _, sdk, provider = configured
    await provider.connect()
    sdk.account.trade_mode = 2
    with pytest.raises(MT5Unavailable, match="SESSION_CHANGED"):
        provider.get_quote("XAUUSD")
    assert not provider.health()


@pytest.mark.parametrize("fault", ["duplicate_order", "boundary", "price"])
async def test_invalid_provider_history_rejected(configured, fault):
    _, sdk, provider = configured
    await provider.connect()
    if fault == "duplicate_order":
        sdk.reverse = True
    elif fault == "boundary":
        sdk.shift = -1
    else:
        sdk.info.digits = 2
        provider.digits = 2
    with pytest.raises(MT5Unavailable):
        provider.get_historical_candles("XAUUSD", Timeframe.M5, NOW)


async def test_authoritative_candles_replace_not_add_volume(configured):
    _, _, provider = configured
    await provider.connect()
    first = await provider.candle_updates(NOW)
    second = await provider.candle_updates(NOW)
    assert first == second and len(first) == 18
    assert {c.timeframe for c in first} == set(Timeframe)
    assert max(c.high for c in first) > provider.get_quote("XAUUSD").bid


async def test_service_real_persistence_and_source_isolation(configured, db_session):
    settings, _, provider = configured
    session, factory = db_session
    market = MarketService(factory, settings)
    market.provider = provider
    await market.initialize()
    symbol = await session.scalar(select(Symbol).where(Symbol.name == "XAUUSD"))
    replay = ReplayProvider().get_historical_candles("XAUUSD", Timeframe.M5, NOW)
    await upsert_candles(session, symbol.id, replay)
    await session.commit()
    queue = market.bus.subscribe()
    assert await market.ingest(provider.get_quote("XAUUSD"), NOW)
    assert len(await queue.get()) == 18
    # Real ticks do not accumulate without an explicit operator archival policy.
    assert await session.scalar(select(func.count()).select_from(MarketTick)) == 0
    real = await candles_query(session, symbol.id, "XAUUSD", Timeframe.M5, source=provider.source)
    fake = await candles_query(session, symbol.id, "XAUUSD", Timeframe.M5)
    assert len(real) == len(fake) == 300
    assert all(c.source == provider.source and c.ask_close is None for c in real)
    assert all(c.source == "simulated" for c in fake)
    assert market.status(NOW).mode == "DEMO" and market.status(NOW).digits == 3
    assert market.status(NOW + dt.timedelta(seconds=6)).status == "STALE"
    assert market.status(NOW + dt.timedelta(seconds=6)).market_state == "UNKNOWN"
    wrong = provider.get_quote("XAUUSD").model_copy(update={"source": "simulated"})
    assert not await market.ingest(wrong, NOW)
    assert market.sequence == 1
    assert await session.scalar(select(func.count()).select_from(MarketCandle)) >= 300 * 9
    await market.stop()


async def test_authoritative_gap_requests_controlled_resnapshot(configured):
    from unittest.mock import AsyncMock

    settings, _, provider = configured
    market = MarketService(None, settings)
    await provider.connect()
    market.provider = provider
    current = dt.datetime.now(dt.UTC)
    first = provider.get_quote("XAUUSD").model_copy(update={"timestamp": current - dt.timedelta(seconds=6)})
    market.quote = Quote(**first.model_dump(), spread=first.ask - first.bid, status="CONNECTED", mode=provider.mode)
    gap = first.model_copy(update={"timestamp": current})

    async def ticks():
        yield gap

    provider.subscribe_ticks = lambda _symbol: ticks()
    market.initialize = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    market.event = AsyncMock()
    provider.disconnect = AsyncMock()
    queue = market.bus.subscribe()

    with pytest.raises(asyncio.CancelledError):
        await market.run()

    assert market.state == "STALE"
    assert market.detail == "Provider gap detected; rebuilding authoritative history"
    assert queue.get_nowait() is None
    market.event.assert_awaited_once_with("MARKET_RESNAPSHOT_REQUIRED")
    provider.disconnect.assert_awaited_once()
    assert market.initialize.await_count == 2


async def test_short_history_blocks_bootstrap_atomically(configured, db_session):
    settings, sdk, provider = configured
    session, factory = db_session
    sdk.short = True
    market = MarketService(factory, settings)
    market.provider = provider
    with pytest.raises(ValueError, match="Insufficient provider history"):
        await market.initialize()
    assert await session.scalar(select(func.count()).select_from(MarketCandle)) == 0
    assert market.quote is None


def test_mode_cannot_mislabel_simulation():
    with pytest.raises(ValidationError):
        MarketDataStatus(
            source="simulated",
            mode="DEMO",
            status="CONNECTED",
            last_quote=NOW,
            server_time=NOW,
            stale_after_seconds=5,
            detail="fixture",
            subscriptions=0,
        )


async def test_provider_failure_retries_bounded_and_masks_logs(configured, monkeypatch, caplog):
    from unittest.mock import AsyncMock

    settings, _, provider = configured
    market = MarketService(None, settings)
    market.provider = provider

    async def fail_connect():
        raise RuntimeError("sensitive-fixture-password-server")

    provider.connect = fail_connect
    market.event = AsyncMock()
    delays = []

    async def sleep(seconds):
        delays.append(seconds)
        if len(delays) == 7:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await market.run()
    assert delays == [1, 2, 4, 8, 16, 30, 30]
    assert market.status().status == "ERROR" and market.status().mode == "UNCONFIRMED"
    assert market.provider.source != "simulated"
    assert "sensitive-fixture" not in caplog.text


async def test_rest_and_first_frame_ws_use_selected_source(configured, db_session, client, auth_headers):
    from unittest.mock import AsyncMock

    settings, _, provider = configured
    session, factory = db_session
    market = MarketService(factory, settings)
    market.provider = provider
    await market.initialize()
    market.start = AsyncMock()  # Read-only snapshot test; fixture is explicitly OFFLINE.
    client.app.state.market = market
    symbol = await session.scalar(select(Symbol).where(Symbol.name == "XAUUSD"))
    await upsert_candles(session, symbol.id, ReplayProvider().get_historical_candles("XAUUSD", Timeframe.M5, NOW))
    await session.commit()
    page = client.get("/api/market/candles?timeframe=M5", headers=auth_headers).json()
    assert len(page["candles"]) == 300
    assert all(c["source"] == provider.source and c["ask_close"] is None for c in page["candles"])
    with client.websocket_connect("/ws/market", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_json({"type": "auth", "token": auth_headers["Authorization"].split()[1]})
        ws.send_json({"type": "subscribe", "symbol": "XAUUSD", "timeframe": "M5"})
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot" and snapshot["status"]["mode"] == "DEMO"
        assert len(snapshot["candles"]) == 300
        assert all(c["source"] == provider.source for c in snapshot["candles"])
        rendered = str(snapshot)
        assert settings.mt5_expected_server not in rendered
        assert settings.mt5_terminal_path not in rendered
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").json()["live_auto_trading"] is False


def test_explicit_broker_timezone_dst_and_ambiguity(configured):
    settings, sdk, _ = configured
    settings.mt5_server_timezone = "Europe/London"
    provider = MT5MarketDataProvider(settings, sdk)
    for wall, expected in [
        ("2026-09-09T08:00:00", "2026-09-09T07:00:00+00:00"),
        ("2026-01-09T08:00:00", "2026-01-09T08:00:00+00:00"),
    ]:
        raw = dt.datetime.fromisoformat(wall).replace(tzinfo=dt.UTC).timestamp()
        assert provider._utc(raw).isoformat() == expected
    for wall in ("2026-10-25T01:30:00", "2026-03-29T01:30:00"):
        raw = dt.datetime.fromisoformat(wall).replace(tzinfo=dt.UTC).timestamp()
        with pytest.raises(MT5Unavailable, match="AMBIGUOUS_OR_NONEXISTENT"):
            provider._utc(raw)


async def test_weekly_is_monday_utc_aggregation_not_broker_sunday(configured):
    _, sdk, provider = configured
    await provider.connect()
    bars = provider.get_historical_candles("XAUUSD", Timeframe.W1, NOW, 3)
    assert len(bars) == 3 and all(c.open_time.weekday() == 0 for c in bars)
    assert all(c.open_time.hour == 0 for c in bars)
    assert all(call[2] == Timeframe.H1 for call in sdk.calls if isinstance(call, tuple) and call[0] == "rates")
