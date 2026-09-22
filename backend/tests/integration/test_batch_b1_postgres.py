"""Real PostgreSQL acceptance for Batch B1 atomic refresh rotation."""

import asyncio
import datetime as dt
import os
import secrets
import uuid

import httpx
import pytest
from sqlalchemy import select, text
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
from app.services.auth_cookies import get_refresh_cookie_name
from app.services.refresh_sessions import (
    acquire_user_authority_lock,
    reread_refresh_session_state,
    user_authority_key,
)
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


def test_refresh_logout_serialization_prerequisites(isolated_postgres):  # noqa: F811
    """The authority design requires PostgreSQL READ COMMITTED and stable user keys."""
    conn, _schema = isolated_postgres
    assert conn.execute("SHOW transaction_isolation").fetchone() == ("read committed",)
    user_id = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
    assert user_authority_key(user_id) == user_authority_key(user_id)
    assert user_authority_key(user_id) != user_authority_key(uuid.uuid4())


async def _release_pair(client_a, client_b, cookie_name: str, token: str):
    release = asyncio.Event()

    async def send(client):
        await release.wait()
        return await client.post("/api/auth/refresh", cookies={cookie_name: token})

    first = asyncio.create_task(send(client_a))
    second = asyncio.create_task(send(client_b))
    await asyncio.sleep(0)
    release.set()
    return await asyncio.gather(first, second)


async def _verify_100_atomic_refresh_races() -> None:
    assert make_url(os.environ["DATABASE_URL"]).database != "ai_trading"
    app = create_app()
    cookie_name = get_refresh_cookie_name()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-race@example.com", password)
        transport_a = httpx.ASGITransport(app=app)
        transport_b = httpx.ASGITransport(app=app)
        headers = {"origin": "http://localhost:3000"}
        async with (
            httpx.AsyncClient(transport=transport_a, base_url="http://test", headers=headers) as client_a,
            httpx.AsyncClient(transport=transport_b, base_url="http://test", headers=headers) as client_b,
        ):
            for _ in range(100):
                client_a.cookies.clear()
                client_b.cookies.clear()
                login = await client_a.post(
                    "/api/auth/login",
                    json={"email": "batch-b1-race@example.com", "password": password},
                )
                assert login.status_code == 200
                assert "refresh_token" not in login.json()
                old_token = login.cookies.get(cookie_name)
                assert old_token is not None
                responses = await _release_pair(client_a, client_b, cookie_name, old_token)
                assert sorted(response.status_code for response in responses) == [200, 401]
                winner = next(response for response in responses if response.status_code == 200)
                failure = next(response for response in responses if response.status_code == 401)
                assert failure.json()["error"]["message"] == "Invalid refresh token"
                # Concurrency loser MUST NOT clear the cookie (winner's new cookie preserved)
                set_cookie_loser = failure.headers.get("set-cookie", "")
                assert "Max-Age=0" not in set_cookie_loser
                # Winner has received new rotated refresh token in cookie
                new_token = winner.cookies.get(cookie_name)
                assert new_token is not None and new_token != old_token

                factory = get_session_factory()
                async with factory() as session:
                    original = await session.scalar(
                        select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(old_token))
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


async def _active_authority_count(user_id: uuid.UUID) -> int:
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.scalars(
            select(RefreshSession.id).where(
                RefreshSession.user_id == user_id,
                RefreshSession.consumed_at.is_(None),
                RefreshSession.revoked_at.is_(None),
            )
        )
        return len(rows.all())


