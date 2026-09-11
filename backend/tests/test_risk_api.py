"""Phase 5 API tests: read-only GET safety, evaluate commands, and Kill Switch admin authorization."""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.services.strategy.domain import (
    Evidence,
    SetupCandidate,
    Target,
    TradePlanSuggestion,
)


def _seed_candidate_and_plan(session, at):
    plan = TradePlanSuggestion(
        id="plan_api_001",
        candidate_id="cand_api_001",
        symbol="XAUUSD",
        direction="LONG",
        entry_type="LIMIT_ZONE",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        entry_source_id="h1_fvg",
        stop_loss=Decimal("2495.00"),
        stop_source_id="h1_swing_low",
        invalidation_th="หลุดแนวรับ",
        targets=(
            Target(name="TP1", price=Decimal("2510.00"), source_id="h4_high", rr=Decimal("1.5")),
            Target(name="TP2", price=Decimal("2520.00"), source_id="d1_high", rr=Decimal("3.0")),
        ),
        score=90,
        evidence=(Evidence(code="EV1", description_th="Confirmation"),),
        warnings_th=(),
        news_state="CALM",
        status="SUGGESTION_ONLY",
        as_of=at,
        context_id="ctx_001",
        expires_at=at + Decimal("7200") * Decimal("1"),  # 2 hours later
    )
    cand = SetupCandidate(
        id="cand_api_001",
        profile_id="day_trader",
        strategy_id="STRAT02",
        strategy_version="strategy-1.2.1",
        symbol="XAUUSD",
        direction="LONG",
        status="READY",
        score=90,
        detected_at=at,
        confirmed_at=at,
        expires_at=at + Decimal("7200") * Decimal("1"),
        context_id="ctx_001",
        upstream_ids=("ctx_001",),
        evidence=(Evidence(code="EV1", description_th="Confirmation"),),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="หลุดแนวรับ",
        plan=plan,
    )
    return cand


def test_get_policy_is_read_only(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/risk/policy", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["max_risk_per_trade_pct"] == "1.0"
    assert data["max_account_risk_pct"] == "3.0"


def test_get_portfolio_is_read_only(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/risk/portfolio", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "open_risk_pct" in data
    assert "reserved_risk_pct" in data
    assert "available_risk_pct" in data
    assert "kill_switch_active" in data
    assert data["kill_switch_active"] is False


def test_get_kill_switch_is_read_only(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/risk/kill-switch", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "INACTIVE"


def test_kill_switch_admin_authorization(client: TestClient, auth_headers: dict[str, str], trader_user):
    # 1. Non-admin (Trader) tries to activate Kill Switch -> 403 Forbidden
    trader_login = client.post(
        "/api/auth/login", json={"email": "trader@example.com", "password": "trader-pass-123"}
    )
    assert trader_login.status_code == 200
    trader_token = trader_login.json()["access_token"]
    trader_headers = {"Authorization": f"Bearer {trader_token}"}

    forbidden = client.post(
        "/api/risk/kill-switch/activate",
        headers=trader_headers,
        json={"reason_th": "พยายามปิดระบบโดยไม่ใช่ Admin"},
    )
    assert forbidden.status_code == 403

    # 2. Admin activates Kill Switch -> 200 OK
    res_activate = client.post(
        "/api/risk/kill-switch/activate",
        headers=auth_headers,
        json={"reason_th": "ผู้ดูแลระบบทดสอบปิดระบบฉุกเฉิน"},
    )
    assert res_activate.status_code == 200
    assert res_activate.json()["state"] == "ACTIVE"

    # Verify status changed
    ks_status = client.get("/api/risk/kill-switch", headers=auth_headers).json()
    assert ks_status["state"] == "ACTIVE"

    # 3. Admin clears Kill Switch -> 200 OK
    res_clear = client.post(
        "/api/risk/kill-switch/clear",
        headers=auth_headers,
        json={"reason_th": "เคลียร์สวิตช์ฉุกเฉินเรียบร้อย"},
    )
    assert res_clear.status_code == 200
    assert res_clear.json()["state"] == "INACTIVE"
