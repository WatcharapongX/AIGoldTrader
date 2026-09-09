"""Explicit providers and deterministic synthetic event vintages. No website scraping."""

import datetime as dt
import uuid
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.services.news.domain import EconomicEvent, Mode

# Code, English title, category, unit, directional context. Inflation is context dependent.
CATALOG = {
    "NFP": ("Non-Farm Payrolls", "EMPLOYMENT", "THOUSANDS", "HIGHER_IS_POSITIVE"),
    "UNEMPLOYMENT": ("US Unemployment Rate", "LABOR", "PERCENT", "LOWER_IS_POSITIVE"),
    "WAGES": ("Average Hourly Earnings", "EMPLOYMENT", "PERCENT", "HIGHER_IS_POSITIVE"),
    "CPI": ("Consumer Price Index", "INFLATION", "PERCENT", "CONTEXT_DEPENDENT"),
    "CORE_CPI": ("Core CPI", "INFLATION", "PERCENT", "CONTEXT_DEPENDENT"),
    "PCE": ("PCE Price Index", "INFLATION", "PERCENT", "CONTEXT_DEPENDENT"),
    "CORE_PCE": ("Core PCE", "INFLATION", "PERCENT", "CONTEXT_DEPENDENT"),
    "FOMC_RATE": ("FOMC Rate Decision", "CENTRAL_BANK", "RATE", "CONTEXT_DEPENDENT"),
    "FED_PRESS": ("Fed Press Conference", "CENTRAL_BANK", "NON_NUMERIC", "CONTEXT_DEPENDENT"),
    "POWELL_SPEECH": ("Powell Speech", "CENTRAL_BANK", "NON_NUMERIC", "CONTEXT_DEPENDENT"),
    "GDP": ("Gross Domestic Product", "GROWTH", "PERCENT", "HIGHER_IS_POSITIVE"),
    "PPI": ("Producer Price Index", "INFLATION", "PERCENT", "CONTEXT_DEPENDENT"),
    "RETAIL_SALES": ("Retail Sales", "CONSUMER", "PERCENT", "HIGHER_IS_POSITIVE"),
    "ISM_MANUFACTURING": ("ISM Manufacturing PMI", "MANUFACTURING", "INDEX", "HIGHER_IS_POSITIVE"),
    "ISM_SERVICES": ("ISM Services PMI", "SERVICES", "INDEX", "HIGHER_IS_POSITIVE"),
    "ADP": ("ADP Employment", "EMPLOYMENT", "THOUSANDS", "HIGHER_IS_POSITIVE"),
    "JOLTS": ("JOLTS Job Openings", "LABOR", "THOUSANDS", "HIGHER_IS_POSITIVE"),
    "JOBLESS_CLAIMS": ("Initial Jobless Claims", "LABOR", "THOUSANDS", "LOWER_IS_POSITIVE"),
}


class ProviderUnavailable(RuntimeError):
    pass


class EconomicCalendarProvider(Protocol):
    source: str
    mode: Mode

    async def fetch(self, start: dt.datetime, end: dt.datetime, as_of: dt.datetime) -> list[EconomicEvent]: ...


class NewsTextProvider(Protocol):
    async def text(self, event_id: str, as_of: dt.datetime) -> str | None: ...


class MacroNLPAnalyzer(Protocol):
    async def analyze_text(self, text: str, as_of: dt.datetime) -> dict: ...


def normalize_number(value, unit: str) -> Decimal | None:
    if value is None or str(value).strip() in ("", "-", "N/A"):
        return None
    text = str(value).strip().replace(",", "")
    multiplier = Decimal(1)
    if text.endswith("%"):
        if unit not in ("PERCENT", "RATE"):
            raise ValueError("Percentage unit mismatch")
        text = text[:-1]
    elif text.upper().endswith(("K", "M")):
        if unit != "THOUSANDS":
            raise ValueError("Scale unit mismatch")
        multiplier = Decimal(1000) if text[-1].upper() == "M" else Decimal(1)
        text = text[:-1]
    try:
        result = Decimal(text) * multiplier
    except InvalidOperation:
        raise ValueError("Invalid economic number") from None
    if not result.is_finite() or abs(result) > Decimal("1e15"):
        raise ValueError("Invalid economic number")
    return result


