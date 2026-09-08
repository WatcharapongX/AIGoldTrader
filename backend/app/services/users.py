"""User management + authentication service (TASK-016)."""

import datetime as dt
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models import Role, User

_REFRESH_TOKEN_SALT = b"refresh-token-hash"


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(_REFRESH_TOKEN_SALT + token.encode()).hexdigest()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    role: Role = Role.VIEWER,
) -> User:
    user = User(email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    await session.flush()
    return user


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("Account is disabled")
    user.last_login_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return user


def require_role(*allowed: Role):
    """FastAPI dependency factory — RBAC guard (FR-SE-01)."""

    from fastapi import Depends  # local import กัน circular ตอน import จาก api layer

    from app.api.deps import get_current_user

    async def _guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise ForbiddenError(f"Requires role in {[r.value for r in allowed]}")
        return current_user

    return _guard
