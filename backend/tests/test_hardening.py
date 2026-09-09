"""Deterministic Phase 1.1 security and response contract regression."""

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import StatementError
from starlette.requests import Request

from app.api import auth
from app.api.health import HealthResponse, ReadyResponse
from app.core.client_ip import resolve_client_ip
from app.core.config import Settings, get_settings
from app.core.correlation import (
    get_correlation_id,
    normalize_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from app.core.errors import AuthError, RateLimitedError
from app.core.logging import JsonFormatter, SafeFormatter
from app.core.rate_limit import RateLimiter
from app.main import create_app
from scripts.export_api_contract import artifacts


def request(peer="198.51.100.1", forwarded="203.0.113.1"):
    return Request({
        "type": "http", "client": (peer, 1234), "headers": [
            (b"x-forwarded-for", forwarded.encode()), (b"forwarded", b"for=203.0.113.2"),
            (b"x-real-ip", b"203.0.113.3"),
        ],
    })


@pytest.mark.parametrize("change_forwarded", [False, True])
def test_login_peer_limit_cannot_be_spoofed(client, monkeypatch, change_forwarded):
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(2))
    statuses = [
        client.post("/api/auth/login", headers={"X-Forwarded-For": f"203.0.113.{i if change_forwarded else 1}"},
                    json={"email": "unknown@example.com", "password": "incorrect-password"}).status_code
        for i in range(3)
    ]
    assert statuses == [401, 401, 429]


def test_changing_accounts_still_spends_client_budget(client, monkeypatch):
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(2))
    statuses = [
        client.post("/api/auth/login", json={
            "email": f"unknown{i}@example.com", "password": "incorrect-password",
        }).status_code for i in range(3)
    ]
    assert statuses == [401, 401, 429]


async def test_normalized_account_budget_spans_different_peers(monkeypatch):
    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(2))
    monkeypatch.setattr(auth, "authenticate", AsyncMock(side_effect=AuthError("Invalid email or password")))
    monkeypatch.setattr(auth.audit, "write_audit", AsyncMock())
    for i, email in enumerate(("User@example.com", "user@example.com", "USER@example.com")):
        error = AuthError if i < 2 else RateLimitedError
        with pytest.raises(error):
            await auth.login(
                auth.LoginRequest(email=email, password="incorrect-password"),
                request(peer=f"198.51.100.{i+1}"), AsyncMock(),
            )


@pytest.mark.parametrize(("trust", "peer", "chain", "expected"), [
    (False, "10.0.0.1", "203.0.113.1", "10.0.0.1"),
    (True, "198.51.100.1", "203.0.113.1", "198.51.100.1"),
    (True, "10.0.0.1", "203.0.113.1", "203.0.113.1"),
    (True, "10.0.0.1", "192.0.2.9, 203.0.113.1, 10.0.0.2", "203.0.113.1"),
    (True, "10.0.0.1", "bad-address", "10.0.0.1"),
    (True, "10.0.0.1", ",203.0.113.1", "10.0.0.1"),
    (True, "10.0.0.1", ",".join(["203.0.113.1"] * 17), "10.0.0.1"),
    (True, "10.0.0.1", "2001:db8::1", "2001:db8::1"),
])
def test_proxy_boundary(monkeypatch, trust, peer, chain, expected):
    monkeypatch.setenv("TRUST_PROXY", str(trust).lower())
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/24")
    get_settings.cache_clear()
    assert resolve_client_ip(request(peer, chain)) == expected


@pytest.mark.parametrize("cidrs", ["", "*", "0.0.0.0/0", "::/0", "not-a-network"])
def test_proxy_configuration_requires_bounded_network(cidrs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trust_proxy=True, trusted_proxy_cidrs=cidrs)


def test_limiter_bounds_expiry_and_atomic_budgets():
    now = [0.0]
    limiter = RateLimiter(2, max_keys=3, clock=lambda: now[0])
    limiter.check("client", "account")
    limiter.check("client", "account")
    with pytest.raises(RateLimitedError):
        limiter.check("client", "new-account")
    assert "new-account" not in limiter._hits
    limiter.check("other")
    for i in range(100):
        with pytest.raises(RateLimitedError):
            limiter.check(f"attacker-{i}")
    assert len(limiter._hits) == 3
    assert max(map(len, limiter._hits.values())) <= 2
    now[0] = 60
    limiter.cleanup()
    assert not limiter._hits
    limiter.check("client", "account")
    assert len(limiter._hits) == 2


