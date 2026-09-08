"""Health endpoints — TASK-011 DoD evidence."""

from fastapi.testclient import TestClient


def test_healthz_reports_trading_mode(client: TestClient) -> None:
    response = client.get("/api/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["trading_mode"] == "PAPER"  # G-03: default PAPER
    assert body["live_auto_trading"] is False  # G-01


def test_readyz_with_fake_redis(client: TestClient) -> None:
    # DB = SQLite in-memory (ok), Redis = fakeredis (ok)
    response = client.get("/api/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"] is True
    assert body["checks"]["redis"] is True


def test_healthz_does_not_require_auth(client: TestClient) -> None:
    response = client.get("/api/healthz")
    assert response.status_code == 200
