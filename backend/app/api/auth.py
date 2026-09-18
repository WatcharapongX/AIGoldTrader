"""Auth endpoints — login / refresh / logout / me (TASK-016, docs/05 §2.1)."""

import datetime as dt
import hashlib
import re
import uuid
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, Request, Response
from pydantic import AwareDatetime, BaseModel, EmailStr, Field, StringConstraints, field_validator
from sqlalchemy import func, select
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
from app.services.auth_cookies import (
    build_clear_cookie_headers,
    clear_refresh_cookie,
    get_refresh_cookie_name,
    set_refresh_cookie,
    validate_auth_origin,
)
from app.services.refresh_sessions import (
    consume_refresh_session,
    find_refresh_session_by_hash,
    revoke_active_family,
)
from app.services.users import authenticate, hash_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_REUSE_GRACE = dt.timedelta(seconds=5)
INVALID_REFRESH_MESSAGE = "Invalid refresh token"

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


class AccessTokenResponse(BaseModel):
    access_token: TokenString
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


# Alias for backwards compatibility in test suites where TokenPair was referenced
TokenPair = AccessTokenResponse


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class MeResponse(BaseModel):
    id: str
    email: str
    role: Role
    is_active: bool


def _as_utc(value: dt.datetime) -> dt.datetime:
    """SQLite คืน naive datetime — normalize เป็น aware UTC ก่อนเทียบ."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)


class _IssuedTokens:

    def __init__(self, access_token: str, refresh_token: str, expires_at: dt.datetime):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at


def _issue_tokens(user: User) -> _IssuedTokens:
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
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return _IssuedTokens(access_token=access, refresh_token=refresh, expires_at=expires_at)


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AccessTokenResponse:
    validate_auth_origin(request)
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
            family_id=uuid.uuid4(),
            refresh_token_hash=hash_refresh_token(tokens.refresh_token),
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=get_settings().jwt_refresh_token_expire_days),
            consumed_at=None,
            revoked_at=None,
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

    # Success cookie ordering: Set-Cookie strictly after commit
    set_refresh_cookie(response, tokens.refresh_token)

    return AccessTokenResponse(
        access_token=tokens.access_token,
        token_type="bearer",
        expires_at=tokens.expires_at,
    )


async def _reject_refresh_reuse(session: AsyncSession, *, token_hash: str) -> NoReturn:
    """Classify a failed consume internally while keeping one public error."""
    stored = await find_refresh_session_by_hash(session, token_hash=token_hash)
    if stored is None or stored.consumed_at is None:
        raise AuthError(INVALID_REFRESH_MESSAGE, headers=build_clear_cookie_headers())

    consumed_at = _as_utc(stored.consumed_at)
    within_grace = dt.datetime.now(dt.UTC) - consumed_at <= REFRESH_REUSE_GRACE
    reason = "concurrent_rejection_within_grace" if within_grace else "consumed_token_replay_family_revoked"
    await audit.write_audit(
        session,
        action="REFRESH_REUSE",
        entity="refresh_session",
        entity_id=stored.id,
        user_id=stored.user_id,
        reason=reason,
    )
    if not within_grace:
        revoked = await revoke_active_family(session, family_id=stored.family_id)
        await audit.write_audit(
            session,
            action="SESSION_REVOKED",
            entity="refresh_family",
            entity_id=stored.family_id,
            user_id=stored.user_id,
            reason=f"refresh_replay active_sessions={revoked}",
        )
        await session.commit()
        # LATER REPLAY: active family revoked -> clear cookie
        raise AuthError(INVALID_REFRESH_MESSAGE, headers=build_clear_cookie_headers())

    await session.commit()
    # IMMEDIATE CONCURRENT LOSER: within grace -> DO NOT CLEAR COOKIE!
    raise AuthError(INVALID_REFRESH_MESSAGE)


async def _revoke_compromised_family(
    session: AsyncSession,
    *,
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    reason: str,
) -> None:
    revoked = await revoke_active_family(session, family_id=family_id)
    await audit.write_audit(
        session,
        action="SESSION_REVOKED",
        entity="refresh_family",
        entity_id=family_id,
        user_id=user_id,
        reason=f"{reason} active_sessions={revoked} source_session={session_id}",
    )
    await session.commit()


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> AccessTokenResponse:
    validate_auth_origin(request)
    settings = get_settings()
    cookie_name = get_refresh_cookie_name(settings)
    raw_token = request.cookies.get(cookie_name)
    if not raw_token and body and body.refresh_token:
        # Transitional fallback for tests passing explicit body
        raw_token = body.refresh_token

    if not raw_token:
        raise AuthError(INVALID_REFRESH_MESSAGE)

    try:
        claims = decode_token(raw_token, settings.secret_key, expected_type="refresh")
        subject = uuid.UUID(str(claims.get("sub")))
    except Exception as exc:  # noqa: BLE001 — decode/subject failures intentionally share one contract
        raise AuthError(INVALID_REFRESH_MESSAGE, headers=build_clear_cookie_headers(settings)) from exc

    token_hash = hash_refresh_token(raw_token)
    try:
        consumed = await consume_refresh_session(session, token_hash=token_hash)
        if consumed is None:
            await _reject_refresh_reuse(session, token_hash=token_hash)

        if subject != consumed.user_id:
            await _revoke_compromised_family(
                session,
                family_id=consumed.family_id,
                user_id=consumed.user_id,
                session_id=consumed.id,
                reason="jwt_session_subject_mismatch",
            )
            raise AuthError(INVALID_REFRESH_MESSAGE, headers=build_clear_cookie_headers(settings))

        user = await session.get(User, consumed.user_id)
        if user is None or not user.is_active:
            await _revoke_compromised_family(
                session,
                family_id=consumed.family_id,
                user_id=consumed.user_id,
                session_id=consumed.id,
                reason="user_missing_or_inactive",
            )
            raise AuthError(INVALID_REFRESH_MESSAGE, headers=build_clear_cookie_headers(settings))

        tokens = _issue_tokens(user)
        session.add(
            RefreshSession(
                user_id=user.id,
                family_id=consumed.family_id,
                refresh_token_hash=hash_refresh_token(tokens.refresh_token),
                expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=settings.jwt_refresh_token_expire_days),
                consumed_at=None,
                revoked_at=None,
                ip=resolve_client_ip(request),
                user_agent=request.headers.get("user-agent", "")[:300],
            )
        )
        await audit.write_audit(session, action="TOKEN_REFRESH", entity="user", entity_id=user.id, user_id=user.id)
        await session.commit()

        # Success cookie ordering: Set rotated cookie strictly AFTER commit succeeds
        set_refresh_cookie(response, tokens.refresh_token, settings)

        return AccessTokenResponse(
            access_token=tokens.access_token,
            token_type="bearer",
            expires_at=tokens.expires_at,
        )
    except AuthError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    validate_auth_origin(request)
    request.state.user = current_user
    # revoke ทุก session ที่ยัง active ของ user (simple policy — ปรับเป็นต่อ-device ได้)
    result = await session.execute(
        select(RefreshSession).where(
            RefreshSession.user_id == current_user.id,
            RefreshSession.consumed_at.is_(None),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > func.now(),
        )
    )
    now = dt.datetime.now(dt.UTC)
    for stored in result.scalars():
        stored.revoked_at = now
    await audit.write_audit(session, action="LOGOUT", entity="user", entity_id=current_user.id, user_id=current_user.id)
    await session.commit()
    clear_refresh_cookie(response)
    return {"status": "ok", "correlation_id": get_correlation_id()}


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )
