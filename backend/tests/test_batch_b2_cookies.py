"""Batch B2: Comprehensive tests for HttpOnly refresh cookie contract and Origin CSRF validation."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.models import RefreshSession
from app.services.users import hash_refresh_token


def test_login_cookie_attributes_and_json_contract(client: TestClient, admin_user) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    data = response.json()

    # Refresh token MUST NOT be in response JSON
    assert "refresh_token" not in data
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_at" in data

    # Refresh cookie MUST be in Set-Cookie with strict security attributes
    raw_cookie = response.headers.get("set-cookie")
    assert raw_cookie is not None
    assert "aigold_refresh_dev=" in raw_cookie
    assert "HttpOnly" in raw_cookie
    assert "SameSite=strict" in raw_cookie or "samesite=strict" in raw_cookie
    assert "Path=/" in raw_cookie or "path=/" in raw_cookie
    assert "Domain=" not in raw_cookie and "domain=" not in raw_cookie
    assert "Max-Age=604800" in raw_cookie or "max-age=604800" in raw_cookie


def test_refresh_rotates_cookie_and_returns_access_only_json(client: TestClient, admin_user) -> None:
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    initial_cookie = login_resp.cookies.get("aigold_refresh_dev")
    assert initial_cookie is not None

    # Refresh request with NO body, cookie sent via transport
    refresh_resp = client.post(
        "/api/auth/refresh",
        headers={"origin": "http://localhost:3000"},
    )
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "refresh_token" not in data
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Rotated cookie must be different from initial
    rotated_cookie = refresh_resp.cookies.get("aigold_refresh_dev")
    assert rotated_cookie is not None
    assert rotated_cookie != initial_cookie


def test_immediate_concurrent_loser_does_not_clear_cookie(client: TestClient, admin_user, db_session) -> None:
    """CRITICAL B1 compatibility: Concurrency loser within 5s grace MUST NOT clear cookie."""
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    token = login_resp.cookies.get("aigold_refresh_dev")

    # Winner consumes token
    winner = client.post(
        "/api/auth/refresh",
        headers={"origin": "http://localhost:3000"},
    )
    assert winner.status_code == 200

    # Loser re-sends the consumed token immediately (within 5s grace)
    loser = client.post(
        "/api/auth/refresh",
        cookies={"aigold_refresh_dev": token},
        headers={"origin": "http://localhost:3000"},
    )
    assert loser.status_code == 401
    assert loser.json()["error"]["message"] == "Invalid refresh token"

    # Loser response MUST NOT contain Set-Cookie with Max-Age=0 (must NOT delete winner's cookie)
    loser_cookie_header = loser.headers.get("set-cookie")
    if loser_cookie_header:
        assert "Max-Age=0" not in loser_cookie_header and "max-age=0" not in loser_cookie_header


async def test_later_replay_revokes_family_and_clears_cookie(client: TestClient, admin_user, db_session) -> None:
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    token = login_resp.cookies.get("aigold_refresh_dev")
    assert token is not None

    # Rotate
    refreshed = client.post(
        "/api/auth/refresh",
        headers={"origin": "http://localhost:3000"},
    )
    assert refreshed.status_code == 200

    # Fast-forward consumed_at beyond 5s grace
    session, _ = db_session
    sess = await session.scalar(
        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token))
    )
    assert sess is not None
    sess.consumed_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=15)
    await session.commit()

    # Replay beyond grace window
    replay = client.post(
        "/api/auth/refresh",
        cookies={"aigold_refresh_dev": token},
        headers={"origin": "http://localhost:3000"},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["message"] == "Invalid refresh token"

    # Set-Cookie MUST clear the cookie
    cookie_header = replay.headers.get("set-cookie", "")
    assert "Max-Age=0" in cookie_header or "max-age=0" in cookie_header


def test_logout_clears_refresh_cookie(client: TestClient, admin_user) -> None:
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    token = login_resp.json()["access_token"]
    logout_resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}", "origin": "http://localhost:3000"},
    )
    assert logout_resp.status_code == 200
    cookie_header = logout_resp.headers.get("set-cookie", "")
    assert "aigold_refresh_dev=" in cookie_header
    assert "Max-Age=0" in cookie_header or "max-age=0" in cookie_header


def test_terminal_failures_clear_cookie(client: TestClient, admin_user) -> None:
    # Malformed token
    malformed = client.post(
        "/api/auth/refresh",
        cookies={"aigold_refresh_dev": "malformed.jwt.token"},
        headers={"origin": "http://localhost:3000"},
    )
    assert malformed.status_code == 401
    cookie_header = malformed.headers.get("set-cookie", "")
    assert "Max-Age=0" in cookie_header or "max-age=0" in cookie_header


# Origin CSRF Tests
def test_login_origin_validation(client: TestClient, admin_user, db_session) -> None:
    # 1. Approved origin: OK
    resp_ok = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    assert resp_ok.status_code == 200

    # 2. Missing origin: 403 Forbidden
    resp_missing = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": ""},
    )
    assert resp_missing.status_code == 403
    assert resp_missing.json()["error"]["code"] == "FORBIDDEN"

    # 3. Unapproved origin: 403 Forbidden
    resp_evil = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://evil.com"},
    )
    assert resp_evil.status_code == 403

    # 4. Lookalike origin: 403 Forbidden
    resp_lookalike = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000.evil.com"},
    )
    assert resp_lookalike.status_code == 403

    # 5. Scheme mismatch: 403 Forbidden
    resp_scheme = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "https://localhost:3000"},
    )
    assert resp_scheme.status_code == 403

    # 6. Port mismatch: 403 Forbidden
    resp_port = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:9999"},
    )
    assert resp_port.status_code == 403


def test_refresh_origin_validation(client: TestClient, admin_user) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    assert login.status_code == 200

    # Unapproved origin on refresh
    resp = client.post(
        "/api/auth/refresh",
        headers={"origin": "http://attacker.com"},
    )
    assert resp.status_code == 403


def test_logout_origin_validation(client: TestClient, admin_user) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    token = login.json()["access_token"]

    # Unapproved origin on logout
    resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}", "origin": "http://attacker.com"},
    )
    assert resp.status_code == 403


# Configuration validation tests
def test_production_startup_validation() -> None:
    # Valid PROD config
    s_valid = Settings(
        app_env="PROD",
        secret_key="a" * 32,
        auth_cookie_secure=True,
        auth_cookie_name="__Host-aigold_refresh",
        auth_trusted_origins="https://app.aigoldtrader.com",
    )
    s_valid.validate_runtime_secrets()

    # PROD with insecure cookie -> fail
    with pytest.raises(ValueError, match="PROD/UAT requires secure refresh cookie"):
        Settings(
            app_env="PROD",
            secret_key="a" * 32,
            auth_cookie_secure=False,
            auth_cookie_name="__Host-aigold_refresh",
            auth_trusted_origins="https://app.aigoldtrader.com",
        ).validate_runtime_secrets()

    # PROD without __Host- -> fail
    with pytest.raises(ValueError, match="PROD/UAT requires __Host- prefix"):
        Settings(
            app_env="PROD",
            secret_key="a" * 32,
            auth_cookie_secure=True,
            auth_cookie_name="aigold_refresh",
            auth_trusted_origins="https://app.aigoldtrader.com",
        ).validate_runtime_secrets()

    # PROD with plain http origin -> fail
    with pytest.raises(ValueError, match="PROD/UAT trusted origins must use HTTPS"):
        Settings(
            app_env="PROD",
            secret_key="a" * 32,
            auth_cookie_secure=True,
            auth_cookie_name="__Host-aigold_refresh",
            auth_trusted_origins="http://app.aigoldtrader.com",
        ).validate_runtime_secrets()

    # PROD with wildcard origin -> fail
    with pytest.raises(ValueError, match="Wildcard origins are strictly forbidden"):
        Settings(
            app_env="PROD",
            secret_key="a" * 32,
            auth_cookie_secure=True,
            auth_cookie_name="__Host-aigold_refresh",
            auth_trusted_origins="https://*.aigoldtrader.com",
        ).validate_runtime_secrets()

    # DEV with insecure cookie and __Host- prefix -> fail
    with pytest.raises(ValueError, match="Insecure cookie cannot use __Host- prefix"):
        Settings(
            app_env="DEV",
            secret_key="a" * 32,
            auth_cookie_secure=False,
            auth_cookie_name="__Host-aigold_refresh",
            auth_trusted_origins="http://localhost:3000",
        ).validate_runtime_secrets()


async def test_refresh_ignores_json_body_without_cookie_zero_mutation(
    client: TestClient, admin_user, db_session
) -> None:
    """Gap #1: JSON body containing valid refresh token without cookie must return 401 with 0 DB mutations."""
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    assert login.status_code == 200
    token = login.cookies.get("aigold_refresh_dev")
    assert token is not None

    session, _ = db_session
    before_sess = await session.scalar(
        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token))
    )
    assert before_sess is not None and before_sess.consumed_at is None

    # Clear all cookies so client has NO refresh cookie
    client.cookies.clear()

    # Send POST /auth/refresh with valid token in JSON body but no cookie
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": token},
        headers={"origin": "http://localhost:3000"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid refresh token"
    assert "set-cookie" not in response.headers

    # Verify zero DB mutation: session remains unconsumed and unrevoked, no successors created
    after_sess = await session.scalar(
        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token))
    )
    assert after_sess is not None
    assert after_sess.consumed_at is None
    assert after_sess.revoked_at is None

    family_sessions = (
        await session.scalars(select(RefreshSession).where(RefreshSession.family_id == before_sess.family_id))
    ).all()
    assert len(family_sessions) == 1


async def test_refresh_cookie_is_sole_authority_ignores_body(
    client: TestClient, admin_user, db_session
) -> None:
    """Gap #1: Cookie is the sole authority; body content is completely ignored."""
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"origin": "http://localhost:3000"},
    )
    assert login.status_code == 200
    token_a = login.cookies.get("aigold_refresh_dev")
    assert token_a is not None

    session, _ = db_session
    before_sess = await session.scalar(
        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token_a))
    )
    assert before_sess is not None

    # Client has cookie_a, but supplies unrelated token in JSON body
    client.cookies.clear()
    client.cookies.set("aigold_refresh_dev", token_a)
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "some-other-unrelated-token"},
        headers={"origin": "http://localhost:3000"},
    )
    assert response.status_code == 200

    # Cookie A was the authority that rotated
    session.expire_all()
    after_sess = await session.scalar(
        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token_a))
    )
    assert after_sess is not None
    assert after_sess.consumed_at is not None

    # Family has exactly 2 members: consumed A and new successor
    family_sessions = (
        await session.scalars(select(RefreshSession).where(RefreshSession.family_id == before_sess.family_id))
    ).all()
    assert len(family_sessions) == 2
