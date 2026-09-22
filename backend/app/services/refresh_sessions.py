"""Atomic refresh-session consumption and family revocation."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshSession


@dataclass(frozen=True)
class ConsumedRefreshSession:
    id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID


@dataclass(frozen=True)
class RefreshSessionIdentity:
    """Immutable routing fields safe to retain while waiting for the authority lock."""

    id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID


@dataclass(frozen=True)
class RefreshSessionState:
    """Authoritative post-lock refresh-session state (never an ORM identity-map value)."""

    id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID
    expires_at: dt.datetime
    consumed_at: dt.datetime | None
    revoked_at: dt.datetime | None


def user_authority_key(user_id: uuid.UUID) -> int:
    """Return the stable signed int64 PostgreSQL advisory key for a user authority scope."""
    digest = hashlib.sha256(b"aigold:auth-user:v1:" + user_id.bytes).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def database_clock_timestamp(session: AsyncSession) -> dt.datetime:
    """Read wall-clock time from PostgreSQL; SQLite is retained only for unit-test support."""
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        return await session.scalar(select(func.clock_timestamp()))
    return dt.datetime.now(dt.UTC)


async def acquire_user_authority_lock(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Boundedly serialize one user's refresh/logout authority mutations in this transaction."""
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    # A timed-out lock aborts this transaction; callers fail closed and never mutate without it.
    await session.execute(text("SET LOCAL lock_timeout = '5s'"))
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": user_authority_key(user_id)})


async def resolve_refresh_session_identity(
    session: AsyncSession, *, token_hash: str
) -> RefreshSessionIdentity | None:
    """Resolve only immutable routing fields before the advisory lock."""
    row = (
        await session.execute(
            select(RefreshSession.id, RefreshSession.user_id, RefreshSession.family_id).where(
                RefreshSession.refresh_token_hash == token_hash
            )
        )
    ).one_or_none()
    if row is None:
        return None
    return RefreshSessionIdentity(id=row.id, user_id=row.user_id, family_id=row.family_id)


async def reread_refresh_session_state(
    session: AsyncSession, *, session_id: uuid.UUID
) -> RefreshSessionState | None:
    """Read mutable state directly from the database after acquiring authority serialization."""
    row = (
        await session.execute(
            select(
                RefreshSession.id,
                RefreshSession.user_id,
                RefreshSession.family_id,
                RefreshSession.expires_at,
                RefreshSession.consumed_at,
                RefreshSession.revoked_at,
            ).where(RefreshSession.id == session_id)
        )
    ).one_or_none()
    if row is None:
        return None
    return RefreshSessionState(
        id=row.id,
        user_id=row.user_id,
        family_id=row.family_id,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        revoked_at=row.revoked_at,
    )


async def consume_refresh_session(
    session: AsyncSession,
    *,
    token_hash: str,
) -> ConsumedRefreshSession | None:
    """Atomically consume one active refresh session."""
    use_postgres_clock = session.bind is not None and session.bind.dialect.name == "postgresql"
    consumed_at = func.clock_timestamp() if use_postgres_clock else func.now()
    statement = (
        update(RefreshSession)
        .where(
            RefreshSession.refresh_token_hash == token_hash,
            RefreshSession.consumed_at.is_(None),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > func.now(),
        )
        .values(consumed_at=consumed_at)
        .returning(RefreshSession.id, RefreshSession.user_id, RefreshSession.family_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    return ConsumedRefreshSession(id=row.id, user_id=row.user_id, family_id=row.family_id)


async def revoke_active_family(session: AsyncSession, *, family_id: uuid.UUID) -> int:
    """Revoke unconsumed, unexpired members without rewriting history."""
    statement = (
        update(RefreshSession)
        .where(
            RefreshSession.family_id == family_id,
            RefreshSession.consumed_at.is_(None),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > func.now(),
        )
        .values(revoked_at=func.now())
        .returning(RefreshSession.id)
    )
    return len((await session.scalars(statement)).all())


async def revoke_active_user_sessions(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Set-based terminal logout revocation for all active refresh authority of one user."""
    use_postgres_clock = session.bind is not None and session.bind.dialect.name == "postgresql"
    revoked_at = func.clock_timestamp() if use_postgres_clock else func.now()
    statement = (
        update(RefreshSession)
        .where(
            RefreshSession.user_id == user_id,
            RefreshSession.consumed_at.is_(None),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > func.now(),
        )
        .values(revoked_at=revoked_at)
        .returning(RefreshSession.id)
    )
    return len((await session.scalars(statement)).all())
