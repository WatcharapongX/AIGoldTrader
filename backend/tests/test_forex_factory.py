"""Targeted FF acceptance: real-shaped feed, causality, cache and general invariance."""

import datetime as dt
from decimal import Decimal as D

import httpx
import pytest

from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as news_context
from app.services.news.engine import latest_known, release_group
from app.services.news.forex_factory import SOURCE, URL, ForexFactoryCalendarProvider, normalize
from app.services.news.public_calendar import RateLimited
from app.services.strategy.domain import fingerprint
from app.services.strategy.engine import REGISTRY, EvaluationCache, evaluate, profiles
from app.services.strategy.lifecycle import transition
from tests.test_strategy import CONFIG, qualified_context

T = dt.datetime(2026, 9, 10, 12, 30, tzinfo=dt.UTC)


def row(title="Unemployment Claims", **changes):
    return dict(
        title=title, country="USD", date=T.isoformat(), impact="High", forecast="205K", previous="206K", **changes
    )


def build(events, at, available=True):
    return news_context(
        events,
        at,
        source=SOURCE,
        mode="LIVE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        calendar_available=available,
    )


def test_exact_units_groups_and_dst():
    summer = normalize([row()], T - dt.timedelta(hours=1))[0]
    assert summer.forecast == 205 and summer.previous == 206 and summer.actual is None
    assert summer.field_provenance["forecast"] == SOURCE and "actual" not in summer.field_provenance
    for date, hour in (("2026-01-09T08:30:00-05:00", 13), ("2026-07-09T08:30:00-04:00", 12)):
        raw = row()
        raw["date"] = date
        event = normalize([raw], T)[0]
        assert event.scheduled_at.hour == hour
        from zoneinfo import ZoneInfo

        assert event.scheduled_at.astimezone(ZoneInfo("Asia/Bangkok")).hour == hour + 7


@pytest.mark.parametrize("impact", ["High", "Medium", "Low", "Holiday", "Non-Economic", "Unknown", "unexpected"])
def test_impact_normalization_not_colors(impact):
    raw = row()
    raw["impact"] = impact
    event = normalize([raw], T)[0]
    assert event.impact in {"HIGH", "MEDIUM", "LOW", "HOLIDAY", "NON_ECONOMIC", "UNKNOWN"}
    build([event], T)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "abc", "999B"])
def test_bad_values_fail_closed(value):
    raw = row()
    raw["forecast"] = value
    with pytest.raises(ValueError):
        normalize([raw], T)


def test_identity_unchanged_for_value_and_within_week_schedule_revision():
    first = normalize([row()], T)[0]
    raw = row()
    raw.update(forecast="210K", date=(T + dt.timedelta(hours=1)).isoformat())
    second = normalize([raw], T)[0]
    assert first.id == second.id and first.group_id == second.group_id
    with pytest.raises(ValueError):
        normalize([row(), row()], T)
    raw["date"] = "2026-09-10T08:30:00"
    with pytest.raises(ValueError):
        normalize([raw], T)


def test_no_unsupported_title_alias_or_future_actual():
    raw = row("ADP Weekly Employment Change")
    with pytest.raises(ValueError):
        normalize([raw], T)
    with pytest.raises(ValueError):
        normalize([row(actual="220K")], T - dt.timedelta(seconds=1))


@pytest.mark.parametrize("minute", [-30, -5, -1, 0, 1, 5])
def test_timeline_future_actual_revision_excluded_and_incremental_equal(minute):
    initial = normalize([row()], T - dt.timedelta(hours=1))[0]
    released = normalize([row(actual="200K")], T + dt.timedelta(minutes=1))[0].model_copy(
        update={"revision_version": 2}
    )
    revised = normalize([row(actual="198K")], T + dt.timedelta(minutes=5))[0].model_copy(update={"revision_version": 3})
    all_events = [initial, released, revised]
    at = T + dt.timedelta(minutes=minute)
    batch = build(all_events, at)
    incremental = build([e for e in all_events if e.available_at <= at], at)
    assert batch == incremental
    known = latest_known(all_events, at)[0]
    assert known.actual == (None if minute < 1 else D(200) if minute < 5 else D(198))
    assert not any(e.available_at > at for e in batch.events)
    if minute == 0:
        assert batch.release_status == "WAITING_FOR_ACTUAL"
    if minute < 0:
        assert batch.release_status == "PRE_NEWS"
    # Values alone never make an eligible setup.
    assert batch.strategy_eligibility["NEWS_MOMENTUM"] == "WAITING"


