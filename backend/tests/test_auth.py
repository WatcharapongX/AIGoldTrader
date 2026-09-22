"""Authentication flow — TASK-016 DoD evidence."""

import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_token
from app.models import RefreshSession
from app.services.users import hash_refresh_token


def test_login_success_returns_token_pair(client: TestClient, admin_user) -> None:
    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert "refresh_token" not in body
    assert body["token_type"] == "bearer"
    assert "aigold_refresh_dev" in response.cookies


def test_login_wrong_password_rejected(client: TestClient, admin_user) -> None:
    response = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong-pass-999"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"


def test_login_unknown_user_same_error_as_wrong_password(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "whatever-123"})
    assert response.status_code == 401  # ไม่เปิดเผยว่า email มีจริงหรือไม่


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_returns_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin@example.com"
    assert body["role"] == "ADMIN"
    uuid.UUID(body["id"])  # valid UUID


def test_refresh_rotates_session(client: TestClient, admin_user) -> None:
    login_resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    assert login_resp.status_code == 200
    old_cookie = login_resp.cookies.get("aigold_refresh_dev")
    assert old_cookie is not None

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    new_pair = refreshed.json()
    assert "refresh_token" not in new_pair
    new_cookie = refreshed.cookies.get("aigold_refresh_dev")
    assert new_cookie is not None and new_cookie != old_cookie

    # refresh token เดิมถูก revoke — replay ด้วย old cookie ใช้ซ้ำไม่ได้ (rotation)
    replay = client.post("/api/auth/refresh", cookies={"aigold_refresh_dev": old_cookie})
    assert replay.status_code == 401

    # ชุดใหม่ใช้ได้จริง
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_pair['access_token']}"})
    assert me.status_code == 200


def test_logout_revokes_sessions(client: TestClient, admin_user) -> None:
    login_resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    cookie = login_resp.cookies.get("aigold_refresh_dev")
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    # refresh หลัง logout = revoked
    replay = client.post("/api/auth/refresh", cookies={"aigold_refresh_dev": cookie})
    assert replay.status_code == 401


async def test_logout_with_expired_access_token_revokes_refresh_authority(
    client: TestClient, admin_user, db_session
) -> None:
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    refresh_token = login.cookies.get("aigold_refresh_dev")
    expired_access, _ = create_token(
        subject=str(admin_user.id),
        role=admin_user.role.value,
        token_type="access",
        secret_key=get_settings().secret_key,
        access_expire_minutes=-1,
    )

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {expired_access}"})
    assert logout.status_code == 200
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert refresh_token is not None
    assert not client.cookies.get("aigold_refresh_dev")
    session, _ = db_session
    stored = await session.scalar(
        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(refresh_token))
    )
    assert stored is not None and stored.revoked_at is not None
    assert client.post("/api/auth/refresh", cookies={"aigold_refresh_dev": refresh_token}).status_code == 401


def test_logout_without_access_token_revokes_refresh_authority(client: TestClient, admin_user) -> None:
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    refresh_token = login.cookies.get("aigold_refresh_dev")

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert refresh_token is not None
    assert client.post("/api/auth/refresh", cookies={"aigold_refresh_dev": refresh_token}).status_code == 401


def test_logout_with_malformed_access_token_revokes_refresh_authority(client: TestClient, admin_user) -> None:
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    refresh_token = login.cookies.get("aigold_refresh_dev")

    logout = client.post("/api/auth/logout", headers={"Authorization": "Bearer malformed.access.token"})
    assert logout.status_code == 200
    assert refresh_token is not None
    assert client.post("/api/auth/refresh", cookies={"aigold_refresh_dev": refresh_token}).status_code == 401


def test_logout_missing_or_invalid_refresh_cookie_is_bounded(client: TestClient, admin_user) -> None:
    client.cookies.clear()
    assert client.post("/api/auth/logout").status_code == 401

    invalid = client.post("/api/auth/logout", cookies={"aigold_refresh_dev": "not-a-jwt"})
    assert invalid.status_code == 401
    assert "Max-Age=0" in invalid.headers["set-cookie"]


def test_logout_rejects_valid_bearer_for_different_refresh_subject(client: TestClient, admin_user, trader_user) -> None:
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    refresh_token = login.cookies.get("aigold_refresh_dev")
    trader_access, _ = create_token(
        subject=str(trader_user.id),
        role=trader_user.role.value,
        token_type="access",
        secret_key=get_settings().secret_key,
    )

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {trader_access}"})
    assert logout.status_code == 401
    assert refresh_token is not None
    assert client.post("/api/auth/refresh", cookies={"aigold_refresh_dev": refresh_token}).status_code == 200


async def test_logout_refresh_jwt_session_subject_mismatch_is_terminal(
    client: TestClient, admin_user, trader_user, db_session
) -> None:
    mismatched_refresh, _ = create_token(
        subject=str(trader_user.id),
        role=trader_user.role.value,
        token_type="refresh",
        secret_key=get_settings().secret_key,
    )
    session, _ = db_session
    stored = RefreshSession(
        user_id=admin_user.id,
        family_id=uuid.uuid4(),
        refresh_token_hash=hash_refresh_token(mismatched_refresh),
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
    )
    session.add(stored)
    await session.commit()
    stored_id = stored.id

    logout = client.post("/api/auth/logout", cookies={"aigold_refresh_dev": mismatched_refresh})
    assert logout.status_code == 401
    assert "Max-Age=0" in logout.headers["set-cookie"]
    session.expire_all()
    stored = await session.get(RefreshSession, stored_id)
    assert stored is not None and stored.revoked_at is not None


def test_logout_origin_validation_precedes_refresh_session_mutation(client: TestClient, admin_user) -> None:
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    refresh_token = login.cookies.get("aigold_refresh_dev")

    missing_origin = client.post("/api/auth/logout", headers={"origin": ""})
    assert missing_origin.status_code == 403
    untrusted_origin = client.post("/api/auth/logout", headers={"origin": "https://attacker.example"})
    assert untrusted_origin.status_code == 403
    assert refresh_token is not None
    assert client.post("/api/auth/refresh", cookies={"aigold_refresh_dev": refresh_token}).status_code == 200


async def test_audit_log_records_login(client: TestClient, admin_user, db_session) -> None:
    from sqlalchemy import select

    from app.models import AuditLog

    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    session, _ = db_session
    result = await session.execute(select(AuditLog).where(AuditLog.action == "LOGIN"))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].correlation_id
