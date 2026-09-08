"""Security primitives — password hashing + JWT (docs/02 §11, FR-SE-01)."""

import datetime as dt
import uuid
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

# pbkdf2_sha256: pure-python, no native build issues; revisit in PHASE 12 hardening
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        return False


TokenType = Literal["access", "refresh"]


def create_token(
    *,
    subject: str,
    role: str,
    token_type: TokenType,
    secret_key: str,
    access_expire_minutes: int = 30,
    refresh_expire_days: int = 7,
) -> tuple[str, dt.datetime]:
    now = dt.datetime.now(dt.UTC)
    if token_type == "access":
        expire = now + dt.timedelta(minutes=access_expire_minutes)
    else:
        expire = now + dt.timedelta(days=refresh_expire_days)
    claims: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": expire,
    }
    token = jwt.encode(claims, secret_key, algorithm="HS256")
    return token, expire


def decode_token(token: str, secret_key: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    claims = jwt.decode(token, secret_key, algorithms=["HS256"])
    if expected_type and claims.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token, got {claims.get('type')}")
    return claims