def test_cpi_components_not_double_counted_and_nfp_completeness():
    cpi = []
    for title in ("CPI m/m", "CPI y/y", "Core CPI m/m", "Core CPI y/y"):
        raw = row(title, actual="0.4%")
        raw.update(forecast="0.2%", previous="0.1%")
        cpi += normalize([raw], T)
    config = NewsConfig(direction_overrides={e.event_code: "HIGHER_IS_POSITIVE" for e in cpi})
    assert release_group(cpi, config).score == 1
    assert release_group(cpi[:1], config).completeness == "PARTIAL"
    assert release_group(cpi, config).completeness == "COMPLETE"
    nfp = normalize([row("Non-Farm Employment Change", actual="220K")], T)
    assert release_group(nfp, config).completeness == "PARTIAL"


def test_speech_has_no_fake_surprise_or_forecast_requirement():
    raw = row("Fed Chair Powell Speaks")
    raw.update(forecast="", previous="")
    event = normalize([raw], T)[0]
    group = release_group([event], NewsConfig())
    assert group.completeness == "COMPLETE"
    assert group.surprises[0].reason_code == "NON_NUMERIC_EVENT"
    assert build([event], T).release_status == "WAITING_FOR_RELEASE"


@pytest.mark.parametrize("strategy_id", ["STRAT01", "STRAT02", "STRAT03", "STRAT04"])
@pytest.mark.parametrize(
    "scenario", ["healthy", "unavailable", "unknown", "upcoming", "released", "forecast_conflict", "actual_conflict"]
)
def test_general_full_invariance_and_no_lifecycle_churn(strategy_id, scenario):
    ctx = qualified_context(strategy_id)
    profile = profiles(CONFIG, ctx.config_id)[1].model_copy(update={"allowed_strategies": (strategy_id,)})
    original = REGISTRY[strategy_id].evaluate(ctx, profile, CONFIG)
    assert original.status == "READY" and original.plan
    data = ctx.news.model_dump()
    data["fingerprint"] = fingerprint(scenario)
    if scenario == "unavailable":
        data.update(calendar_state="CALENDAR_UNAVAILABLE", trade_policy_state="RESTRICTED", data_quality="UNAVAILABLE")
    elif scenario == "unknown":
        data.update(news_regime="UNKNOWN", macro_bias="UNKNOWN", data_quality="UNAVAILABLE")
    elif scenario == "upcoming":
        data.update(news_regime="PRE_NEWS", release_status="PRE_NEWS", trade_policy_state="CAUTION")
        for e in data["events"]:
            e.update(
                scheduled_at=ctx.as_of + dt.timedelta(minutes=5), actual=None, released_at=None, status="SCHEDULED"
            )
    elif scenario == "released":
        data["events"][0]["actual"] = D(999)
        data.update(macro_bias="USD_STRONG_POSITIVE")
    elif scenario in ("forecast_conflict", "actual_conflict"):
        field = "forecast" if scenario == "forecast_conflict" else "actual"
        data["events"][0]["field_conflicts"] = (field,)
        data.update(data_quality="CONFLICT", macro_bias="CONFLICTING", trade_policy_state="RESTRICTED")
    # Calendar annotations cannot substitute for real market safety.
    if scenario in ("unknown", "actual_conflict"):
        data.update(spread_state="SPREAD_EXTREME", volatility_state="EXTREME")
    n = ctx.news.model_validate(data)
    changed = ctx.model_copy(
        update={
            "id": fingerprint([ctx.id, scenario]),
            "news_json": n.model_dump_json(),
            "news_fingerprint": n.fingerprint,
        }
    )
    other = REGISTRY[strategy_id].evaluate(changed, profile, CONFIG)
    assert original == other  # Includes plan, score, evidence, direction, status, all identities.
    assert transition(original, changed, other) is None
    cache = EvaluationCache()
    first = evaluate(ctx, CONFIG, (profile,), cache=cache)
    count = len(cache.values)
    second = evaluate(changed, CONFIG, (profile,), cache=cache)
    assert first.candidates == second.candidates and len(cache.values) == count


