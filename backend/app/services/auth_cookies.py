"""Central auth cookie management and Origin CSRF validation (Batch B2, AUD-P2-002)."""

from __future__ import annotations

from fastapi import Request, Response

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError


def get_refresh_cookie_name(settings: Settings | None = None) -> str:
    return (settings or get_settings()).effective_auth_cookie_name


def get_refresh_cookie_secure(settings: Settings | None = None) -> bool:
    return (settings or get_settings()).effective_auth_cookie_secure


def set_refresh_cookie(response: Response, refresh_token: str, settings: Settings | None = None) -> None:
    s = settings or get_settings()
    name = s.effective_auth_cookie_name
    secure = s.effective_auth_cookie_secure
    max_age = int(s.jwt_refresh_token_expire_days * 86400)
    response.set_cookie(
        key=name,
        value=refresh_token,
        max_age=max_age,
        path="/",
        domain=None,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, settings: Settings | None = None) -> None:
    s = settings or get_settings()
    name = s.effective_auth_cookie_name
    secure = s.effective_auth_cookie_secure
    response.set_cookie(
        key=name,
        value="",
        max_age=0,
        path="/",
        domain=None,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def build_clear_cookie_headers(settings: Settings | None = None) -> dict[str, str]:
    s = settings or get_settings()
    name = s.effective_auth_cookie_name
    secure = s.effective_auth_cookie_secure
    parts = [f"{name}=", "Path=/", "Max-Age=0", "SameSite=Strict", "HttpOnly"]
    if secure:
        parts.append("Secure")
    return {"Set-Cookie": "; ".join(parts)}


def validate_auth_origin(request: Request, settings: Settings | None = None) -> None:
    """Validate request Origin strictly against explicit configured trusted browser origins.

    Missing Origin or unapproved Origin raises ForbiddenError (HTTP 403) before any DB mutation.
    """
    s = settings or get_settings()
    raw_origin = request.headers.get("origin")
    if not raw_origin:
        raise ForbiddenError("Missing Origin header")

    norm = s._normalize_single_origin(raw_origin)
    if not norm or norm not in s.auth_trusted_origin_list:
        raise ForbiddenError("Forbidden origin")
