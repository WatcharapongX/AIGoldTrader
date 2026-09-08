"""Shared API dependencies — current user from JWT access token."""

import uuid

import jwt as pyjwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthError
from app.core.security import decode_token
from app.db.session import get_session
from app.models import User
from app.services.users import get_user

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise AuthError("Missing bearer token")
    settings = get_settings()
    try:
        claims = decode_token(credentials.credentials, settings.secret_key, expected_type="access")
    except pyjwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise AuthError("Invalid token subject") from exc
    user = await get_user(session, user_id)
    if not user.is_active:
        raise AuthError("Account is disabled")
    request.state.user = user
    return user
