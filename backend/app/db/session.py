"""Async engine + session factory (docs/02 §5, docs/04 §3 transaction boundary)."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"pool_pre_ping": True, "echo": False}
        # pool args ใช้ได้เฉพาะ dialect ที่มี connection pool ของตัวเอง (SQLite ใช้ StaticPool)
        if settings.database_url.startswith("postgresql"):
            kwargs.update(pool_size=10, max_overflow=10)
        _engine = create_async_engine(settings.database_url, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — 1 request = 1 session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
