"""Batch B1 auth semantics independent of PostgreSQL concurrency proof."""

import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_token, decode_token
from app.models import AuditLog, RefreshSession, Role
from app.services import audit
from app.services.users import hash_refresh_token


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
        headers={"user-agent": "batch-b1-test"},
    )
    assert response.status_code == 200
    return response.json()


async def _session_for_token(db_session, token: str) -> RefreshSession:
    session, _ = db_session
    session.expire_all()
    stored = await session.scalar(
        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token))
    )
    assert stored is not None
    return stored


async def test_login_and_successor_session_family_metadata(client, admin_user, db_session) -> None:
    pair = _login(client)
    original = await _session_for_token(db_session, pair["refresh_token"])
    family_id = original.family_id
    assert family_id
    assert original.consumed_at is None and original.revoked_at is None
    assert original.user_agent == "batch-b1-test"

    refreshed = client.post(
        "/api/auth/refresh",
        json={"refresh_token": pair["refresh_token"]},
        headers={"user-agent": "batch-b1-refresh"},
    )
    assert refreshed.status_code == 200
    original = await _session_for_token(db_session, pair["refresh_token"])
    assert original.consumed_at is not None and original.revoked_at is None
    successor = await _session_for_token(db_session, refreshed.json()["refresh_token"])
    assert successor.family_id == family_id
    assert successor.consumed_at is None and successor.revoked_at is None
    assert successor.user_agent == "batch-b1-refresh"


async def test_immediate_reuse_rejected_without_family_revocation(client, admin_user, db_session) -> None:
    pair = _login(client)
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 200

    replay = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["error"]["message"] == "Invalid refresh token"

    successor = await _session_for_token(db_session, refreshed.json()["refresh_token"])
    assert successor.consumed_at is None and successor.revoked_at is None
    session, _ = db_session
    reuse = (
        await session.scalars(select(AuditLog).where(AuditLog.action == "REFRESH_REUSE"))
    ).all()
    assert reuse and reuse[-1].reason == "concurrent_rejection_within_grace"


async def test_later_replay_revokes_active_family(client, admin_user, db_session) -> None:
    pair = _login(client)
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 200

    original = await _session_for_token(db_session, pair["refresh_token"])
    original.consumed_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
    session, _ = db_session
    await session.commit()

    replay = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert replay.status_code == 401
    successor = await _session_for_token(db_session, refreshed.json()["refresh_token"])
    assert successor.revoked_at is not None
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]}
    ).status_code == 401
    actions = (
        await session.scalars(select(AuditLog.action).where(AuditLog.action.in_(("REFRESH_REUSE", "SESSION_REVOKED"))))
    ).all()
    assert "REFRESH_REUSE" in actions and "SESSION_REVOKED" in actions


async def test_refresh_failure_rolls_back_consume_and_successor(
    client, admin_user, db_session, monkeypatch
) -> None:
    pair = _login(client)
    original_write = audit.write_audit
    failed = False

    async def fail_once(session, **kwargs):
        nonlocal failed
        if kwargs.get("action") == "TOKEN_REFRESH" and not failed:
            failed = True
            raise RuntimeError("controlled-b1-rollback")
        return await original_write(session, **kwargs)

    monkeypatch.setattr(audit, "write_audit", fail_once)
    response = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 500

    original = await _session_for_token(db_session, pair["refresh_token"])
    assert original.consumed_at is None and original.revoked_at is None
    session, _ = db_session
    rows = (
        await session.scalars(select(RefreshSession).where(RefreshSession.family_id == original.family_id))
    ).all()
    assert len(rows) == 1
    assert not (
        await session.scalars(select(AuditLog).where(AuditLog.action == "TOKEN_REFRESH"))
    ).all()

    assert client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401


async def test_inactive_user_gets_no_successor_and_family_is_terminal(client, admin_user, db_session) -> None:
    pair = _login(client)
    session, _ = db_session
    admin_user.is_active = False
    await session.commit()

    response = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid refresh token"
    original = await _session_for_token(db_session, pair["refresh_token"])
    rows = (
        await session.scalars(select(RefreshSession).where(RefreshSession.family_id == original.family_id))
    ).all()
    assert len(rows) == 1 and rows[0].consumed_at is not None
    assert (
        await session.scalars(select(AuditLog).where(AuditLog.action == "SESSION_REVOKED"))
    ).all()


async def test_refresh_uses_current_database_role(client, admin_user, db_session) -> None:
    pair = _login(client)
    session, _ = db_session
    admin_user.role = Role.VIEWER
    await session.commit()

    response = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 200
    claims = decode_token(response.json()["access_token"], get_settings().secret_key, expected_type="access")
    assert claims["role"] == "VIEWER"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["role"] == "VIEWER"


async def test_jwt_session_user_mismatch_fails_closed(client, admin_user, trader_user, db_session) -> None:
    settings = get_settings()
    token, _ = create_token(
        subject=str(trader_user.id),
        role=trader_user.role.value,
        token_type="refresh",
        secret_key=settings.secret_key,
        refresh_expire_days=1,
    )
    family_id = uuid.uuid4()
    session, _ = db_session
    session.add(
        RefreshSession(
            user_id=admin_user.id,
            family_id=family_id,
            refresh_token_hash=hash_refresh_token(token),
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
        )
    )
    await session.commit()

    response = client.post("/api/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401
    stored = await _session_for_token(db_session, token)
    assert stored.consumed_at is not None
    assert (
        await session.scalars(select(AuditLog).where(AuditLog.action == "SESSION_REVOKED"))
    ).all()


async def test_invalid_refresh_conditions_share_generic_contract(client, admin_user, db_session) -> None:
    expected = {"code": "AUTH_FAILED", "message": "Invalid refresh token"}
    malformed = client.post("/api/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert {k: malformed.json()["error"][k] for k in expected} == expected

    unknown, _ = create_token(
        subject=str(admin_user.id),
        role=admin_user.role.value,
        token_type="refresh",
        secret_key=get_settings().secret_key,
    )
    unknown_response = client.post("/api/auth/refresh", json={"refresh_token": unknown})
    assert {k: unknown_response.json()["error"][k] for k in expected} == expected

    for field, value in (
        ("expires_at", dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)),
        ("revoked_at", dt.datetime.now(dt.UTC)),
    ):
        pair = _login(client)
        stored = await _session_for_token(db_session, pair["refresh_token"])
        setattr(stored, field, value)
        session, _ = db_session
        await session.commit()
        response = client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert {k: response.json()["error"][k] for k in expected} == expected
