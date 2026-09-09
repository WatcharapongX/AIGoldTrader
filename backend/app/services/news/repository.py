"""Persist vintages without overwriting history; select vintage before applying schedule filters."""

import datetime as dt
import hashlib

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.economic import EconomicOccurrence, EconomicRevision
from app.services.news.domain import EconomicEvent
from app.services.news.provider import occurrence_id


async def store_events(session: AsyncSession, events: list[EconomicEvent]) -> int:
    if len(events) > 2000:
        raise ValueError("Provider batch exceeds bound")
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    added = 0
    for event in events:
        event = EconomicEvent.model_validate(event.model_dump())
        if event.id != occurrence_id(event.source, event.provider_event_id, event.occurrence_key):
            raise ValueError("Canonical occurrence identity mismatch")
        digest = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
        old = await session.get(EconomicRevision, (event.id, event.revision_version))
        if old:
            if old.payload_hash != digest:
                raise ValueError("Provider changed an existing revision; increment version")
            continue
        await session.execute(
            insert(EconomicOccurrence)
            .values(
                id=event.id,
                source=event.source,
                provider_event_id=event.provider_event_id,
                occurrence_key=event.occurrence_key,
            )
            .on_conflict_do_nothing()
        )
        await session.execute(
            insert(EconomicRevision)
            .values(
                event_id=event.id,
                revision_version=event.revision_version,
                available_at=event.available_at,
                scheduled_at=event.scheduled_at,
                payload_hash=digest,
                payload=event.model_dump(mode="json"),
            )
            .on_conflict_do_nothing()
        )
        added += 1
    return added


async def event_vintages(
    session: AsyncSession, source: str, as_of: dt.datetime, limit: int = 1000
) -> list[EconomicEvent]:
    if as_of.tzinfo is None or not 1 <= limit <= 1000:
        raise ValueError("Invalid point-in-time query")
    ranked = (
        select(
            EconomicRevision.event_id,
            EconomicRevision.revision_version,
            func.row_number()
            .over(partition_by=EconomicRevision.event_id, order_by=EconomicRevision.revision_version.desc())
            .label("rank"),
        )
        .join(EconomicOccurrence, EconomicOccurrence.id == EconomicRevision.event_id)
        .where(EconomicOccurrence.source == source, EconomicRevision.available_at <= as_of)
        .subquery()
    )
    query = (
        select(EconomicRevision)
        .join(
            ranked,
            (ranked.c.event_id == EconomicRevision.event_id)
            & (ranked.c.revision_version == EconomicRevision.revision_version),
        )
        .where(ranked.c.rank == 1)
        .order_by(EconomicRevision.scheduled_at.desc(), EconomicRevision.event_id)
        .limit(limit)
    )
    return [EconomicEvent.model_validate(row.payload) for row in (await session.scalars(query)).all()]


async def revisions(session: AsyncSession, source: str, event_id: str, as_of: dt.datetime) -> list[EconomicEvent]:
    query = (
        select(EconomicRevision)
        .join(EconomicOccurrence)
        .where(
            EconomicOccurrence.source == source,
            EconomicRevision.event_id == event_id,
            EconomicRevision.available_at <= as_of,
        )
        .order_by(EconomicRevision.revision_version.desc())
        .limit(100)
    )
    return [EconomicEvent.model_validate(row.payload) for row in reversed((await session.scalars(query)).all())]


async def store_observations(session: AsyncSession, events: list[EconomicEvent]) -> int:
    """Single NewsService writer allocates append-only local observed vintages.

    A fetched snapshot cannot reconstruct revisions missed between polls. Omission
    is never cancellation. Compare values, not receipt/snapshot clocks, on restart.
    """
    if len(events) > 500 or len({e.id for e in events}) != len(events):
        raise ValueError("Ambiguous or oversized observation batch")
    added = 0
    ignored = {
        "updated_at",
        "available_at",
        "released_at",
        "revision_version",
        "status",
        "revised_previous",
        "previous_before_revision",
    }
    for event in events:
        old = await session.scalar(
            select(EconomicRevision)
            .where(EconomicRevision.event_id == event.id)
            .order_by(EconomicRevision.revision_version.desc())
            .limit(1)
        )
        if old is not None:
            previous = EconomicEvent.model_validate(old.payload)
            old_state = "RELEASED" if previous.status == "REVISED" else previous.status
            new_state = "RELEASED" if event.status == "REVISED" else event.status
            if previous.model_dump(exclude=ignored) == event.model_dump(exclude=ignored) and old_state == new_state:
                continue
            if event.available_at <= previous.available_at:
                raise ValueError("Observation knowledge must advance")
            changes: dict = {"revision_version": previous.revision_version + 1}
            if event.actual is not None:
                changes["status"] = "REVISED"
                if previous.released_at is not None and previous.released_at >= event.scheduled_at:
                    changes["released_at"] = previous.released_at
            # Previous is the latest published value; retain prior observation in history.
            if event.previous != previous.previous:
                changes["revised_previous"] = event.previous
                changes["previous_before_revision"] = previous.previous
            event = EconomicEvent.model_validate({**event.model_dump(), **changes})
        added += await store_events(session, [event])
    return added