async def _verify_refresh_logout_serialization(monkeypatch, *, logout_first: bool) -> None:
    """Gate a real production mutation after its advisory lock, not a timing sleep."""
    app = create_app()
    cookie_name = get_refresh_cookie_name()
    held = asyncio.Event()
    release = asyncio.Event()
    password = secrets.token_urlsafe(24)

    if logout_first:
        original_revoke = auth.revoke_active_user_sessions

        async def gate_logout(session, *, user_id):
            held.set()
            await release.wait()
            return await original_revoke(session, user_id=user_id)

        monkeypatch.setattr(auth, "revoke_active_user_sessions", gate_logout)
    else:
        original_audit = audit.write_audit

        async def gate_refresh(session, **kwargs):
            result = await original_audit(session, **kwargs)
            if kwargs.get("action") == "TOKEN_REFRESH":
                held.set()
                await release.wait()
            return result

        monkeypatch.setattr(audit, "write_audit", gate_refresh)

    async with app.router.lifespan_context(app):
        await seed_admin("batch-b1-logout-race@example.com", password)
        headers = {"origin": "http://localhost:3000"}
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
            ) as login_client,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
            ) as refresh_client,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
            ) as logout_client,
        ):
            login = await login_client.post(
                "/api/auth/login", json={"email": "batch-b1-logout-race@example.com", "password": password}
            )
            assert login.status_code == 200
            original_token = login.cookies.get(cookie_name)
            assert original_token is not None
            factory = get_session_factory()
            async with factory() as session:
                user_id = await session.scalar(
                    select(RefreshSession.user_id).where(
                        RefreshSession.refresh_token_hash == hash_refresh_token(original_token)
                    )
                )
            assert user_id is not None

            if logout_first:
                first = asyncio.create_task(
                    logout_client.post("/api/auth/logout", cookies={cookie_name: original_token})
                )
                await asyncio.wait_for(held.wait(), timeout=5)
                second = asyncio.create_task(
                    refresh_client.post("/api/auth/refresh", cookies={cookie_name: original_token})
                )
            else:
                first = asyncio.create_task(
                    refresh_client.post("/api/auth/refresh", cookies={cookie_name: original_token})
                )
                await asyncio.wait_for(held.wait(), timeout=5)
                second = asyncio.create_task(
                    logout_client.post("/api/auth/logout", cookies={cookie_name: original_token})
                )
            release.set()
            first_response, second_response = await asyncio.gather(first, second)
            logout_response = first_response if logout_first else second_response
            refresh_response = second_response if logout_first else first_response
            assert logout_response.status_code == 200
            assert await _active_authority_count(user_id) == 0
            if refresh_response.status_code == 200:
                successor = refresh_response.cookies.get(cookie_name)
                assert successor is not None
                assert (
                    await refresh_client.post("/api/auth/refresh", cookies={cookie_name: successor})
                ).status_code == 401
            else:
                assert refresh_response.status_code == 401


