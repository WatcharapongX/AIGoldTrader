"""Authentication flow — TASK-016 DoD evidence."""

import uuid

from fastapi.testclient import TestClient


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


async def test_audit_log_records_login(client: TestClient, admin_user, db_session) -> None:
    from sqlalchemy import select

    from app.models import AuditLog

    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-pass-123"})
    session, _ = db_session
    result = await session.execute(select(AuditLog).where(AuditLog.action == "LOGIN"))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].correlation_id
