"""Native DEV regressions: config boundaries, disabled Redis, Windows and PostgreSQL DDL."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.core.event_loop import new_event_loop
from app.main import create_app
from app.services import redis_client


def test_database_url_normalizes_driver_and_preserves_encoded_password(monkeypatch):
    monkeypatch.delenv("DATABASE_URL_OVERRIDE")
    monkeypatch.setenv("DATABASE_URL", "postgresql://dev:p%40ss%25word@localhost:5544/testdb")
    settings = Settings(_env_file=None)
    url = make_url(settings.database_url)
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.database, url.username, url.password) == (
        "localhost",
        5544,
        "testdb",
        "dev",
        "p@ss%word",
    )
    assert "p%40ss" not in repr(settings)


def test_compose_fields_escape_special_credentials(monkeypatch):
    monkeypatch.delenv("DATABASE_URL_OVERRIDE")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        _env_file=None,
        postgres_host="localhost",
        postgres_port=5544,
        postgres_db="testdb",
        postgres_user="dev@user",
        postgres_password="p@ss%:/word",
    )
    url = make_url(settings.database_url)
    assert url.username == "dev@user"
    assert url.password == "p@ss%:/word"


@pytest.mark.parametrize("value", ["bad-secret-url", "sqlite:///data.db", "postgresql://dev:secret@localhost/db"])
def test_invalid_database_url_fails_without_echoing_secret(monkeypatch, value):
    monkeypatch.delenv("DATABASE_URL_OVERRIDE")
    monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(ValueError, match="DATABASE_URL") as error:
        _ = Settings(_env_file=None).database_url
    assert value not in str(error.value)


def test_missing_database_configuration_has_no_implicit_credentials(monkeypatch):
    for name in (
        "DATABASE_URL_OVERRIDE",
        "DATABASE_URL",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="Set DATABASE_URL"):
        _ = Settings(_env_file=None).database_url


async def test_disabled_redis_never_creates_connection(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Disabled Redis must not attempt a connection")

    monkeypatch.setattr(redis_client.aioredis, "from_url", unexpected)
    monkeypatch.setattr(redis_client, "_client", None)
    assert await redis_client.redis_health() is None
    assert await redis_client.cache_get_json("key") is None
    assert await redis_client.cache_set_json("key", "{}") is False
    assert await redis_client.publish("channel", {"event": "test"}) is False
    with pytest.raises(RuntimeError, match="disabled"):
        redis_client.PubSubManager()


def test_native_health_without_redis_and_database_failure(monkeypatch, caplog):
    import app.api.health as health

    with TestClient(create_app()) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["checks"] == {"database": True, "redis": None}
        assert ready.json()["redis_enabled"] is False

        def unavailable():
            raise RuntimeError("private-database-password")

        monkeypatch.setattr(health, "get_engine", unavailable)
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["checks"]["database"] is False
        assert "private-database-password" not in response.text + caplog.text
        assert client.get("/healthz").status_code == 200


async def test_enabled_unavailable_redis_reports_failure(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "true")
    get_settings.cache_clear()
    failed = AsyncMock()
    failed.ping.side_effect = ConnectionError("unavailable")
    monkeypatch.setattr(redis_client, "_client", failed)
    assert await redis_client.redis_health() is False


@pytest.mark.parametrize("secret", ["", "short", "change-me-generate-a-long-random-string"])
def test_runtime_rejects_missing_or_placeholder_secret(monkeypatch, secret):
    monkeypatch.setenv("SECRET_KEY", secret)
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="SECRET_KEY"):
        with TestClient(create_app()):
            pass


def test_windows_db_loop_supports_io_watchers():
    loop = new_event_loop()
    try:
        if sys.platform == "win32":
            assert isinstance(loop, asyncio.SelectorEventLoop)
        from uvicorn import Config

        for reload in (False, True):
            config = Config(
                "app.main:app",
                loop="app.core.event_loop:new_event_loop",
                reload=reload,
                proxy_headers=False,
            )
            assert config.get_loop_factory() is new_event_loop
    finally:
        loop.close()


def test_postgresql_offline_migration_handles_percent_encoded_password():
    backend_dir = Path(__file__).resolve().parent.parent
    env = {**os.environ, "DATABASE_URL": "postgresql://dev:p%40ss%25word@localhost:5544/testdb"}
    env.pop("DATABASE_URL_OVERRIDE", None)
    result = subprocess.run(  # noqa: S603 — offline SQL only, never connects
        [sys.executable, "-m", "alembic", "-c", str(backend_dir / "alembic.ini"), "upgrade", "head", "--sql"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE users" in result.stdout
    assert "CREATE TABLE audit_logs" in result.stdout
    assert "p%40ss" not in result.stdout + result.stderr