@pytest.mark.parametrize("strategy_id", ["STRAT05", "STRAT06"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("calendar_state", "CALENDAR_UNAVAILABLE"),
        ("release_status", "WAITING_FOR_ACTUAL"),
        ("data_quality", "CONFLICT"),
        ("data_quality", "PARTIAL"),
        ("reaction_state", "MUTED"),
        ("spread_state", "SPREAD_EXTREME"),
    ],
)
def test_news_strategies_sensitive_only_after_complete_release(strategy_id, field, value):
    ctx = qualified_context(strategy_id)
    p = profiles(CONFIG, ctx.config_id)[1].model_copy(update={"allowed_strategies": (strategy_id,)})
    good = REGISTRY[strategy_id].evaluate(ctx, p, CONFIG)
    assert good.status == "READY"
    assert good.news_provenance and good.news_provenance.event_vintages
    assert good.news_provenance.context_fingerprint == ctx.news_fingerprint
    assert good.news_provenance.phase3_input_ids == tuple(f.input_id for f in ctx.frames)
    changed = ctx.model_copy(update={"news_json": ctx.news.model_copy(update={field: value}).model_dump_json()})
    result = REGISTRY[strategy_id].evaluate(changed, p, CONFIG)
    assert result.status != "READY" and result.plan is None


@pytest.mark.asyncio
async def test_transport_fixed_url_no_redirect_and_json_only():
    raw = row()
    raw["date"] = dt.datetime.now(dt.UTC).isoformat()

    async def handler(request):
        assert str(request.url) == URL and request.url.query == b""
        return httpx.Response(200, json=[raw])

    provider = ForexFactoryCalendarProvider(httpx.MockTransport(handler))
    now = dt.datetime.now(dt.UTC)
    assert await provider.fetch(now - dt.timedelta(days=1), now + dt.timedelta(days=1), now)
    for status, headers, body in (
        (302, {"location": "http://127.0.0.1/"}, ""),
        (200, {"content-type": "text/html"}, "<html/>"),
        (200, {"content-type": "application/json"}, "x" * 1_000_001),
    ):

        async def bad(request, status=status, headers=headers, body=body):
            return httpx.Response(status, headers=headers, content=body)

        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            await ForexFactoryCalendarProvider(httpx.MockTransport(bad)).fetch(now, now + dt.timedelta(days=1), now)

    async def limited(request):
        return httpx.Response(429, headers={"retry-after": "7200"})

    with pytest.raises(RateLimited) as exc:
        await ForexFactoryCalendarProvider(httpx.MockTransport(limited)).fetch(now, now + dt.timedelta(days=1), now)
    assert exc.value.seconds == 7200


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", ["STRAT01", "STRAT05"])
async def test_dashboard_cached_plan_only_news_depends_on_calendar(monkeypatch, strategy_id):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    from app.api import dashboard

    for name in ("started", "news_card", "analysis_card", "strategy_current", "database_card"):
        monkeypatch.setattr(dashboard, name, AsyncMock(return_value=None))
    value = await dashboard.assemble(SimpleNamespace())
    ctx = qualified_context(strategy_id)
    p = profiles(CONFIG, ctx.config_id)[1].model_copy(update={"allowed_strategies": (strategy_id,)})
    candidate = REGISTRY[strategy_id].evaluate(ctx, p, CONFIG)
    assert candidate.plan
    plan = candidate.plan.model_copy(update={"expires_at": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)})
    value = value.model_copy(update={"current_plan": plan, "candidates": [candidate], "strategy_stale": False})
    monkeypatch.setattr(dashboard, "assemble", AsyncMock(return_value=value))
    provider = SimpleNamespace(available=False, health=lambda: None)
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(news=provider))})
    # health object needed for assembly update even when no health entries consume it.
    provider.health = lambda: SimpleNamespace(state="UNAVAILABLE", detail_th="Unavailable")
    result = await dashboard.summary(request)
    assert (result.current_plan is None) == (strategy_id == "STRAT05")


@pytest.mark.asyncio
async def test_slow_calendar_does_not_pause_market_quote_collection(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.core.config import Settings
    from app.services.news.service import NewsService

    def quote():
        return SimpleNamespace(timestamp=dt.datetime.now(dt.UTC), bid=D(100), ask=D("100.02"), source="simulated")

    market = SimpleNamespace(quote=quote())
    service = NewsService(None, Settings(_env_file=None), market)
    entered = asyncio.Event()
    pending = asyncio.Event()
    calls = 0

    async def slow_poll():
        nonlocal calls
        calls += 1
        entered.set()
        await pending.wait()

    monkeypatch.setattr(service, "poll", slow_poll)
    service.task = asyncio.create_task(service.run())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        market.quote = quote()
        await asyncio.sleep(1.1)
        assert len(service.quotes) == 2 and calls == 1
        assert service.quotes[-1].timestamp == market.quote.timestamp
    finally:
        await service.stop()
    assert service.task is None and service.poll_task is None