def test_postgres_logout_first_serializes_refresh_authority(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_refresh_logout_serialization(monkeypatch, logout_first=True), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


def test_postgres_refresh_first_logout_revokes_successor(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_refresh_logout_serialization(monkeypatch, logout_first=False), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _create_race_clients(app, email: str, password: str):
    """Create independent browser clients and one refresh credential for real ASGI requests."""
    headers = {"origin": "http://localhost:3000"}
    clients = [
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers)
        for _ in range(3)
    ]
    login = await clients[0].post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    cookie_name = get_refresh_cookie_name()
    token = login.cookies.get(cookie_name)
    assert token is not None
    factory = get_session_factory()
    async with factory() as session:
        user_id = await session.scalar(
            select(RefreshSession.user_id).where(RefreshSession.refresh_token_hash == hash_refresh_token(token))
        )
    assert user_id is not None
    return clients, cookie_name, token, user_id


async def _close_clients(clients) -> None:
    for client in clients:
        await client.aclose()


async def _verify_true_concurrent_start(monkeypatch) -> None:
    """Both requests enter the production lock helper before the winning mutation proceeds."""
    app = create_app()
    entered = asyncio.Event()
    second_attempt = asyncio.Event()
    release = asyncio.Event()
    arrivals = 0
    original_lock = auth.acquire_user_authority_lock

    async def gate_lock(session, *, user_id):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 1:
            await original_lock(session, user_id=user_id)
            entered.set()
            await release.wait()
            return
        second_attempt.set()
        entered.set()
        return await original_lock(session, user_id=user_id)

    monkeypatch.setattr(auth, "acquire_user_authority_lock", gate_lock)
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-true-concurrent@example.com", password)
        clients, cookie_name, token, user_id = await _create_race_clients(
            app, "batch-b1-true-concurrent@example.com", password
        )
        try:
            start = asyncio.Event()

            async def refresh_request():
                await start.wait()
                return await clients[1].post("/api/auth/refresh", cookies={cookie_name: token})

            async def logout_request():
                await start.wait()
                return await clients[2].post("/api/auth/logout", cookies={cookie_name: token})

            refresh_task = asyncio.create_task(refresh_request())
            logout_task = asyncio.create_task(logout_request())
            start.set()
            await asyncio.wait_for(entered.wait(), timeout=5)
            await asyncio.wait_for(second_attempt.wait(), timeout=5)
            release.set()
            refresh_response, logout_response = await asyncio.gather(refresh_task, logout_task)
            assert logout_response.status_code == 200
            assert refresh_response.status_code in {200, 401}
            assert await _active_authority_count(user_id) == 0
            if refresh_response.status_code == 200:
                successor = refresh_response.cookies.get(cookie_name)
                assert successor is not None
                assert (await clients[1].post("/api/auth/refresh", cookies={cookie_name: successor})).status_code == 401
        finally:
            await _close_clients(clients)


def test_postgres_true_concurrent_refresh_logout_is_terminal(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_true_concurrent_start(monkeypatch), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _verify_long_lock_wait_preserves_concurrent_loser(monkeypatch) -> None:
    """The only elapsed wait is deliberate: it exceeds the five-second replay grace boundary."""
    app = create_app()
    winner_held = asyncio.Event()
    loser_waiting = asyncio.Event()
    release = asyncio.Event()
    lock_calls = 0

    async def gate_lock(session, *, user_id):
        nonlocal lock_calls
        lock_calls += 1
        # Test-only: separate the five-second authority timeout from the five-second
        # replay policy so real PostgreSQL can exercise a longer queued wait.
        await session.execute(text("SET LOCAL lock_timeout = '10s'"))
        if lock_calls == 1:
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": user_authority_key(user_id)})
            winner_held.set()
            await release.wait()
            return
        loser_waiting.set()
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": user_authority_key(user_id)})

    monkeypatch.setattr(auth, "acquire_user_authority_lock", gate_lock)
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-long-wait@example.com", password)
        clients, cookie_name, token, _user_id = await _create_race_clients(
            app, "batch-b1-long-wait@example.com", password
        )
        try:
            winner = asyncio.create_task(clients[1].post("/api/auth/refresh", cookies={cookie_name: token}))
            await asyncio.wait_for(winner_held.wait(), timeout=5)
            loser = asyncio.create_task(clients[2].post("/api/auth/refresh", cookies={cookie_name: token}))
            await asyncio.wait_for(loser_waiting.wait(), timeout=5)
            await asyncio.sleep(5.2)
            release.set()
            winner_response, loser_response = await asyncio.gather(winner, loser)
            assert winner_response.status_code == 200
            assert loser_response.status_code == 401
            assert "Max-Age=0" not in loser_response.headers.get("set-cookie", "")
            successor = winner_response.cookies.get(cookie_name)
            assert successor is not None
            assert (await clients[1].post("/api/auth/refresh", cookies={cookie_name: successor})).status_code == 200
        finally:
            await _close_clients(clients)


def test_postgres_lock_wait_beyond_grace_preserves_concurrent_loser(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_long_lock_wait_preserves_concurrent_loser(monkeypatch), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _verify_cross_user_isolation(monkeypatch) -> None:
    app = create_app()
    held = asyncio.Event()
    release = asyncio.Event()
    held_user_id = None
    original_lock = auth.acquire_user_authority_lock

    async def gate_lock(session, *, user_id):
        nonlocal held_user_id
        await original_lock(session, user_id=user_id)
        if held_user_id is None:
            held_user_id = user_id
            held.set()
            await release.wait()

    monkeypatch.setattr(auth, "acquire_user_authority_lock", gate_lock)
    async with app.router.lifespan_context(app):
        password_a, password_b = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        await seed_admin("batch-b1-user-a@example.com", password_a)
        await seed_admin("batch-b1-user-b@example.com", password_b)
        clients_a, cookie_name, token_a, user_a = await _create_race_clients(
            app, "batch-b1-user-a@example.com", password_a
        )
        clients_b, _cookie_name, token_b, user_b = await _create_race_clients(
            app, "batch-b1-user-b@example.com", password_b
        )
        try:
            assert user_authority_key(user_a) != user_authority_key(user_b)
            refresh_a = asyncio.create_task(clients_a[1].post("/api/auth/refresh", cookies={cookie_name: token_a}))
            await asyncio.wait_for(held.wait(), timeout=5)
            refresh_b = await asyncio.wait_for(
                clients_b[1].post("/api/auth/refresh", cookies={cookie_name: token_b}), timeout=2
            )
            assert refresh_b.status_code == 200
            assert not refresh_a.done()
            release.set()
            assert (await refresh_a).status_code == 200
            assert await _active_authority_count(user_a) == 1
            assert await _active_authority_count(user_b) == 1
        finally:
            await _close_clients(clients_a)
            await _close_clients(clients_b)


def test_postgres_cross_user_authority_locks_are_isolated(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_cross_user_isolation(monkeypatch), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _verify_identity_map_reread() -> None:
    """A deliberately stale ORM entity cannot influence the scalar post-lock observation."""
    app = create_app()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-identity-map@example.com", password)
        clients, cookie_name, token, user_id = await _create_race_clients(
            app, "batch-b1-identity-map@example.com", password
        )
        try:
            factory = get_session_factory()
            async with factory() as stale_session:
                original = await stale_session.scalar(
                    select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token))
                )
                assert original is not None and original.consumed_at is None
                winner = await clients[1].post("/api/auth/refresh", cookies={cookie_name: token})
                assert winner.status_code == 200
                # The ORM object intentionally remains stale, proving the test exercises identity-map risk.
                assert original.consumed_at is None
                await acquire_user_authority_lock(stale_session, user_id=user_id)
                fresh = await reread_refresh_session_state(stale_session, session_id=original.id)
                assert fresh is not None and fresh.consumed_at is not None
                assert fresh.revoked_at is None
                await stale_session.rollback()
        finally:
            await _close_clients(clients)


def test_postgres_post_lock_scalar_reread_defeats_stale_identity_map(isolated_postgres):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    try:
        asyncio.run(_verify_identity_map_reread(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _verify_browser_response_ordering(monkeypatch) -> None:
    """Applying a stale refresh Set-Cookie after logout cannot restore server authority."""
    app = create_app()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-response-order@example.com", password)
        clients, cookie_name, token, user_id = await _create_race_clients(
            app, "batch-b1-response-order@example.com", password
        )
        try:
            refresh = await clients[1].post("/api/auth/refresh", cookies={cookie_name: token})
            assert refresh.status_code == 200
            successor = refresh.cookies.get(cookie_name)
            assert successor is not None
            logout = await clients[2].post("/api/auth/logout", cookies={cookie_name: token})
            # Logout presents the concurrently consumed original authority, then revokes the successor.
            assert logout.status_code == 200
            assert await _active_authority_count(user_id) == 0
            stale_cookie_application = await clients[1].post("/api/auth/refresh", cookies={cookie_name: successor})
            assert stale_cookie_application.status_code == 401
            assert "Max-Age=0" in stale_cookie_application.headers.get("set-cookie", "")
        finally:
            await _close_clients(clients)


def test_postgres_browser_response_ordering_cannot_restore_authority(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_browser_response_ordering(monkeypatch), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _verify_lock_timeout_fails_closed() -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-lock-timeout@example.com", password)
        clients, cookie_name, token, user_id = await _create_race_clients(
            app, "batch-b1-lock-timeout@example.com", password
        )
        try:
            factory = get_session_factory()
            async with factory() as holder:
                await acquire_user_authority_lock(holder, user_id=user_id)
                timed_out = await clients[1].post("/api/auth/refresh", cookies={cookie_name: token})
                assert timed_out.status_code == 500
                await holder.rollback()
            async with factory() as session:
                original = await session.scalar(
                    select(RefreshSession).where(RefreshSession.refresh_token_hash == hash_refresh_token(token))
                )
                assert original is not None and original.consumed_at is None and original.revoked_at is None
                family = (
                    await session.scalars(select(RefreshSession).where(RefreshSession.family_id == original.family_id))
                ).all()
                assert len(family) == 1
                refresh_audits = (
                    await session.scalars(
                        select(AuditLog).where(AuditLog.action == "TOKEN_REFRESH", AuditLog.entity_id == str(user_id))
                    )
                ).all()
                assert refresh_audits == []
            assert (await clients[1].post("/api/auth/refresh", cookies={cookie_name: token})).status_code == 200
        finally:
            await _close_clients(clients)


def test_postgres_authority_lock_timeout_fails_closed(isolated_postgres):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    try:
        asyncio.run(_verify_lock_timeout_fails_closed(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)


async def _verify_postgres_replay_and_rollback(monkeypatch) -> None:
    app = create_app()
    cookie_name = get_refresh_cookie_name()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(24)
        await seed_admin("batch-b1-replay@example.com", password)
        headers = {"origin": "http://localhost:3000"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
        ) as client:
            login = await client.post(
                "/api/auth/login", json={"email": "batch-b1-replay@example.com", "password": password}
            )
            assert login.status_code == 200
            assert "refresh_token" not in login.json()
            token_a = login.cookies.get(cookie_name)
            assert token_a is not None

            # 1. Normal rotation via cookie
            refresh = await client.post("/api/auth/refresh", cookies={cookie_name: token_a})
            assert refresh.status_code == 200
            assert "refresh_token" not in refresh.json()
            token_b = refresh.cookies.get(cookie_name)
            assert token_b is not None and token_b != token_a

            # 2. Immediate replay of token_a (within 5s grace window)
            # Concurrency loser: 401, but does NOT clear cookie
            immediate = await client.post("/api/auth/refresh", cookies={cookie_name: token_a})
            assert immediate.status_code == 401
            assert "Max-Age=0" not in immediate.headers.get("set-cookie", "")

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

            # 3. Late replay of token_a (> 5s grace window) -> family revocation & terminal cookie clear
            later = await client.post("/api/auth/refresh", cookies={cookie_name: token_a})
            assert later.status_code == 401
            assert "Max-Age=0" in later.headers.get("set-cookie", "")

            # token_b was revoked as part of the family revocation
            later_b = await client.post("/api/auth/refresh", cookies={cookie_name: token_b})
            assert later_b.status_code == 401
            assert "Max-Age=0" in later_b.headers.get("set-cookie", "")

            # 4. Rollback injection
            rollback_login = await client.post(
                "/api/auth/login", json={"email": "batch-b1-replay@example.com", "password": password}
            )
            assert rollback_login.status_code == 200
            rollback_token = rollback_login.cookies.get(cookie_name)
            assert rollback_token is not None

            original_write = audit.write_audit
            failed = False

            async def fail_once(session, **kwargs):
                nonlocal failed
                if kwargs.get("action") == "TOKEN_REFRESH" and not failed:
                    failed = True
                    raise RuntimeError("controlled-postgres-b1-rollback")
                return await original_write(session, **kwargs)

            monkeypatch.setattr(audit, "write_audit", fail_once)
            assert (await client.post("/api/auth/refresh", cookies={cookie_name: rollback_token})).status_code == 500

            async with factory() as session:
                stored = await session.scalar(
                    select(RefreshSession).where(
                        RefreshSession.refresh_token_hash == hash_refresh_token(rollback_token)
                    )
                )
                assert stored is not None and stored.consumed_at is None and stored.revoked_at is None
                family = (
                    await session.scalars(select(RefreshSession).where(RefreshSession.family_id == stored.family_id))
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

            assert (await client.post("/api/auth/refresh", cookies={cookie_name: rollback_token})).status_code == 200


def test_postgres_replay_grace_family_revocation_and_rollback(isolated_postgres, monkeypatch):  # noqa: F811
    _conn, _schema = isolated_postgres
    _alembic("upgrade", "head")
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(per_minute=1000, max_keys=10000))
    try:
        asyncio.run(_verify_postgres_replay_and_rollback(monkeypatch), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine(), loop_factory=new_event_loop)
