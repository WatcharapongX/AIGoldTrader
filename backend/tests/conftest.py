"""Test fixtures — SQLite in-memory + fakeredis (ไม่ต้องมี PostgreSQL/Redis จริงเพื่อรัน unit tests)."""

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeredis_aioredis
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models import Role, User
from app.services import redis_client
from app.services.users import create_user


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[tuple]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_ENABLED", "true")
    get_settings.cache_clear()
    client = fakeredis_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "_client", client)
    yield client
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(client.aclose())


@pytest.fixture
def client(db_session, fake_redis) -> TestClient:
    """TestClient ที่ผูก get_session เข้ากับ test DB (dependency override)."""
    _, factory = db_session

    async def _override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session) -> User:
    session, _ = db_session
    user = await create_user(
        session, email="admin@example.com", password="admin-pass-123", role=Role.ADMIN
    )
    await session.commit()
    return user


@pytest_asyncio.fixture
async def trader_user(db_session) -> User:
    session, _ = db_session
    user = await create_user(
        session, email="trader@example.com", password="trader-pass-123", role=Role.TRADER
    )
    await session.commit()
    return user


@pytest.fixture
def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    """Login ผ่าน API จริงเพื่อได้ access token (ทดสอบ path ทั้งเส้น)."""
    from app.db.session import get_session as _get_session  # noqa: F401

    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch, request):
    """ตั้งค่า test-safe settings และเคลียร์ cache ทุก test."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-unit-tests-only")
    if request.node.get_closest_marker("live_external") is None:
        monkeypatch.setenv("MARKET_DATA_PROVIDER", "simulated")
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setenv("LIVE_AUTO_TRADING", "false")
    monkeypatch.setenv("REDIS_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL_OVERRIDE", "sqlite+aiosqlite:///:memory:")
    from app.api.auth import _auth_limiter

    _auth_limiter.reset()
    get_settings.cache_clear()
    yield
    _auth_limiter.reset()
    get_settings.cache_clear()
