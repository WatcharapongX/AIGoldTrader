"""Atomic refresh-session consumption and family revocation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshSession


@dataclass(frozen=True)
class ConsumedRefreshSession:
    id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID


async def consume_refresh_session(
    session: AsyncSession,
    *,
    token_hash: str,
) -> ConsumedRefreshSession | None:
    """Atomically consume one active refresh session."""
    statement = (
        update(RefreshSession)
        .where(
            RefreshSession.refresh_token_hash == token_hash,
            RefreshSession.consumed_at.is_(None),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > func.now(),
        )
        .values(consumed_at=func.now())
        .returning(RefreshSession.id, RefreshSession.user_id, RefreshSession.family_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    return ConsumedRefreshSession(id=row.id, user_id=row.user_id, family_id=row.family_id)


async def find_refresh_session_by_hash(session: AsyncSession, *, token_hash: str) -> RefreshSession | None:
    return await session.scalar(select(RefreshSession).where(RefreshSession.refresh_token_hash == token_hash))


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
