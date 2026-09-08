"""Opt-in PostgreSQL gate; never uses DATABASE_URL for integration test selection.

Set TEST_DATABASE_URL and TEST_DATABASE_DISPOSABLE=true. A unique owned schema
isolates migration up/down/up; no existing schema/table is dropped.
"""

import asyncio
import datetime as dt
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.event_loop import new_event_loop
from app.core.security import verify_password
from app.db.seed import seed_admin
from app.db.session import get_session_factory
from app.main import create_app
from app.models import AuditLog, RefreshSession, Role, User

pytestmark = pytest.mark.integration


def test_postgresql_migrations_auth_and_audit(monkeypatch, capfd):
    local_config = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
    raw_url = os.environ.get("TEST_DATABASE_URL", local_config.get("TEST_DATABASE_URL"))
    if not raw_url:
        pytest.skip("BLOCKED BY LOCAL POSTGRESQL: TEST_DATABASE_URL is not configured")
    disposable = os.environ.get("TEST_DATABASE_DISPOSABLE", local_config.get("TEST_DATABASE_DISPOSABLE"))
    if disposable != "true":
        pytest.skip("Set TEST_DATABASE_DISPOSABLE=true only for a disposable test database")

    monkeypatch.delenv("DATABASE_URL_OVERRIDE", raising=False)
    monkeypatch.setenv("DATABASE_URL", raw_url)
    get_settings.cache_clear()
    url = make_url(Settings(_env_file=None).database_url)
    connection_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    # The caller supplied a test DB. Only this newly created schema is modified.
    schema = "phase1_gate_" + uuid.uuid4().hex
    with psycopg.connect(connection_url, autocommit=True, connect_timeout=5) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            isolated = url.update_query_dict({"options": f"-csearch_path={schema}"})
            monkeypatch.setenv("DATABASE_URL", isolated.render_as_string(hide_password=False))
            get_settings.cache_clear()
            expected = {"users", "sessions", "accounts", "symbols", "audit_logs", "system_events"}
            for action, target in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
                result = subprocess.run(  # noqa: S603 — owned test schema, fixed commands
                    [sys.executable, "-m", "alembic", action, target],
                    cwd=Path(__file__).resolve().parents[2],
                    env=os.environ.copy(), capture_output=True, text=True, timeout=30,
                )
                # Avoid disclosing connection credentials from external driver errors.
                assert result.returncode == 0, f"Alembic {action} failed in isolated PostgreSQL schema"
                rows = conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                    (schema,),
                ).fetchall()
                actual = {row[0] for row in rows} - {"alembic_version"}
                assert actual == (set() if target == "base" else expected)
                if target == "head":
                    _verify_schema(conn, schema, expected)
                    sensitive = asyncio.run(_verify_auth(), loop_factory=new_event_loop)
                    captured = capfd.readouterr()
                    if any(value in captured.out + captured.err for value in sensitive):
                        pytest.fail("Sensitive authentication data appeared in captured logs", pytrace=False)
                else:
                    revision = conn.execute(
                        sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(schema))
                    ).fetchall()
                    assert revision == []
        finally:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            get_settings.cache_clear()


def _verify_schema(conn, schema, expected):
    revision = conn.execute(
        sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(schema))
    ).fetchone()
    assert revision == ("0001_initial",)
    indexes = {
        row[0]: row[1] for row in conn.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s", (schema,)
        ).fetchall()
    }
    for unique_index in ("ix_users_email", "ix_sessions_refresh_token_hash", "ix_symbols_name"):
        assert "UNIQUE INDEX" in indexes[unique_index]
    assert {"ix_accounts_user_id", "ix_sessions_user_id", "ix_audit_logs_ts", "ix_audit_logs_action"} <= indexes.keys()
    constraints = conn.execute(
        "SELECT table_name, constraint_type FROM information_schema.table_constraints WHERE table_schema = %s",
        (schema,),
    ).fetchall()
    assert {table for table, kind in constraints if kind == "PRIMARY KEY"} == expected | {"alembic_version"}
    assert {table for table, kind in constraints if kind == "FOREIGN KEY"} == {"sessions", "accounts"}


async def _verify_auth():
    app = create_app()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(32)
        await seed_admin("phase1@example.com", password)
        factory = get_session_factory()
        async with factory() as session:
            user = (await session.execute(select(User).where(User.email == "phase1@example.com"))).scalar_one()
            user_id = user.id
            assert user.password_hash != password
            assert verify_password(password, user.password_hash)
            password_hash = user.password_hash

        # Actual PostgreSQL transaction rollback, unique index and FK enforcement.
        async with factory() as session:
            session.add(User(email="rollback@example.com", password_hash=password_hash, role=Role.VIEWER))
            await session.flush()
            await session.rollback()
        async with factory() as session:
            rolled_back = await session.execute(select(User).where(User.email == "rollback@example.com"))
            assert rolled_back.scalar_one_or_none() is None
            session.add(User(email="phase1@example.com", password_hash=password_hash, role=Role.VIEWER))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
            session.add(RefreshSession(
                user_id=uuid.uuid4(), refresh_token_hash=secrets.token_hex(32),
                expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
            ))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/healthz")
            assert health.json()["trading_mode"] == "PAPER"
            assert health.json()["live_auto_trading"] is False
            ready = await client.get("/readyz")
            assert ready.status_code == 200
            assert ready.json()["checks"] == {"database": True, "redis": None}
            wrong = await client.post("/api/auth/login", json={
                "email": "phase1@example.com", "password": "incorrect-test-password",
            })
            unknown = await client.post("/api/auth/login", json={
                "email": "unknown@example.com", "password": "incorrect-test-password",
            })
            assert wrong.status_code == unknown.status_code == 401
            assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
            assert password not in wrong.text + unknown.text
            login = await client.post("/api/auth/login", json={"email": "phase1@example.com", "password": password})
            assert login.status_code == 200
            tokens = login.json()
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            assert (await client.get("/api/auth/me", headers=headers)).json()["role"] == "ADMIN"
            refreshed = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            assert refreshed.status_code == 200
            replay = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            assert replay.status_code == 401
            assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200
            replay = await client.post("/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
            assert replay.status_code == 401
        async with get_session_factory()() as session:
            audits = (await session.execute(select(AuditLog).where(AuditLog.action == "LOGIN"))).scalars().all()
            assert len(audits) == 1
            assert audits[0].user_id == user_id
            assert audits[0].entity_id == str(user_id)
            assert audits[0].entity == "user" and audits[0].source == "API"
            assert audits[0].ts.tzinfo is not None
            assert audits[0].correlation_id and audits[0].correlation_id != "-"
            assert audits[0].after == {"email": "phase1@example.com", "role": "ADMIN"}
            user = await session.get(User, user_id)
            assert user is not None and user.last_login_at is not None
            sessions = (await session.execute(select(RefreshSession).where(
                RefreshSession.user_id == user_id
            ))).scalars().all()
            assert len(sessions) == 2 and all(item.revoked_at for item in sessions)
            assert all(item.refresh_token_hash != tokens["refresh_token"] for item in sessions)
        return (password, tokens["access_token"], tokens["refresh_token"], get_settings().secret_key)
