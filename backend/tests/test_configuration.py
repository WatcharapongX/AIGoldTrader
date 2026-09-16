"""FC-10 safe configuration contract and secret-boundary tests."""

from fastapi.testclient import TestClient

from app.core.config import get_settings

EXPECTED_TOP_LEVEL = {
    "as_of",
    "authority",
    "restart_required",
    "trading",
    "market",
    "news",
    "ai",
    "infrastructure",
    "session",
}


def test_safe_configuration_requires_authentication(client: TestClient):
    assert client.get("/api/configuration/safe").status_code == 401


def test_safe_configuration_is_explicit_read_only_allow_list(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/configuration/safe", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == EXPECTED_TOP_LEVEL
    assert set(data["trading"]) == {"mode", "live_auto_trading", "broker_execution", "account_provenance"}
    assert set(data["market"]) == {
        "provider",
        "account_mode",
        "configured_symbol",
        "server_timezone",
        "poll_seconds",
        "stale_after_seconds",
        "archive_real_ticks",
        "terminal",
        "account_validation",
        "server_validation",
        "provenance",
    }
    assert set(data["news"]) == {"provider", "poll_seconds", "stale_after_seconds", "provenance"}
    assert set(data["ai"]) == {
        "mode",
        "provider_type",
        "credential",
        "endpoint",
        "model_mapping",
        "max_concurrent_provider_calls",
        "queue_timeout_seconds",
        "provenance",
    }
    assert set(data["infrastructure"]) == {"environment", "redis_enabled"}
    assert set(data["session"]) == {"access_token_minutes", "refresh_session_days"}
    assert data["authority"] == "SERVER_CONFIGURATION"
    assert data["trading"]["mode"] == "PAPER"
    assert data["trading"]["live_auto_trading"] is False
    assert data["trading"]["broker_execution"] == "NONE"


def test_safe_configuration_maps_modes_without_collapsing_provenance(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "mt5_terminal_path", "")
    monkeypatch.setattr(settings, "mt5_expected_login", None)
    monkeypatch.setattr(settings, "mt5_expected_server", "")

    baseline = client.get("/api/configuration/safe", headers=auth_headers).json()
    assert baseline["market"]["provider"] == "simulated"
    assert baseline["market"]["provenance"] == "SIMULATED"
    assert baseline["market"]["terminal"] == "NOT_REQUIRED"
    assert baseline["news"]["provider"] == "unavailable"
    assert baseline["news"]["provenance"] == "UNAVAILABLE"
    assert baseline["ai"]["mode"] == "fixture"
    assert baseline["ai"]["provenance"] == "FIXTURE"
    assert baseline["ai"]["credential"] == "NOT_REQUIRED"

    monkeypatch.setattr(settings, "market_data_provider", "mt5")
    monkeypatch.setattr(settings, "mt5_account_mode", "DEMO")
    demo = client.get("/api/configuration/safe", headers=auth_headers).json()
    assert demo["market"]["provenance"] == "DEMO"
    assert demo["market"]["terminal"] == "MISSING"

    monkeypatch.setattr(settings, "mt5_account_mode", "LIVE")
    live = client.get("/api/configuration/safe", headers=auth_headers).json()
    assert live["market"]["provenance"] == "LIVE"

    monkeypatch.setattr(settings, "news_calendar_provider", "fixture")
    fixture_news = client.get("/api/configuration/safe", headers=auth_headers).json()
    assert fixture_news["news"]["provenance"] == "FIXTURE"

    monkeypatch.setattr(settings, "ai_provider_mode", "external")
    monkeypatch.setattr(settings, "ai_provider_type", "openai_compatible")
    assert client.get("/api/configuration/safe", headers=auth_headers).json()["ai"]["credential"] == "MISSING"
    monkeypatch.setattr(settings, "ai_provider_api_key", "configured-but-never-returned")
    assert client.get("/api/configuration/safe", headers=auth_headers).json()["ai"]["credential"] == "CONFIGURED"


def test_safe_configuration_never_leaks_secret_values(client: TestClient, auth_headers: dict[str, str], monkeypatch):
    settings = get_settings()
    sentinels = {
        "database_connection_url": "postgresql://fc10-user:fc10-password@private-db:5432/fc10",
        "postgres_password": "fc10-postgres-password",
        "ai_provider_api_key": "fc10-ai-api-key",
        "mt5_terminal_path": "C:/private/fc10-terminal.exe",
        "mt5_expected_login": 99112233,
        "mt5_expected_server": "FC10-Private-Broker-Server",
    }
    hidden_values = [*sentinels.values(), settings.secret_key]
    for field, value in sentinels.items():
        monkeypatch.setattr(settings, field, value)
    response = client.get("/api/configuration/safe", headers=auth_headers)
    assert response.status_code == 200
    rendered = response.text
    for value in hidden_values:
        assert str(value) not in rendered
    for forbidden_key in (
        "secret_key",
        "database_connection_url",
        "postgres_password",
        "ai_provider_api_key",
        "mt5_terminal_path",
        "mt5_expected_login",
        "mt5_expected_server",
        "redis_host",
    ):
        assert forbidden_key not in rendered


def test_non_admin_receives_no_credential_presence_metadata(
    client: TestClient, auth_headers: dict[str, str], trader_user, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "market_data_provider", "mt5")
    monkeypatch.setattr(settings, "mt5_terminal_path", "configured-terminal")
    monkeypatch.setattr(settings, "mt5_expected_login", 123456)
    monkeypatch.setattr(settings, "mt5_expected_server", "configured-server")
    monkeypatch.setattr(settings, "ai_provider_mode", "external")
    monkeypatch.setattr(settings, "ai_provider_type", "openai_compatible")
    monkeypatch.setattr(settings, "ai_provider_api_key", "configured-key")
    login = client.post("/api/auth/login", json={"email": "trader@example.com", "password": "trader-pass-123"})
    response = client.get(
        "/api/configuration/safe",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["market"]["terminal"] == "NOT_EXPOSED"
    assert data["market"]["account_validation"] == "NOT_EXPOSED"
    assert data["market"]["server_validation"] == "NOT_EXPOSED"
    assert data["ai"]["credential"] == "NOT_EXPOSED"


def test_configuration_router_has_no_write_methods(client: TestClient, auth_headers: dict[str, str]):
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/configuration/safe", headers=auth_headers).status_code == 405
