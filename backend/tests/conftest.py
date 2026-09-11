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
        import datetime as dt
        from decimal import Decimal

        from app.models.risk import (
            AccountSnapshotRecord,
            KillSwitchRecord,
            RiskPolicyRecord,
            SymbolSpecificationRecord,
        )
        from app.services.risk.domain import RiskPolicy, default_gold_spec

        now = dt.datetime.now(dt.UTC)
        bootstrap_ks = KillSwitchRecord(
            id="ks_test_bootstrap",
            state="INACTIVE",
            trigger_type="MANUAL",
            reason_th="ระบบพร้อมทำงานตามปกติ",
            activated_at=dt.datetime(2020, 1, 1, 0, 0, 0, tzinfo=dt.UTC),
            activated_by="system",
            policy_version="risk-policy-1.0.0",
            payload={"source": "test_bootstrap"},
        )
        session.add(bootstrap_ks)

        pol = RiskPolicy()
        policy_rec = RiskPolicyRecord(
            id="pol_test_bootstrap",
            version="risk-policy-1.0.0",
            is_active=True,
            created_at=dt.datetime(2020, 1, 1, 0, 0, 0, tzinfo=dt.UTC),
            payload=pol.model_dump(mode="json"),
        )
        session.add(policy_rec)

        snap = AccountSnapshotRecord(
            id="snap_default_paper_account_init",
            account_id="default_paper_account",
            balance=Decimal("10000.00"),
            equity=Decimal("10000.00"),
            free_margin=Decimal("10000.00"),
            daily_realized_pnl=Decimal("0.00"),
            weekly_realized_pnl=Decimal("0.00"),
            peak_equity=Decimal("10000.00"),
            open_risk_pct=Decimal("0.0000"),
            reserved_risk_pct=Decimal("0.0000"),
            consecutive_losses=0,
            trading_mode="PAPER",
            source="CONFIGURED_PAPER",
            as_of=now,
            payload={
                "id": "snap_default_paper_account_init",
                "account_id": "default_paper_account",
                "balance": "10000.00",
                "equity": "10000.00",
                "free_margin": "10000.00",
                "daily_realized_pnl": "0.00",
                "weekly_realized_pnl": "0.00",
                "peak_equity": "10000.00",
                "open_risk_pct": "0.0000",
                "reserved_risk_pct": "0.0000",
                "consecutive_losses": 0,
                "trading_mode": "PAPER",
                "source": "CONFIGURED_PAPER",
                "as_of": now.isoformat(),
            },
        )
        session.add(snap)

        spec = default_gold_spec(source="mt5_demo_iux", observed_at=now)
        spec_rec = SymbolSpecificationRecord(
            id="sym_xauusd_mt5_demo_iux_seed",
            symbol="XAUUSD",
            source="mt5_demo_iux",
            tick_size=spec.tick_size,
            tick_value=spec.tick_value,
            contract_size=spec.contract_size,
            volume_min=spec.volume_min,
            volume_max=spec.volume_max,
            volume_step=spec.volume_step,
            digits=spec.digits,
            observed_at=now,
            payload=spec.model_dump(mode="json"),
        )
        session.add(spec_rec)

        await session.commit()
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
    user = await create_user(session, email="admin@example.com", password="admin-pass-123", role=Role.ADMIN)
    from app.models.account import Account, TradingMode

    acc = Account(
        name="default_paper_account",
        user_id=user.id,
        trading_mode=TradingMode.PAPER,
        starting_balance=10000.00,
        base_currency="USD",
        is_active=True,
    )
    session.add(acc)
    await session.commit()
    return user


@pytest_asyncio.fixture
async def trader_user(db_session) -> User:
    session, _ = db_session
    user = await create_user(session, email="trader@example.com", password="trader-pass-123", role=Role.TRADER)
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
