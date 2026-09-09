"""Official weekly JSON export; USD series only, observation-time knowledge.

No HTML scraping, credentials, arbitrary URL, secondary merge, or inferred actual.
Identity: exact series + ISO week. Ambiguous duplicates fail closed; cross-week
reschedules cannot be linked without a provider identifier and remain a limitation.
"""

import datetime as dt
import json
from email.utils import parsedate_to_datetime

import httpx

from app.services.news.domain import EconomicEvent, Mode
from app.services.news.provider import CATALOG, normalize_number, occurrence_id
from app.services.news.public_calendar import RateLimited, utc

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SOURCE = "forex_factory"
# Exact names and measurement frequencies: headline and core never alias.
SERIES = {
    "Non-Farm Employment Change": ("NFP", "NFP"),
    "Unemployment Rate": ("UNEMPLOYMENT", "NFP"),
    "Average Hourly Earnings m/m": ("WAGES", "NFP"),
    "CPI m/m": ("CPI_MOM", "CPI"),
    "CPI y/y": ("CPI_YOY", "CPI"),
    "Core CPI m/m": ("CORE_CPI_MOM", "CPI"),
    "Core CPI y/y": ("CORE_CPI_YOY", "CPI"),
    "PPI m/m": ("PPI", "PPI"),
    "Core PPI m/m": ("CORE_PPI", "PPI"),
    "PCE Price Index m/m": ("PCE", "PCE"),
    "Core PCE Price Index m/m": ("CORE_PCE", "PCE"),
    "Federal Funds Rate": ("FOMC_RATE", "FOMC"),
    "FOMC Statement": ("FOMC_STATEMENT", "FOMC"),
    "FOMC Press Conference": ("FED_PRESS", "FOMC_PRESS"),
    "Fed Chair Powell Speaks": ("POWELL_SPEECH", "POWELL"),
    "Advance GDP q/q": ("GDP_ADVANCE", "GDP_ADVANCE"),
    "Prelim GDP q/q": ("GDP_PRELIM", "GDP_PRELIM"),
    "Final GDP q/q": ("GDP_FINAL", "GDP_FINAL"),
    "Retail Sales m/m": ("RETAIL_SALES", "RETAIL"),
    "Core Retail Sales m/m": ("CORE_RETAIL_SALES", "RETAIL"),
    "ISM Manufacturing PMI": ("ISM_MANUFACTURING", "ISM_MANUFACTURING"),
    "ISM Services PMI": ("ISM_SERVICES", "ISM_SERVICES"),
    "JOLTS Job Openings": ("JOLTS", "JOLTS"),
    "ADP Non-Farm Employment Change": ("ADP", "ADP"),
    "Unemployment Claims": ("JOBLESS_CLAIMS", "JOBLESS_CLAIMS"),
}
BASE = {
    "CPI_MOM": "CPI",
    "CPI_YOY": "CPI",
    "CORE_CPI_MOM": "CORE_CPI",
    "CORE_CPI_YOY": "CORE_CPI",
    "CORE_PPI": "PPI",
    "GDP_ADVANCE": "GDP",
    "GDP_PRELIM": "GDP",
    "GDP_FINAL": "GDP",
    "CORE_RETAIL_SALES": "RETAIL_SALES",
    "FOMC_STATEMENT": "FED_PRESS",
}
IMPACTS = {
    "High": "HIGH",
    "Medium": "MEDIUM",
    "Low": "LOW",
    "Holiday": "HOLIDAY",
    "Non-Economic": "NON_ECONOMIC",
    "Unknown": "UNKNOWN",
}


def normalize(payload: object, received: dt.datetime) -> list[EconomicEvent]:
    if received.tzinfo is None or not isinstance(payload, list) or not 1 <= len(payload) <= 500:
        raise ValueError("Invalid bounded calendar batch")
    events, seen = [], set()
    for row in payload:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("country"), str)
            or not isinstance(row.get("title"), str)
        ):
            raise ValueError("Invalid calendar row")
        if row["country"] != "USD" or row["title"] not in SERIES:
            continue
        if not isinstance(row.get("date"), str):
            raise ValueError("Missing offset-aware event schedule")
        when = utc(row["date"])
        code, group = SERIES[row["title"]]
        _, category, unit, rule = CATALOG[BASE.get(code, code)]
        week = when.date().isocalendar()
        period = f"{week.year}-W{week.week:02d}"
        identity = occurrence_id(SOURCE, code, period)
        if identity in seen:
            raise ValueError("Ambiguous weekly series occurrence")
        seen.add(identity)
        actual = normalize_number(row.get("actual"), unit)
        forecast = normalize_number(row.get("forecast"), unit)
        previous = normalize_number(row.get("previous"), unit)
        if actual is not None and when > received:
            raise ValueError("Future actual rejected")
        fields = {field: SOURCE for field in ("scheduled_at", "impact", "event_name")}
        fields.update(
            {
                field: SOURCE
                for field, value in (("actual", actual), ("forecast", forecast), ("previous", previous))
                if value is not None
            }
        )
        events.append(
            EconomicEvent.model_validate(
                dict(
                    id=identity,
                    provider_event_id=code,
                    occurrence_key=period,
                    event_name=row["title"],
                    event_code=code,
                    group_id=occurrence_id(SOURCE, group, period),
                    country="US",
                    currency="USD",
                    category=category,
                    impact=IMPACTS.get(str(row.get("impact")), "UNKNOWN"),
                    scheduled_at=when,
                    actual=actual,
                    forecast=forecast,
                    previous=previous,
                    unit=unit,
                    status="RELEASED" if actual is not None else "SCHEDULED" if when > received else "UNKNOWN",
                    source=SOURCE,
                    source_mode="LIVE",
                    updated_at=received,
                    available_at=received,
                    released_at=received if actual is not None else None,
                    revision_version=1,
                    direction_rule=rule,
                    field_provenance=fields,
                )
            )
        )
    if not events:
        raise ValueError("No supported USD events; calendar coverage unknown")
    return events


class ForexFactoryCalendarProvider:
    source = SOURCE
    mode: Mode = "LIVE"
    limited_coverage = False  # Supported USD schedule usable; actual is gated per release.
    provider_updated_at: dt.datetime | None = None
    received_at: dt.datetime | None = None

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def fetch(self, start: dt.datetime, end: dt.datetime, as_of: dt.datetime) -> list[EconomicEvent]:
        if end <= start or end - start > dt.timedelta(days=45):
            raise ValueError("Invalid calendar window")
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=False, transport=self.transport, trust_env=False
        ) as client:
            async with client.stream("GET", URL, headers={"Accept": "application/json"}) as response:
                if response.status_code == 429:
                    try:
                        seconds = int(response.headers.get("retry-after", "300"))
                    except ValueError:
                        try:
                            seconds = int(
                                (
                                    parsedate_to_datetime(response.headers["retry-after"]) - dt.datetime.now(dt.UTC)
                                ).total_seconds()
                            )
                        except (ValueError, TypeError, KeyError):
                            seconds = 300
                    raise RateLimited(max(60, min(86400, seconds)))
                response.raise_for_status()
                if response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                    raise ValueError("Calendar must be JSON")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 1_000_000:
                        raise ValueError("Calendar exceeds one MB")
        received = dt.datetime.now(dt.UTC)
        events = normalize(json.loads(content), received)
        # A cached old weekly file must not be labeled healthy after rollover.
        if not any(
            received - dt.timedelta(days=7) <= e.scheduled_at <= received + dt.timedelta(days=7) for e in events
        ):
            raise ValueError("Stale weekly calendar")
        self.received_at = received
        return events