def occurrence_id(source: str, provider_id: str, occurrence_key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join((source, provider_id, occurrence_key))))


def fixture_release(at: dt.datetime, variant: str = "positive") -> list[EconomicEvent]:
    """Synthetic hourly employment release, deliberately not an actual economic calendar."""
    source = "fixture_economic_v1"
    key = at.isoformat()
    group = occurrence_id(source, "employment", key)
    values = {
        "positive": (("250", "180", "165"), ("3.8", "4.0", "4.0"), (".4", ".3", ".3")),
        "negative": (("90", "180", "165"), ("4.2", "4.0", "4.0"), (".1", ".3", ".3")),
        "mixed": (("250", "180", "165"), ("4.2", "4.0", "4.0"), (".4", ".3", ".3")),
    }[variant]
    output = []
    for code, (actual, forecast, previous) in zip(("NFP", "UNEMPLOYMENT", "WAGES"), values, strict=True):
        name, category, unit, rule = CATALOG[code]
        identity = occurrence_id(source, code, key)
        base = EconomicEvent.model_validate(
            {
                "id": identity,
                "provider_event_id": code,
                "occurrence_key": key,
                "event_name": name,
                "event_code": code,
                "group_id": group,
                "country": "US",
                "currency": "USD",
                "category": category,
                "impact": "HIGH",
                "scheduled_at": at,
                "actual": None,
                "forecast": Decimal(forecast),
                "previous": Decimal(previous),
                "unit": unit,
                "status": "SCHEDULED",
                "source": source,
                "source_mode": "FIXTURE",
                "updated_at": at - dt.timedelta(days=1),
                "available_at": at - dt.timedelta(days=1),
                "revision_version": 1,
                "direction_rule": rule,
            }
        )
        output.append(base)
        released = base.model_copy(
            update={
                "actual": Decimal(actual),
                "status": "RELEASED",
                "revision_version": 2,
                "released_at": at + dt.timedelta(seconds=10),
                "available_at": at + dt.timedelta(seconds=10),
                "updated_at": at + dt.timedelta(seconds=10),
            }
        )
        output.append(EconomicEvent.model_validate(released.model_dump()))
        revised = released.model_copy(
            update={
                "revision_version": 3,
                "status": "REVISED",
                "revised_previous": Decimal("100") if code == "NFP" and variant == "mixed" else Decimal(previous),
                "available_at": at + dt.timedelta(minutes=10),
                "updated_at": at + dt.timedelta(minutes=10),
            }
        )
        output.append(EconomicEvent.model_validate(revised.model_dump()))
    return output


class EconomicCalendarReplayProvider:
    source = "fixture_economic_v1"
    mode: Mode = "FIXTURE"

    async def fetch(self, start: dt.datetime, end: dt.datetime, as_of: dt.datetime) -> list[EconomicEvent]:
        if end - start > dt.timedelta(days=7):
            raise ValueError("Calendar window exceeds seven days")
        cursor = start.replace(minute=30, second=0, microsecond=0) - dt.timedelta(hours=1)
        result = []
        while cursor <= end:
            if start <= cursor <= end:
                result.extend(fixture_release(cursor, ("positive", "mixed", "negative")[cursor.hour % 3]))
            cursor += dt.timedelta(hours=1)
        # Available vintages only; never ingest tomorrow's Actual from a fixture today.
        return [event for event in result if event.available_at <= as_of]


class UnavailableCalendarProvider:
    source = "calendar_unavailable"
    mode: Mode = "UNAVAILABLE"

    async def fetch(self, start: dt.datetime, end: dt.datetime, as_of: dt.datetime) -> list[EconomicEvent]:
        raise ProviderUnavailable("CALENDAR_UNAVAILABLE")
