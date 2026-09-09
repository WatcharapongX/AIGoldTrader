"""Golden macro fixtures, causal event replay and actual input-boundary checks."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.analysis.domain import AnalysisResponse
from app.services.analysis.engine import analyze
from app.services.analysis.service import AnalysisService
from app.services.market_data.domain import Candle, Timeframe
from app.services.news.domain import EconomicEvent, NewsConfig, NewsResponse, ObservedQuote
from app.services.news.engine import build_context, latest_known, surprise
from app.services.news.provider import (
    CATALOG,
    EconomicCalendarReplayProvider,
    fixture_release,
    normalize_number,
)
from app.services.news.repository import event_vintages, revisions, store_events

AT = dt.datetime(2026, 9, 9, 12, 30, tzinfo=dt.UTC)
SOURCE = "fixture_economic_v1"
CONFIG = NewsConfig()


def context(seconds=0, events=None, **kwargs):
    values = dict(
        events=fixture_release(AT, "mixed") if events is None else events,
        as_of=AT + dt.timedelta(seconds=seconds),
        source=SOURCE,
        mode="FIXTURE",
        config=CONFIG,
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    values.update(kwargs)
    return build_context(**values)


def bars(kind="strong"):
    result = []
    for minute in range(-30, 16):
        close = Decimal(100) if minute < 0 or kind == "muted" else Decimal(106)
        high, low = (Decimal(101), Decimal(99)) if minute < 0 or kind == "muted" else (Decimal(107), Decimal(100))
        if minute >= 0 and kind == "whipsaw":
            high, low, close = Decimal(107), Decimal(93), Decimal(100)
        result.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.M1,
                source="simulated",
                open_time=AT + dt.timedelta(minutes=minute),
                open=Decimal(100) if minute < 1 else close,
                high=high,
                low=low,
                close=close,
                bid_close=close,
                ask_close=None,
                volume=Decimal(10),
                is_closed=True,
            )
        )
    return result


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (-1801, "NORMAL"),
        (-1800, "PRE_NEWS"),
        (-301, "PRE_NEWS"),
        (-300, "NEWS_LOCK"),
        (-60, "NEWS_LOCK"),
        (0, "RELEASE"),
        (5, "RELEASE"),
        (60, "POST_NEWS_VOLATILITY"),
        (299, "POST_NEWS_VOLATILITY"),
        (300, "POST_NEWS_CONFIRMATION"),
        (899, "POST_NEWS_CONFIRMATION"),
        (900, "NORMALIZED"),
        (1800, "NORMAL"),
    ],
)
def test_golden_timeline(seconds, expected):
    assert context(seconds).news_regime == expected


@pytest.mark.parametrize("seconds", [-1800, -300, -60, 0, 5, 60, 300, 900])
def test_batch_incremental_prefix_has_identical_fingerprint(seconds):
    cutoff = AT + dt.timedelta(seconds=seconds)
    all_events = fixture_release(AT, "mixed")
    prefix = [e for e in all_events if e.available_at <= cutoff]
    assert context(seconds, all_events) == context(seconds, prefix)
    assert (
        context(seconds, all_events, candles=bars()).fingerprint
        == context(
            seconds, prefix, candles=[c for c in bars() if c.open_time + dt.timedelta(minutes=1) <= cutoff]
        ).fingerprint
    )


def test_actual_and_negative_revision_visible_only_when_available():
    before = context(5)
    assert all(e.actual is None for e in before.events)
    released = context(20)
    assert all(e.revision_version == 2 and e.revised_previous is None for e in released.events)
    revised = context(601)
    nfp = next(e for e in revised.events if e.event_code == "NFP")
    assert nfp.revised_previous == 100 and nfp.previous == 165
    assert revised.active_group.alignment == "CONFLICTING"
    assert revised.macro_bias == "CONFLICTING"


@pytest.mark.parametrize(
    "variant,bias", [("positive", "USD_STRONG_POSITIVE"), ("negative", "USD_STRONG_NEGATIVE"), ("mixed", "CONFLICTING")]
)
def test_nfp_group_direction(variant, bias):
    assert context(20, fixture_release(AT, variant)).macro_bias == bias


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        ("250K", "THOUSANDS", "250"),
        ("1.2M", "THOUSANDS", "1200"),
        ("4.2%", "PERCENT", "4.2"),
        ("-0.3", "NUMBER", "-0.3"),
        ("1,200", "NUMBER", "1200"),
        ("-", "NUMBER", None),
        ("N/A", "NUMBER", None),
    ],
)
def test_provider_number_units(value, unit, expected):
    assert normalize_number(value, unit) == (None if expected is None else Decimal(expected))


@pytest.mark.parametrize(
    "value,unit", [("NaN", "NUMBER"), ("Infinity", "NUMBER"), ("2M", "PERCENT"), ("4%", "THOUSANDS")]
)
def test_bad_numbers_rejected(value, unit):
    with pytest.raises(ValueError):
        normalize_number(value, unit)


def test_zero_negative_forecast_and_missing_without_fake_zscore():
    e = latest_known(fixture_release(AT), AT + dt.timedelta(seconds=20))[0]
    for actual, forecast, raw, relative in [(1, 0, 1, None), (0, 0, 0, None), (-1, -2, 1, Decimal(".5"))]:
        value = surprise(e.model_copy(update={"actual": Decimal(actual), "forecast": Decimal(forecast)}), CONFIG)
        assert value.raw == raw and value.relative == relative and value.normalized is None
    assert surprise(e.model_copy(update={"forecast": None}), CONFIG).raw is None


@pytest.mark.parametrize("actual", [Decimal(".4"), Decimal(".1")])
def test_cpi_context_dependent_and_configurable_rule(actual):
    e = latest_known(fixture_release(AT), AT + dt.timedelta(seconds=20))[0]
    e = e.model_copy(
        update={
            "event_code": "CPI",
            "unit": "PERCENT",
            "actual": actual,
            "forecast": Decimal(".3"),
            "direction_rule": "CONTEXT_DEPENDENT",
        }
    )
    assert surprise(e, CONFIG).usd_direction == "UNKNOWN"
    expected = "POSITIVE" if actual > Decimal(".3") else "NEGATIVE"
    assert surprise(e, NewsConfig(direction_overrides={"CPI": "HIGHER_IS_POSITIVE"})).usd_direction == expected


def test_delayed_cancelled_nonnumeric_and_cluster_do_not_reset_risk():
    e = fixture_release(AT)[0]
    delayed = e.model_copy(update={"status": "DELAYED"})
    assert context(7200, [delayed]).news_regime == "NEWS_LOCK"
    assert context(0, [e.model_copy(update={"status": "CANCELLED"})]).news_regime == "NORMAL"
    fomc = e.model_copy(
        update={
            "unit": "NON_NUMERIC",
            "event_code": "FED_PRESS",
            "forecast": None,
            "previous": None,
            "status": "RELEASED",
            "released_at": AT,
            "available_at": AT,
            "updated_at": AT,
            "direction_rule": "CONTEXT_DEPENDENT",
        }
    )
    assert context(300, [fomc]).macro_bias == "UNKNOWN"
    later = fixture_release(AT + dt.timedelta(minutes=20))
    cluster = context(900, fixture_release(AT) + later)
    assert cluster.news_regime == "NEWS_LOCK" and cluster.multiple_event_risk


@pytest.mark.parametrize(
    "kind,expected", [("strong", "STRONG_DIRECTIONAL"), ("whipsaw", "WHIPSAW"), ("muted", "MUTED")]
)
def test_reaction_uses_only_closed_complete_m1(kind, expected):
    value = context(300, candles=bars(kind))
    assert value.reaction_state == expected
    assert value.reaction_windows[0].price_before == 100
    assert value.spread_ratio is None
    assert context(5, candles=bars(kind)).reaction_windows[0].status == "WAITING"
    missing = [c for c in bars(kind) if c.open_time != AT]
    assert context(300, candles=missing).reaction_state == "REACTION_UNAVAILABLE"
    subminute = context(30, candles=bars(kind), config=NewsConfig(reaction_seconds=[5, 15, 30, 60]))
    assert all(w.status == "REACTION_UNAVAILABLE" for w in subminute.reaction_windows[:3])


def test_future_and_late_observed_spread_does_not_leak():
    quotes = [
        ObservedQuote(
            timestamp=AT + dt.timedelta(seconds=s),
            observed_at=AT + dt.timedelta(seconds=s),
            bid=Decimal(100),
            ask=Decimal("100.2"),
            source="simulated",
        )
        for s in [-30, -20, -10, 300]
    ]
    fresh = quotes[-1].model_copy(update={"ask": Decimal(101)})
    value = context(300, quotes=quotes[:-1] + [fresh])
    assert value.spread_ratio == 5 and value.trade_policy_state == "RESTRICTED"
    late = fresh.model_copy(update={"observed_at": AT + dt.timedelta(seconds=301)})
    assert context(300, quotes=quotes[:-1] + [late]).spread_ratio is None


def test_structure_future_and_operational_timestamps_not_in_fingerprint():
    candles = bars()
    snapshot = analyze(candles, "XAUUSD", Timeframe.M1, "simulated")
    base = context(300)
    assert context(300, structure=snapshot).fingerprint == base.fingerprint
    past = analyze([c for c in candles if c.open_time < AT], "XAUUSD", Timeframe.M1, "simulated")
    envelope = AnalysisResponse(**past.model_dump(), generated_at=AT, served_at=AT, cache_age_seconds=0)
    assert context(300, structure=past).fingerprint == context(300, structure=envelope).fingerprint
    assert context(300, structure=past).structure_confirmation.absence_means == "NOT_INCLUDED_UNKNOWN"


def test_empty_calendar_and_provider_unavailable_are_explicit():
    assert context(0, events=[]).news_regime == "NORMAL"
    value = context(0, calendar_available=False)
    assert value.news_regime == "UNKNOWN" and value.trade_policy_state == "RESTRICTED"
    assert value.strategy_eligibility["TREND_CONTINUATION"] == "CAUTION"
    assert value.strategy_eligibility["MEAN_REVERSION"] == "CAUTION"
    assert value.strategy_eligibility["BREAKOUT"] == "CAUTION"
    assert value.strategy_eligibility["NEWS_MOMENTUM"] == "WAITING"
    assert context(0, view="none").events == []


def test_fingerprint_config_revision_source_and_clock_boundaries():
    value = context(300)
    assert context(300, config=NewsConfig(relative_large=Decimal(".3"))).fingerprint != value.fingerprint
    assert context(301).fingerprint != value.fingerprint
    assert context(300, source="another_source").fingerprint != value.fingerprint
    assert "generated_at" not in value.model_dump()
    for field in ("entry", "stop_loss", "take_profit", "signal", "order"):
        assert field not in value.model_dump()


@pytest.mark.parametrize(
    "config",
    [
        {"reaction_seconds": [30, 5]},
        {"pre_seconds": {"HIGH": 100}},
        {"spread_elevated": "5", "spread_extreme": "4"},
        {"observation_seconds": 900, "confirmation_seconds": 300},
        {"weights": {"NFP": -1}},
    ],
)
def test_invalid_config(config):
    with pytest.raises(ValidationError):
        NewsConfig.model_validate(config)


async def test_append_revision_dedupe_reschedule_point_in_time(db_session):
    session, _ = db_session
    values = fixture_release(AT, "mixed")
    assert await store_events(session, values) == 9
    assert await store_events(session, values) == 0
    early = await event_vintages(session, SOURCE, AT)
    assert len(early) == 3 and all(e.actual is None for e in early)
    first = values[0]
    shifted = first.model_copy(
        update={
            "scheduled_at": AT + dt.timedelta(days=2),
            "revision_version": 4,
            "updated_at": AT + dt.timedelta(minutes=30),
            "available_at": AT + dt.timedelta(minutes=30),
        }
    )
    assert shifted.id == first.id
    await store_events(session, [shifted])
    selected = await event_vintages(session, SOURCE, AT + dt.timedelta(hours=1))
    assert next(e for e in selected if e.id == first.id).scheduled_at == AT + dt.timedelta(days=2)
    assert len(await revisions(session, SOURCE, first.id, AT + dt.timedelta(minutes=20))) == 3
    with pytest.raises(ValueError):
        await store_events(session, [first.model_copy(update={"forecast": Decimal(999)})])
    with pytest.raises(ValueError):
        await store_events(session, [first.model_copy(update={"id": "wrong-identity"})])


async def test_replay_provider_is_bounded_and_never_returns_future_actual():
    provider = EconomicCalendarReplayProvider()
    events = await provider.fetch(AT - dt.timedelta(hours=1), AT + dt.timedelta(hours=2), AT)
    assert events and all(e.available_at <= AT for e in events)
    assert len(CATALOG) == 18
    with pytest.raises(ValueError):
        await provider.fetch(AT, AT + dt.timedelta(days=8), AT)


async def test_qrev_operational_envelope_preserves_determinism():
    service = AnalysisService()
    candles = bars()
    a = await service.response(candles, "XAUUSD", Timeframe.M1, "simulated")
    b = await service.response(candles, "XAUUSD", Timeframe.M1, "simulated")
    assert a.input_id == b.input_id and a.generated_at == b.generated_at
    assert b.served_at >= a.served_at and b.cache_age_seconds >= a.cache_age_seconds
    assert not a.retention.absence_is_invalidation and a.retention.absence_means == "NOT_INCLUDED_UNKNOWN"


def test_export_browser_fixture():
    value = context(601, candles=bars("whipsaw"))
    response = NewsResponse(
        **value.model_dump(),
        generated_at=AT + dt.timedelta(minutes=20),
        served_at=AT + dt.timedelta(minutes=20),
        cache_age_seconds=0,
    )
    path = Path(__file__).parents[2] / "frontend/tests/fixtures/news.json"
    # Checked fixture is maintained deliberately, never silently regenerated by tests.
    if path.exists():
        expected = NewsResponse.model_validate_json(path.read_text(encoding="utf-8"))
        assert expected == response


@pytest.mark.parametrize("path", ["/api/news/context", "/api/calendar/economic", "/api/news/events/unknown"])
def test_news_endpoints_require_login(client, path):
    assert client.get(path).status_code == 401


async def test_news_worker_is_single_and_backoff_is_bounded(db_session):
    import asyncio
    import time
    from types import SimpleNamespace

    from app.core.config import Settings
    from app.services.news.service import NewsService

    _, factory = db_session
    service = NewsService(
        factory, Settings(_env_file=None, news_calendar_provider="unavailable"), SimpleNamespace(quote=None)
    )
    await asyncio.gather(service.start(), service.start(), service.start())
    original = service.task
    assert original is not None and not service.available and service.failures == 1
    assert 0 < service.next_poll - time.monotonic() <= 300
    await service.start()
    assert service.task is original and service.failures == 1
    await service.stop()
    assert service.task is None


def test_nonnumeric_future_release_status_and_invented_actual_rejected():
    original = fixture_release(AT)[0]
    for updates in (
        {"status": "RELEASED"},
        {"status": "RELEASED", "released_at": AT + dt.timedelta(days=1)},
        {"unit": "NON_NUMERIC"},
    ):
        with pytest.raises(ValidationError):
            EconomicEvent.model_validate(original.model_copy(update=updates).model_dump())


def test_currency_channel_and_impact_relevance_are_configurable():
    value = context(20)
    assert all(r.score == 3 and r.channels == ["USD", "INTEREST_RATES"] for r in value.xauusd_relevance.values())
    changed = context(20, config=NewsConfig(relevance={"USD": 1}))
    assert changed.news_regime == "NORMAL" and all(r.score == 1 for r in changed.xauusd_relevance.values())


@pytest.mark.parametrize(
    "case,expected",
    [
        ("breakout", "BREAKOUT"),
        ("failed", "FAILED_BREAKOUT"),
        ("sweep", "LIQUIDITY_SWEEP_REVERSAL"),
        ("future", "STRONG_DIRECTIONAL"),
    ],
)
def test_reaction_structure_confirmation_goldens(case, expected):
    from app.services.analysis.domain import LiquidityLevel, StructureEvent

    source = bars()
    source = [c for c in source if c.open_time < AT + dt.timedelta(minutes=5)]
    snapshot = analyze(source, "XAUUSD", Timeframe.M1, "simulated")
    event = StructureEvent(
        id="confirmed-break",
        scope="EXTERNAL",
        kind="BOS",
        direction="BEARISH" if case == "failed" else "BULLISH",
        price=Decimal(101),
        swing_id="prior-high",
        swing_time=AT - dt.timedelta(minutes=5),
        occurred_at=AT,
        confirmed_at=AT + dt.timedelta(seconds=600 if case == "future" else 60),
        displacement=True,
    )
    level = LiquidityLevel(
        id="swept-low",
        kind="SSL",
        side="LOW",
        price=Decimal(99),
        created_at=AT - dt.timedelta(minutes=5),
        confirmed_at=AT - dt.timedelta(minutes=3),
        source_ids=["prior-low"],
        status="SWEPT",
        swept_at=AT + dt.timedelta(seconds=60),
        sweep_price=Decimal(98),
        ended_at=AT + dt.timedelta(seconds=60),
    )
    snapshot = snapshot.model_copy(
        update={"events": [] if case == "sweep" else [event], "liquidity": [level] if case == "sweep" else []}
    )
    if case == "future":
        with pytest.raises(ValueError, match="Future lifecycle"):
            context(300, candles=source, structure=snapshot)
    else:
        assert context(300, candles=source, structure=snapshot).reaction_state == expected


async def test_bounded_revision_detail_keeps_latest_vintage(db_session):
    session, _ = db_session
    first = fixture_release(AT)[0]
    values = [
        first.model_copy(
            update={
                "revision_version": version,
                "available_at": first.available_at + dt.timedelta(seconds=version),
                "updated_at": first.updated_at + dt.timedelta(seconds=version),
            }
        )
        for version in range(1, 102)
    ]
    await store_events(session, values)
    history = await revisions(session, SOURCE, first.id, AT)
    assert len(history) == 100 and history[0].revision_version == 2 and history[-1].revision_version == 101
