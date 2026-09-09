"""No network in unit tests; real acceptance is recorded separately."""

import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.core.config import Settings
from app.services.news.public_calendar import PublicCalendarProvider, RateLimited, normalize
from app.services.news.repository import event_vintages, revisions, store_observations
from app.services.news.service import NewsService

AT = dt.datetime(2026, 9, 9, 14, tzinfo=dt.UTC)


def payload():
    return {
        "source": "xoomar.com",
        "updatedAt": "2026-09-09T12:00:00Z",
        "data": [
            {
                "source": "bls",
                "eventName": "Nonfarm Payrolls (Employment Situation)",
                "importance": "high",
                "scheduledAt": "2026-09-04T08:30:00-04:00",
                "periodLabel": "August 2026",
                "actual": "162.0000",
                "previous": "21",
                "forecast": None,
            }
        ],
    }


def test_keyless_values_timezones_and_conservative_receipt():
    e = normalize(payload(), AT)[0]
    assert e.actual == 162 and e.previous == 21 and e.forecast is None
    assert e.scheduled_at.isoformat() == "2026-09-04T12:30:00+00:00"
    assert e.scheduled_at.astimezone(ZoneInfo("Asia/Bangkok")).hour == 19
    assert e.available_at == e.updated_at == e.released_at == AT
    assert e.source_mode == "LIVE"


@pytest.mark.parametrize(
    "key,value",
    [
        ("actual", "NaN"),
        ("actual", "9999999999999999999"),
        ("scheduledAt", "2027-01-01T12:30:00Z"),
        ("scheduledAt", "2026-09-04T12:30:00"),
        ("periodLabel", None),
        ("source", "unknown"),
        ("eventName", "Core CPI"),
        ("forecast", "100"),
        ("importance", "guess"),
    ],
)
def test_malformed_future_or_ambiguous_feed_rejected(key, value):
    data = payload()
    data["data"][0][key] = value
    with pytest.raises((ValueError, KeyError)):
        normalize(data, AT)


def test_duplicate_unknown_and_provider_clock_rejected():
    data = payload()
    data["data"] *= 2
    with pytest.raises(ValueError):
        normalize(data, AT)
    data = payload()
    data["updatedAt"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        normalize(data, AT)


def test_dst_missing_values_and_no_invented_forecast():
    data = payload()
    data["data"][0].update(scheduledAt="2026-12-04T08:30:00-05:00", actual=None, previous=None)
    e = normalize(data, AT)[0]
    assert e.scheduled_at.hour == 13
    assert e.scheduled_at.astimezone(ZoneInfo("Asia/Bangkok")).hour == 20
    assert e.actual is e.previous is e.forecast is e.released_at is None


async def test_append_only_dedup_restart_reschedule_revision_and_cutoff(db_session):
    session, _ = db_session
    first = normalize(payload(), AT)[0]
    assert await store_observations(session, [first]) == 1
    await session.commit()
    assert await store_observations(session, normalize(payload(), AT + dt.timedelta(minutes=5))) == 0
    revised = payload()
    revised["data"][0].update(actual="163", previous="22", scheduledAt="2026-09-04T09:00:00-04:00")
    next_event = normalize(revised, AT + dt.timedelta(minutes=10))[0]
    assert next_event.id == first.id
    assert await store_observations(session, [next_event]) == 1
    await session.commit()
    assert await store_observations(session, normalize(revised, AT + dt.timedelta(minutes=15))) == 0
    before = await event_vintages(session, first.source, AT - dt.timedelta(seconds=1))
    assert not before
    old = (await event_vintages(session, first.source, AT))[0]
    latest = (await event_vintages(session, first.source, AT + dt.timedelta(minutes=20)))[0]
    assert old.actual == 162 and latest.actual == 163 and latest.revised_previous == 22
    assert len(await revisions(session, first.source, first.id, AT + dt.timedelta(minutes=20))) == 2


async def test_poll_failure_and_partial_coverage_never_approve_calendar(db_session):
    _, factory = db_session
    service = NewsService(
        factory, Settings(_env_file=None, news_calendar_provider="xoomar"), SimpleNamespace(quote=None)
    )

    class Provider(PublicCalendarProvider):
        failed = False

        async def fetch(self, start, end, as_of):
            if self.failed:
                raise RateLimited(1800)
            return normalize(payload(), AT)

    service.provider = Provider()
    await service.poll()
    assert service.health().connected and service.health().coverage == "LIMITED"
    assert not service.available and not service.health().calendar_usable_for_trading
    service.provider.failed = True
    await service.poll()
    import time

    assert service.next_poll - time.monotonic() > 1790
    assert service.health().state == "DEGRADED" and not service.health().connected
    assert service.provider.source == "xoomar_calendar"
    service.last_success -= 10000
    assert service.health().state == "STALE"


@pytest.mark.parametrize("code", [429, 500, 302])
async def test_http_failure_no_fallback(code):
    def handler(request):
        assert request.url.host == "xoomar.com" and "key" not in str(request.url)
        return httpx.Response(code, headers={"Retry-After": "900"})

    provider = PublicCalendarProvider(httpx.MockTransport(handler))
    with pytest.raises((RateLimited, httpx.HTTPStatusError)):
        await provider.fetch(AT - dt.timedelta(days=7), AT + dt.timedelta(days=30), AT)


async def test_documented_http_payload_normalizes():
    provider = PublicCalendarProvider(httpx.MockTransport(lambda _: httpx.Response(200, json=payload())))
    assert (await provider.fetch(AT - dt.timedelta(days=7), AT + dt.timedelta(days=30), AT))[0].actual == 162


def test_unconfigured_runtime_never_defaults_to_fixture():
    assert Settings(_env_file=None).news_calendar_provider == "unavailable"