@pytest.mark.parametrize("incoming", ["a" * 64, "a" * 65, "with space", "bad\nforged", "bad\rforged", "bad\x00id", ""])
def test_correlation_header_is_safe_and_preserved(client, incoming):
    response = client.get("/healthz", headers={"X-Correlation-ID": incoming})
    assert response.status_code == 200
    actual = response.headers["X-Correlation-ID"]
    assert len(actual) <= 64 and actual == normalize_correlation_id(actual)
    if incoming == "a" * 64:
        assert actual == incoming
    else:
        assert actual != incoming


def test_correlation_context_is_reset():
    previous = get_correlation_id()
    token = set_correlation_id("request-123")
    assert get_correlation_id() == "request-123"
    reset_correlation_id(token)
    assert get_correlation_id() == previous


@pytest.mark.parametrize("formatter", [JsonFormatter(), SafeFormatter()])
def test_exception_formatter_does_not_render_sensitive_parameters(formatter):
    marker = "fixture-password-token-signing-key"
    exc = StatementError("driver " + marker, "SELECT " + marker, {"password": marker}, ValueError(marker))
    record = logging.LogRecord("test", logging.ERROR, __file__, 1, "safe operation", (), (type(exc), exc, None))
    rendered = formatter.format(record)
    assert marker not in rendered
    assert "StatementError" in rendered


def test_unhandled_exception_has_safe_context_and_header():
    app = create_app()

    @app.get("/_test/error")
    async def fail():
        raise ValueError("fixture-sensitive-request-body")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test/error", headers={"X-Correlation-ID": "error-123"})
    assert response.status_code == 500
    assert response.headers["X-Correlation-ID"] == response.json()["error"]["correlation_id"] == "error-123"
    assert "fixture-sensitive-request-body" not in response.text


def test_openapi_generated_contract_matches_source():
    for path, expected in artifacts().items():
        assert path.read_text(encoding="utf-8") == expected, "Regenerate and review the API contract"


def test_backend_response_models_and_wire_shapes(client, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers)
    assert set(me.json()) == set(auth.MeResponse.model_fields)
    assert auth.MeResponse.model_validate(me.json()).role.value == "ADMIN"
    health = client.get("/healthz").json()
    ready = client.get("/readyz").json()
    assert set(health) == set(HealthResponse.model_fields)
    assert set(ready) == set(ReadyResponse.model_fields)
    HealthResponse.model_validate(health)
    ReadyResponse.model_validate(ready)


def test_documented_native_launch_disables_server_proxy_rewriting():
    root = Path(__file__).resolve().parents[2]
    for name in ("README.md", "docs/18-devops.md", "docker-compose.yml", "docker-compose.dev.yml"):
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            if "uvicorn app.main:app" in line:
                assert "--no-proxy-headers" in line
    command = (root / "backend/Dockerfile").read_text(encoding="utf-8").split("CMD ")[-1]
    assert "--no-proxy-headers" in json.loads(command)

@pytest.mark.parametrize(("field", "value"), [
    ("access_token", ""), ("access_token", "  "), ("refresh_token", ""),
    ("refresh_token", "\t"), ("token_type", "Basic"), ("token_type", "Bearer"),
    ("token_type", "other"), ("expires_at", "1"), ("expires_at", 1),
    ("expires_at", "2030-01-01"), ("expires_at", "2030-02-30T00:00:00Z"),
    ("expires_at", "2030-01-01T00:00:00"), ("expires_at", "2030-01-01T24:00:00Z"),
])
def test_token_response_semantic_constraints(field, value):
    payload = {
        "access_token": "fixture-access", "refresh_token": "fixture-refresh",
        "token_type": "bearer", "expires_at": "2030-01-01T00:00:00Z",
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        auth.TokenPair.model_validate(payload)


def test_token_response_contract_requires_every_field_and_accepts_real_format():
    payload = {
        "access_token": "fixture-access", "refresh_token": "fixture-refresh",
        "token_type": "bearer", "expires_at": "2030-01-01T00:00:00.123456+00:00",
    }
    model = auth.TokenPair.model_validate(payload)
    assert model.token_type == "bearer"
    for field in payload:
        with pytest.raises(ValidationError):
            auth.TokenPair.model_validate({key: value for key, value in payload.items() if key != field})
    schema = auth.TokenPair.model_json_schema()
    assert set(schema["required"]) == set(payload)
    assert schema["properties"]["access_token"]["minLength"] == 1
    assert schema["properties"]["access_token"]["pattern"] == r"^\S+$"
    assert schema["properties"]["token_type"]["const"] == "bearer"
    assert schema["properties"]["expires_at"]["format"] == "date-time"
