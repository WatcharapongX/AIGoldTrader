"""Tests for system status aggregation and risk account snapshot endpoints (FC-01)."""

from fastapi.testclient import TestClient


def test_system_status_endpoint(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/system/status", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "as_of" in data
    assert data["trading_mode"] == "PAPER"
    assert data["live_auto_trading"] is False
    assert "modules" in data
    modules = data["modules"]
    expected_keys = {
        "backend",
        "database",
        "redis",
        "market_data",
        "news",
        "ai_provider",
        "risk_engine",
        "kill_switch",
    }
    assert expected_keys.issubset(set(modules.keys()))
    assert modules["backend"]["state"] == "HEALTHY"
    assert modules["ai_provider"]["state"] in (
        "FIXTURE_READY",
        "EXTERNAL_READY",
        "EXTERNAL_NOT_CONFIGURED",
    )
    # Ensure zero secrets are leaked in response
    raw_text = response.text
    assert "ai_provider_api_key" not in raw_text
    assert "password" not in raw_text.lower()


def test_risk_account_snapshot_endpoint(client: TestClient, auth_headers: dict[str, str]):
    response = client.get(
        "/api/risk/account?account_id=default_paper_account",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "balance" in data
    assert "equity" in data
    assert data["trading_mode"] == "PAPER"
    assert float(data["balance"]) >= 0
