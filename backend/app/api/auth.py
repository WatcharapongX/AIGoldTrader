"""Auth endpoints — login / refresh / logout / me (TASK-016, docs/05 §2.1)."""

import datetime as dt
import hashlib
import re
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, EmailStr, Field, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.client_ip import resolve_client_ip
from app.core.config import get_settings
from app.core.correlation import get_correlation_id
from app.core.errors import AuthError, RateLimitedError
from app.core.rate_limit import RateLimiter
from app.core.security import create_token, decode_token
from app.db.session import get_session
from app.models import RefreshSession, Role, User
from app.services import audit
from app.services.users import authenticate, get_user, hash_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])

# auth endpoints อนุญาตสั้นกว่า API ทั่วไป (docs/05 §4)
_auth_limiter = RateLimiter(
    per_minute=get_settings().rate_limit_auth_per_minute,
    max_keys=get_settings().rate_limit_max_keys,
)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


# Match the timezone-aware RFC3339 form emitted by Pydantic (microseconds at most).
TOKEN_EXPIRY_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
TokenString = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"^\S+$")]


class TokenPair(BaseModel):
    access_token: TokenString
    refresh_token: TokenString
    token_type: Literal["bearer"]
    expires_at: AwareDatetime = Field(json_schema_extra={"pattern": TOKEN_EXPIRY_PATTERN})

    @field_validator("expires_at", mode="before")
    @classmethod
    def strict_expiry(cls, value):
        # Future-at-receipt is enforced by the client; the transport model stays clock-independent.
        if isinstance(value, dt.datetime):
            return value
        if not isinstance(value, str) or not re.fullmatch(TOKEN_EXPIRY_PATTERN, value, re.ASCII):
            raise ValueError("expires_at must be a timezone-aware RFC3339 timestamp")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: str
    email: str
    role: Role
    is_active: bool


def _as_utc(value: dt.datetime) -> dt.datetime:
    """SQLite คืน naive datetime — normalize เป็น aware UTC ก่อนเทียบ."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)


def _issue_tokens(user: User) -> TokenPair:
    settings = get_settings()
    access, _ = create_token(
        subject=str(user.id),
        role=user.role.value,
        token_type="access",
        secret_key=settings.secret_key,
        access_expire_minutes=settings.jwt_access_token_expire_minutes,
    )
    refresh, _ = create_token(
        subject=str(user.id),
        role=user.role.value,
        token_type="refresh",
        secret_key=settings.secret_key,
        refresh_expire_days=settings.jwt_refresh_token_expire_days,
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        token_type="bearer",
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)) -> TokenPair:
    ip = resolve_client_ip(request)
    try:
        account = hashlib.sha256(str(body.email).strip().casefold().encode()).hexdigest()
        _auth_limiter.check(f"login:client:{ip}", f"login:account:{account}")
    except RateLimitedError:
        await audit.write_audit(session, action="LOGIN_RATE_LIMITED", entity="user", reason=f"ip={ip}", ip=ip)
        await session.commit()
        raise

    user = await authenticate(session, email=body.email, password=body.password)
    tokens = _issue_tokens(user)

    session.add(
        RefreshSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(tokens.refresh_token),
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=get_settings().jwt_refresh_token_expire_days),
            ip=ip,
            user_agent=request.headers.get("user-agent", "")[:300],
        )
    )
    await audit.write_audit(
        session,
        action="LOGIN",
        entity="user",
        entity_id=user.id,
        user_id=user.id,
        after={"email": user.email, "role": user.role.value},
        ip=ip,
    )
    await session.commit()
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    settings = get_settings()
    try:
        claims = decode_token(body.refresh_token, settings.secret_key, expected_type="refresh")
    except Exception as exc:  # noqa: BLE001 — ใด ๆ ที่ decode fail = invalid
        raise AuthError("Invalid refresh token") from exc

    token_hash = hash_refresh_token(body.refresh_token)
    result = await session.execute(select(RefreshSession).where(RefreshSession.refresh_token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is None or stored.revoked_at is not None or _as_utc(stored.expires_at) < dt.datetime.now(dt.UTC):
        raise AuthError("Refresh session is revoked or expired")

    # rotation: revoke session เดิม ออก token ชุดใหม่
    stored.revoked_at = dt.datetime.now(dt.UTC)
    user = await get_user(session, uuid.UUID(str(claims.get("sub"))))
    tokens = _issue_tokens(user)
    session.add(
        RefreshSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(tokens.refresh_token),
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    await audit.write_audit(session, action="TOKEN_REFRESH", entity="user", entity_id=user.id, user_id=user.id)
    await session.commit()
    return tokens


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    request.state.user = current_user
    # revoke ทุก session ที่ยัง active ของ user (simple policy — ปรับเป็นต่อ-device ได้)
    result = await session.execute(
        select(RefreshSession).where(RefreshSession.user_id == current_user.id, RefreshSession.revoked_at.is_(None))
    )
    now = dt.datetime.now(dt.UTC)
    for stored in result.scalars():
        stored.revoked_at = now
    await audit.write_audit(session, action="LOGOUT", entity="user", entity_id=current_user.id, user_id=current_user.id)
    await session.commit()
    return {"status": "ok", "correlation_id": get_correlation_id()}


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )
