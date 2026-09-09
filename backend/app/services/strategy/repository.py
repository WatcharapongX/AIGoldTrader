"""Immutable dependency projections; request envelopes are never database rows."""

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import (
    CandidateTransitionRecord,
    StrategyEvaluationRecord,
    TradeCandidateRecord,
    TraderProfileRecord,
)
from app.services.strategy.domain import EVALUATION_VERSION, Evaluation, SetupCandidate, Transition, fingerprint
from app.services.strategy.identity import projections
from app.services.strategy.lifecycle import transition

logger = logging.getLogger(__name__)


def utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)


async def persist(session: AsyncSession, evaluation: Evaluation) -> dt.datetime:
    values = projections(evaluation)
    clocks = [await _persist_projection(session, value) for value in values]
    return max(clocks)


async def _persist_projection(session: AsyncSession, evaluation: Evaluation) -> dt.datetime:
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    payload = evaluation.model_dump(mode="json")
    digest = fingerprint(payload)
    old = await session.get(StrategyEvaluationRecord, evaluation.id)
    if old:
        if old.payload_hash != digest or old.payload != payload:
            raise ValueError("Immutable evaluation identity conflict")
        for candidate in evaluation.candidates:
            owned_candidate = await session.get(TradeCandidateRecord, candidate.id)
            if (
                owned_candidate is None
                or owned_candidate.evaluation_id != evaluation.id
                or SetupCandidate.model_validate(owned_candidate.payload) != candidate
            ):
                raise ValueError("Persisted candidate ownership or payload conflict")
        return utc(old.generated_at)
    for profile in evaluation.profiles:
        identity = fingerprint([profile.id, profile.config_id])
        existing = await session.get(TraderProfileRecord, identity)
        value = profile.model_dump(mode="json")
        if existing and existing.payload != value:
            raise ValueError("Immutable profile configuration conflict")
        await session.execute(
            insert(TraderProfileRecord)
            .values(id=identity, profile_id=profile.id, config_id=profile.config_id, payload=value)
            .on_conflict_do_nothing()
        )
    generated = dt.datetime.now(dt.UTC)
    await session.execute(
        insert(StrategyEvaluationRecord)
        .values(
            id=evaluation.id,
            context_id=evaluation.context.id,
            symbol=evaluation.context.symbol,
            source=evaluation.context.source,
            as_of=evaluation.context.as_of,
            generated_at=generated,
            payload_hash=digest,
            payload=payload,
        )
        .on_conflict_do_nothing()
    )
    stored = await session.get(StrategyEvaluationRecord, evaluation.id)
    if stored is None or stored.payload_hash != digest or stored.payload != payload:
        raise ValueError("Concurrent evaluation identity conflict")
    for candidate in evaluation.candidates:
        # Predecessor must belong to this profile/strategy, including mixed requests.
        previous = await session.scalar(
            select(TradeCandidateRecord)
            .join(StrategyEvaluationRecord)
            .where(
                StrategyEvaluationRecord.symbol == evaluation.context.symbol,
                StrategyEvaluationRecord.source == evaluation.context.source,
                TradeCandidateRecord.profile_id == candidate.profile_id,
                TradeCandidateRecord.strategy_id == candidate.strategy_id,
                TradeCandidateRecord.as_of <= evaluation.context.as_of,
                TradeCandidateRecord.id != candidate.id,
            )
            .order_by(
                TradeCandidateRecord.as_of.desc(), StrategyEvaluationRecord.generated_at.desc(), TradeCandidateRecord.id
            )
            .limit(1)
        )
        await session.execute(
            insert(TradeCandidateRecord)
            .values(
                id=candidate.id,
                evaluation_id=evaluation.id,
                profile_id=candidate.profile_id,
                strategy_id=candidate.strategy_id,
                as_of=evaluation.context.as_of,
                payload=candidate.model_dump(mode="json"),
            )
            .on_conflict_do_nothing()
        )
        existing_candidate = await session.scalar(
            select(TradeCandidateRecord).where(TradeCandidateRecord.id == candidate.id).with_for_update()
        )
        if existing_candidate is None or SetupCandidate.model_validate(existing_candidate.payload) != candidate:
            raise ValueError("Immutable candidate identity conflict")
        if existing_candidate.evaluation_id != evaluation.id:
            owner = await session.get(StrategyEvaluationRecord, existing_candidate.evaluation_id)
            # Explicit lazy compatibility: retain legacy snapshots/payload hashes and
            # candidate IDs/payloads, adopt only their FK into the canonical leaf.
            if owner is None or owner.payload.get("identity_version") == EVALUATION_VERSION:
                raise ValueError("Candidate evaluation ownership conflict")
            legacy = Evaluation.model_validate(owner.payload)
            if (
                legacy.scope != "LEGACY"
                or legacy.identity_version != "legacy-aggregate-v1"
                or legacy.context.symbol != evaluation.context.symbol
                or legacy.context.source != evaluation.context.source
                or candidate not in legacy.candidates
            ):
                raise ValueError("Legacy candidate ownership is not verifiable")
            old_owner = existing_candidate.evaluation_id
            existing_candidate.evaluation_id = evaluation.id
            await session.flush()
            logger.info(
                "legacy_candidate_owner_adopted candidate=%s previous=%s evaluation=%s",
                candidate.id,
                old_owner,
                evaluation.id,
            )
            # A representation upgrade is not a new trading lifecycle transition.
            continue
        if previous:
            change = transition(SetupCandidate.model_validate(previous.payload), evaluation.context, candidate)
            if change:
                await session.execute(
                    insert(CandidateTransitionRecord)
                    .values(
                        id=change.id,
                        candidate_id=change.candidate_id,
                        as_of=change.as_of,
                        payload=change.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing()
                )
    return utc(stored.generated_at)


async def candidate_history(
    session: AsyncSession, *, limit: int = 50, profile_id: str | None = None
) -> list[SetupCandidate]:
    query = select(TradeCandidateRecord)
    if profile_id:
        query = query.where(TradeCandidateRecord.profile_id == profile_id)
    rows = (
        await session.scalars(query.order_by(TradeCandidateRecord.as_of.desc(), TradeCandidateRecord.id).limit(limit))
    ).all()
    return [SetupCandidate.model_validate(row.payload) for row in rows]


async def transitions(session: AsyncSession, candidate_id: str) -> list[Transition]:
    rows = (
        await session.scalars(
            select(CandidateTransitionRecord)
            .where(CandidateTransitionRecord.candidate_id == candidate_id)
            .order_by(CandidateTransitionRecord.as_of, CandidateTransitionRecord.id)
            .limit(100)
        )
    ).all()
    return [Transition.model_validate(row.payload) for row in rows]
