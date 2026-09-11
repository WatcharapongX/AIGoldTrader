"""Phase 1 gate: migrations, Redis helpers, and secret-safe validation."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.services import redis_client


def test_migration_upgrade_downgrade_upgrade(tmp_path):
    database = tmp_path / "migration.sqlite"
    env = {**os.environ, "DATABASE_URL_OVERRIDE": f"sqlite+aiosqlite:///{database.as_posix()}"}
    backend = Path(__file__).resolve().parents[1]
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    expected = {
        "users", "sessions", "accounts", "symbols", "audit_logs", "system_events",
        "ticks", "candles", "economic_events", "economic_event_revisions",
        "trader_profiles", "strategy_evaluations", "trade_candidates", "candidate_transitions",
        "risk_policies", "symbol_specifications", "account_snapshots",
        "risk_decisions", "risk_reservations", "kill_switch_records",
    }
    try:
        for target in ("head", "base", "head"):
            action = "downgrade" if target == "base" else "upgrade"
            result = subprocess.run(  # noqa: S603 — fixed executable and migration args, isolated temp DB
                [sys.executable, "-m", "alembic", action, target],
                cwd=backend, env=env, capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, result.stderr
            actual = set(inspect(engine).get_table_names()) - {"alembic_version"}
            assert actual == (set() if target == "base" else expected)
    finally:
        engine.dispose()


async def test_redis_cache_and_publish(fake_redis):
    assert await redis_client.redis_health()
    assert await redis_client.cache_set_json("gate:cache", '{"value":1}', ttl_seconds=20)
    assert await redis_client.cache_get_json("gate:cache") == '{"value":1}'
    assert await fake_redis.ttl("gate:cache") > 0
    async with fake_redis.pubsub() as subscription:
        await subscription.subscribe("gate:channel")
        await subscription.get_message(timeout=1)  # consume subscription acknowledgement
        assert await redis_client.publish("gate:channel", {"value": 2})
        message = await subscription.get_message(ignore_subscribe_messages=True, timeout=1)
        assert message is not None
        assert message["data"] == '{"value": 2}'


def test_validation_response_does_not_echo_password(client):
    response = client.post("/api/auth/login", json={"email": "bad-email", "password": "secret"})
    assert response.status_code == 422
    assert "secret" not in response.text
    assert "bad-email" not in response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_root_health_alias_matches_api(client):
    root_response = client.get("/healthz")
    api_response = client.get("/api/healthz")
    assert root_response.status_code == api_response.status_code == 200
    assert root_response.json()["trading_mode"] == "PAPER"
    assert root_response.json()["live_auto_trading"] is False
    assert client.get("/readyz").json()["checks"] == client.get("/api/readyz").json()["checks"]
