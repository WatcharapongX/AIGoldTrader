"""Documented keyless Xoomar calendar. Limited coverage is NEVER trading-ready.

https://xoomar.com/markets/api/calendar and /terms (reviewed 2026-09-09).
The feed has no per-event update clock or immutable ID. Reference period + exact
series identify an occurrence; receipt is our first knowledge, never release time.
"""

import datetime as dt
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx
from pydantic import AwareDatetime, Field

from app.services.news.domain import EconomicEvent, Mode, UTCModel
from app.services.news.provider import CATALOG, ProviderUnavailable, normalize_number, occurrence_id

URL = "https://xoomar.com/api/markets/calendar"
# Exact series names only: do not confuse YoY CPI with MoM or core inflation.
SERIES = {
    "Nonfarm Payrolls (Employment Situation)": ("bls", "NFP"),
    "CPI (Consumer Price Index)": ("bls", "CPI"),
    "FOMC Rate Decision": ("fed", "FOMC_RATE"),
    "GDP": ("bea", "GDP"),
}


class ProviderHealth(UTCModel):
    source: str
    source_mode: Literal["FIXTURE", "LIVE", "UNAVAILABLE"]
    state: Literal["HEALTHY", "DEGRADED", "STALE", "UNAVAILABLE", "CONFIGURATION_REQUIRED"]
    connected: bool
    coverage: Literal["FULL", "LIMITED", "FIXTURE", "NONE"]
    calendar_usable_for_trading: bool
    provider_updated_at: AwareDatetime | None
    received_at: AwareDatetime | None
    snapshot_clock_skew_seconds: float = Field(default=0, ge=-604800, le=10)
    last_sync_at: AwareDatetime | None
    next_poll_at: AwareDatetime | None
    event_count: int = Field(ge=0, le=2000)
    failures: int = Field(ge=0)
    poll_seconds: int = Field(ge=15)
    reason_code: str
    detail_th: str


class RateLimited(ProviderUnavailable):
    def __init__(self, seconds: int):
        super().__init__("RATE_LIMITED")
        self.seconds = seconds


def utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Provider timestamp must include its timezone")
    return parsed.astimezone(dt.UTC)


def normalize(payload: dict, received: dt.datetime) -> list[EconomicEvent]:
    # Measured upstream snapshot clock is ~4 seconds ahead of this host.
    # Allow <=10s metadata skew only; actual/knowledge clocks still use local receipt.
    updated = utc(payload["updatedAt"])
    if updated > received + dt.timedelta(seconds=10) or payload.get("source") != "xoomar.com":
        raise ValueError("Invalid provider provenance or future update")
    rows = payload["data"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError("Empty or excessive calendar batch")
    events, identities = [], set()
    for row in rows:
        series = row["eventName"]
        if series not in SERIES:
            raise ValueError("Unknown calendar series; review mapping before ingestion")
        agency, code = SERIES[series]
        if row["source"] != agency:
            raise ValueError("Unexpected source agency")
        period = row["periodLabel"]
        if not isinstance(period, str) or not period.strip() or len(period) > 60:
            raise ValueError("Stable reference period is required")
        name, category, unit, rule = CATALOG[code]
        # Provider CPI is explicitly YoY; preserve the measurement in the displayed name.
        if code == "CPI":
            name += " (YoY)"
        when = utc(row["scheduledAt"])
        actual = normalize_number(row.get("actual"), unit)
        if actual is not None and when > received:
            raise ValueError("Future actual rejected")
        # Forecast is explicitly unsupported. A surprise field requires a schema review.
        if row.get("forecast") is not None:
            raise ValueError("Undocumented forecast field")
        identity = occurrence_id("xoomar_calendar", code, period)
        if identity in identities:
            raise ValueError("Ambiguous duplicate occurrence")
        identities.add(identity)
        importance = {"high": "HIGH", "med": "MEDIUM", "low": "LOW"}[row["importance"]]
        events.append(
            EconomicEvent.model_validate(
                dict(
                    id=identity,
                    provider_event_id=code,
                    occurrence_key=period,
                    event_name=name,
                    event_code=code,
                    group_id=occurrence_id("xoomar_calendar", "employment" if code == "NFP" else code, period),
                    country="US",
                    currency="USD",
                    category=category,
                    impact=importance,
                    scheduled_at=when,
                    actual=actual,
                    forecast=None,
                    previous=normalize_number(row.get("previous"), unit),
                    unit=unit,
                    status="RELEASED" if actual is not None else ("SCHEDULED" if when > received else "UNKNOWN"),
                    source="xoomar_calendar",
                    source_mode="LIVE",
                    # updated_at is observation time: this provider supplies no event revision timestamp.
                    updated_at=received,
                    available_at=received,
                    released_at=received if actual is not None else None,
                    revision_version=1,
                    direction_rule=rule,
                )
            )
        )
    return events


class PublicCalendarProvider:
    source = "xoomar_calendar"
    mode: Mode = "LIVE"
    limited_coverage = True
    provider_updated_at: dt.datetime | None = None
    received_at: dt.datetime | None = None

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def fetch(self, start: dt.datetime, end: dt.datetime, as_of: dt.datetime) -> list[EconomicEvent]:
        if end - start > dt.timedelta(days=45):
            raise ValueError("Calendar window exceeds 45 days")
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, transport=self.transport) as client:
            async with client.stream(
                "GET",
                URL,
                params={"from": start.date().isoformat(), "to": end.date().isoformat()},
                headers={"Accept": "application/json"},
            ) as response:
                if response.status_code == 429:
                    retry = response.headers.get("retry-after", "300")
                    try:
                        seconds = int(retry)
                    except ValueError:
                        try:
                            seconds = int((parsedate_to_datetime(retry) - dt.datetime.now(dt.UTC)).total_seconds())
                        except (ValueError, TypeError):
                            seconds = 300
                    # Respect long server backoff, including > normal polling interval.
                    raise RateLimited(max(60, min(86400, seconds)))
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 1_000_000:
                        raise ValueError("Provider payload exceeds one MB")
        import json

        payload = json.loads(content)
        received = dt.datetime.now(dt.UTC)
        events = normalize(payload, received)
        self.provider_updated_at, self.received_at = utc(payload["updatedAt"]), received
        return events
