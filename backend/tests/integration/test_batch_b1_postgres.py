"""Real PostgreSQL acceptance for Batch B1 atomic refresh rotation."""

import asyncio
import datetime as dt
import os
import secrets
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.api import auth
from app.core.event_loop import new_event_loop
from app.core.rate_limit import RateLimiter
from app.db.seed import seed_admin
from app.db.session import dispose_engine, get_session_factory
from app.main import create_app
from app.models import AuditLog, RefreshSession
from app.services import audit
from app.services.users import hash_refresh_token

pytestmark = pytest.mark.integration


def test_0016_refresh_family_migration_and_legacy_cutover(isolated_postgres):  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(f'SET search_path TO "{schema}"')  # noqa: S608 — generated owned schema fixture
    _alembic("upgrade", "0015_batch_a3_risk_account_fk")

    user_id = uuid.uuid4()
    active_id = uuid.uuid4()
    historical_id = uuid.uuid4()
    historical_revoked = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    conn.execute(
        "INSERT INTO users (id,email,password_hash,role) VALUES (%s,%s,'fixture','VIEWER')",
        (user_id, f"batch-b1-{uuid.uuid4().hex}@example.com"),
    )
    conn.execute(
        "INSERT INTO sessions (id,user_id,refresh_token_hash,expires_at) VALUES (%s,%s,%s,now()+interval '1 day')",
        (active_id, user_id, secrets.token_hex(32)),
    )
    conn.execute(
        "INSERT INTO sessions (id,user_id,refresh_token_hash,expires_at,revoked_at) "
        "VALUES (%s,%s,%s,now()+interval '1 day',%s)",
        (historical_id, user_id, secrets.token_hex(32), historical_revoked),
    )

    _alembic("upgrade", "0016_batch_b_refresh_families")
    rows = conn.execute(
        "SELECT id,family_id,consumed_at,revoked_at FROM sessions WHERE user_id=%s ORDER BY id",
        (user_id,),
    ).fetchall()
    assert len(rows) == 2
    by_id = {row[0]: row for row in rows}
    assert by_id[active_id][1] == active_id
    assert by_id[historical_id][1] == historical_id
    assert all(row[2] is None for row in rows)
    assert by_id[active_id][3] is not None
    assert by_id[historical_id][3] == historical_revoked

    columns = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT column_name,is_nullable,data_type FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name='sessions' AND column_name IN ('family_id','consumed_at')",
            (schema,),
        ).fetchall()
    }
    assert columns == {"family_id": ("NO", "uuid"), "consumed_at": ("YES", "timestamp with time zone")}
    indexes = {
        row[0] for row in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname=%s", (schema,)).fetchall()
    }
    assert "ix_sessions_family_id" in indexes
    _alembic("check")


async def _release_pair(client_a, client_b, token):
    release = asyncio.Event()

    async def send(client):
        await release.wait()
        return await client.post("/api/auth/refresh", json={"refresh_token": token})

    first = asyncio.create_task(send(client_a))
    second = asyncio.create_task(send(client_b))
    await asyncio.sleep(0)
    release.set()
    return await asyncio.gather(first, second)


async def _verify_100_atomic_refresh_races() -> None:
    assert make_url(os.environ["DATABASE_URL"]).database != "ai_trading"
    app = create_app()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-race@example.com", password)
        transport_a = httpx.ASGITransport(app=app)
        transport_b = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport_a, base_url="http://test") as client_a,
            httpx.AsyncClient(transport=transport_b, base_url="http://test") as client_b,
        ):
            for _ in range(100):
                login = await client_a.post(
                    "/api/auth/login",
                    json={"email": "batch-b1-race@example.com", "password": password},
                )
                assert login.status_code == 200
                old_token = login.json()["refresh_token"]
                responses = await _release_pair(client_a, client_b, old_token)
                assert sorted(response.status_code for response in responses) == [200, 401]
                failure = next(response for response in responses if response.status_code == 401)
                assert failure.json()["error"]["message"] == "Invalid refresh token"

                factory = get_session_factory()
                async with factory() as session:
                    original = await session.scalar(
                        select(RefreshSession).where(
                            RefreshSession.refresh_token_hash == hash_refresh_token(old_token)
                        )
                    )
                    assert original is not None and original.consumed_at is not None
                    family = (
                        await session.scalars(
                            select(RefreshSession).where(RefreshSession.family_id == original.family_id)
                        )
                    ).all()
                    active = [item for item in family if item.consumed_at is None and item.revoked_at is None]
                    assert len(family) == 2
                    assert len(active) == 1


def test_atomic_refresh_http_concurrency_100_iterations(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=10000, max_keys=10000))
    try:
        asyncio.run(_verify_100_atomic_refresh_races(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _verify_postgres_replay_and_rollback(monkeypatch) -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-replay@example.com", password)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            login = await client.post(
                "/api/auth/login", json={"email": "batch-b1-replay@example.com", "password": password}
            )
            token_a = login.json()["refresh_token"]
            refresh = await client.post("/api/auth/refresh", json={"refresh_token": token_a})
            assert refresh.status_code == 200
            token_b = refresh.json()["refresh_token"]

            immediate = await client.post("/api/auth/refresh", json={"refresh_token": token_a})
            assert immediate.status_code == 401
            factory = get_session_factory()
            async with factory() as session:
                session_a = await session.scalar(
                    select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token_a))
                )
                session_b = await session.scalar(
                    select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token_b))
                )
                assert session_a is not None and session_b is not None and session_b.revoked_at is None
                session_a.consumed_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
                await session.commit()

            later = await client.post("/api/auth/refresh", json={"refresh_token": token_a})
            assert later.status_code == 401
            assert (await client.post("/api/auth/refresh", json={"refresh_token": token_b})).status_code == 401

            rollback_login = await client.post(
                "/api/auth/login", json={"email": "batch-b1-replay@example.com", "password": password}
            )
            rollback_token = rollback_login.json()["refresh_token"]
            original_write = audit.write_audit
            failed = False

            async def fail_once(session, **kwargs):
                nonlocal failed
                if kwargs.get("action") == "TOKEN_REFRESH" and not failed:
                    failed = True
                    raise RuntimeError("controlled-postgres-b1-rollback")
                return await original_write(session, **kwargs)

            monkeypatch.setattr(audit, "write_audit", fail_once)
            assert (
                await client.post("/api/auth/refresh", json={"refresh_token": rollback_token})
            ).status_code == 500
            async with factory() as session:
                stored = await session.scalar(
                    select(RefreshSession).where(
                        RefreshSession.refresh_token_hash == hash_refresh_token(rollback_token)
                    )
                )
                assert stored is not None and stored.consumed_at is None and stored.revoked_at is None
                family = (
                    await session.scalars(
                        select(RefreshSession).where(RefreshSession.family_id == stored.family_id)
                    )
                ).all()
                assert len(family) == 1
                audits = (
                    await session.scalars(
                        select(AuditLog).where(
                            AuditLog.action == "TOKEN_REFRESH", AuditLog.entity_id == str(stored.user_id)
                        )
                    )
                ).all()
                # One successful audit belongs to A -> B; none was added for the failed family.
                assert len(audits) == 1
            assert (
                await client.post("/api/auth/refresh", json={"refresh_token": rollback_token})
            ).status_code == 200


def test_postgres_replay_grace_family_revocation_and_rollback(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_postgres_replay_and_rollback(monkeypatch), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)
