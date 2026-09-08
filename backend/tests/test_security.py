"""Rate limiter + security primitives — TASK-016/019 DoD evidence."""

import pytest

from app.core.errors import RateLimitedError
from app.core.rate_limit import RateLimiter
from app.core.security import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("my-secret-pass")
    assert hashed != "my-secret-pass"
    assert verify_password("my-secret-pass", hashed) is True
    assert verify_password("wrong-pass", hashed) is False


def test_jwt_roundtrip_and_type_guard() -> None:
    secret = "unit-test-secret-key-0123456789abcdef"  # >= 32 bytes (RFC 7518)
    token, _ = create_token(
        subject="user-1", role="ADMIN", token_type="access", secret_key=secret, access_expire_minutes=5
    )
    claims = decode_token(token, secret, expected_type="access")
    assert claims["sub"] == "user-1"
    assert claims["role"] == "ADMIN"

    # access token ใช้แทน refresh token ไม่ได้ (type guard)
    import jwt as pyjwt

    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(token, secret, expected_type="refresh")

    # secret ผิด = ปฏิเสธ
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(token, "another-secret-key-0123456789abcdef")


def test_rate_limiter_blocks_after_quota() -> None:
    limiter = RateLimiter(per_minute=3)
    limiter.check("k")
    limiter.check("k")
    limiter.check("k")
    with pytest.raises(RateLimitedError):
        limiter.check("k")
    limiter.reset("k")
    limiter.check("k")  # หลัง reset ผ่านได้


def test_settings_rejects_invalid_trading_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("TRADING_MODE", "SUPER_LIVE")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
