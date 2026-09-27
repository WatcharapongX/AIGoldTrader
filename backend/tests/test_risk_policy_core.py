"""D2B1 pure Risk policy contract, boundary, and determinism tests."""

import datetime as dt
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, Decimal, localcontext

import pytest
from pydantic import ValidationError

from app.services.risk import policy_core
from app.services.risk.domain import AccountSnapshot, RiskPolicy, SymbolSpecification, default_gold_spec
from app.services.risk.policy_core import evaluate_pure_risk
from app.services.risk.policy_domain import (
    DataHealthInputState,
    KillSwitchInputState,
    NewsAvailability,
    PortfolioExposureSnapshot,
    PureDataHealthInput,
    PureKillSwitchInput,
    PureNewsEvent,
    PureNewsState,
    PureQuoteState,
    PureRiskEvaluationInput,
    QuoteAvailability,
    ReservationIntegrityState,
)
from app.services.risk.policy_fingerprint import _canonical_decimal, build_pure_risk_semantic_payload
from app.services.strategy.domain import Evidence, SetupCandidate, Target, TradePlanSuggestion

AT = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.UTC)


def _plan(*, direction: str = "LONG") -> TradePlanSuggestion:
    is_long = direction == "LONG"
    return TradePlanSuggestion(
        id="plan_pure_001",
        candidate_id="cand_pure_001",
        symbol="XAUUSD",
        direction=direction,
        entry_type="LIMIT_ZONE",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        entry_source_id="h1_fvg",
        stop_loss=Decimal("2495.00") if is_long else Decimal("2507.00"),
        stop_source_id="h1_swing",
        invalidation_th="โครงสร้างเสีย",
        targets=(
            Target(
                name="TP1",
                price=Decimal("2510.00") if is_long else Decimal("2490.00"),
                source_id="h4_target",
                rr=Decimal("1.5"),
            ),
            Target(
                name="TP2",
                price=Decimal("2520.00") if is_long else Decimal("2480.00"),
                source_id="d1_target",
                rr=Decimal("3.0"),
            ),
        ),
        score=85,
        evidence=(Evidence(code="EV1", description_th="ยืนยันโครงสร้าง"),),
        warnings_th=(),
        news_state="CALM",
        status="SUGGESTION_ONLY",
        as_of=AT,
        context_id="ctx_pure_001",
        expires_at=AT + dt.timedelta(hours=2),
    )


def _candidate(plan: TradePlanSuggestion, *, status: str = "READY") -> SetupCandidate:
    return SetupCandidate(
        id="cand_pure_001",
        profile_id="day_trader",
        strategy_id="STRAT02",
        strategy_version="strategy-1.2.1",
        symbol="XAUUSD",
        direction=plan.direction,
        status=status,
        score=85,
        detected_at=AT - dt.timedelta(minutes=10),
        confirmed_at=AT,
        expires_at=AT + dt.timedelta(hours=2),
        context_id="ctx_pure_001",
        upstream_ids=("ctx_pure_001",),
        evidence=(Evidence(code="EV1", description_th="ยืนยันโครงสร้าง"),),
        missing_conditions=(),
        conflicts=(),
        invalidation_th="โครงสร้างเสีย",
        plan=plan,
    )


def _news_event(minutes_from_now: Decimal | int | str) -> PureNewsEvent:
    minutes = Decimal(str(minutes_from_now))
    return PureNewsEvent(
        event_id=f"news_{minutes}",
        event_name="US High Impact",
        currency="USD",
        impact="HIGH",
        scheduled_at=AT + dt.timedelta(seconds=float(minutes * Decimal("60"))),
        available_at=AT - dt.timedelta(hours=1),
        provider="fixture_economic_v1",
        source="fixture_economic_v1",
        revision_id="1",
        revision_version=1,
    )


def make_input(
    *,
    caller: Decimal | None = None,
    as_of: dt.datetime = AT,
    plan: TradePlanSuggestion | None = None,
    candidate_status: str = "READY",
    lifecycle_status: str | None = None,
    account_updates: dict | None = None,
    policy_updates: dict | None = None,
    spec_updates: dict | None = None,
    quote: PureQuoteState | None = None,
    news: PureNewsState | None = None,
    kill_switch: PureKillSwitchInput | None = None,
    data_health: PureDataHealthInput | None = None,
    portfolio_updates: dict | None = None,
) -> PureRiskEvaluationInput:
    plan = plan or _plan()
    candidate = _candidate(_plan(direction=plan.direction), status=candidate_status).model_copy(update={"plan": plan})
    account = AccountSnapshot(
        id="snap_pure_001",
        account_id="acc_pure_001",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        free_margin=Decimal("10000.00"),
        daily_realized_pnl=Decimal("0.00"),
        weekly_realized_pnl=Decimal("0.00"),
        peak_equity=Decimal("10000.00"),
        open_risk_pct=Decimal("0"),
        reserved_risk_pct=Decimal("0"),
        consecutive_losses=0,
        open_positions_count=0,
        source="CONFIGURED_TEST",
        as_of=AT,
    )
    if account_updates:
        account = account.model_copy(update=account_updates)
    policy = RiskPolicy()
    if policy_updates:
        policy = policy.model_copy(update=policy_updates)
    spec = default_gold_spec(source="simulated", observed_at=AT)
    if spec_updates:
        spec = spec.model_copy(update=spec_updates)
    quote = quote or PureQuoteState(
        availability=QuoteAvailability.AVAILABLE,
        timestamp=AT,
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        source="simulated",
        mode="SIMULATED",
        status="CONNECTED",
    )
    news = news or PureNewsState(
        availability=NewsAvailability.AVAILABLE,
        provider="fixture_economic_v1",
        source="fixture_economic_v1",
        revision_id="1",
        revision_version=1,
    )
    portfolio_values = {
        "symbol": "XAUUSD",
        "direction": plan.direction,
        "open_risk_pct": account.open_risk_pct,
        "reserved_risk_pct": Decimal("0"),
        "symbol_risk_pct": Decimal("0"),
        "directional_risk_pct": Decimal("0"),
        "active_reservation_count": 0,
        "open_position_count": account.open_positions_count,
        "reservation_integrity": ReservationIntegrityState.OK,
    }
    portfolio_values.update(portfolio_updates or {})
    return PureRiskEvaluationInput(
        as_of=as_of,
        candidate=candidate,
        trade_plan=plan,
        account=account,
        policy=policy,
        symbol_specification=spec,
        quote=quote,
        news=news,
        kill_switch=kill_switch or PureKillSwitchInput(state=KillSwitchInputState.INACTIVE),
        data_health=data_health or PureDataHealthInput(state=DataHealthInputState.HEALTHY),
        candidate_lifecycle_status=lifecycle_status or candidate_status,
        candidate_transition_count=0,
        caller_requested_risk_pct=caller,
        portfolio=PortfolioExposureSnapshot(**portfolio_values),
    )


def test_normal_approved_and_repeat_determinism():
    evaluation_input = make_input()
    first = evaluate_pure_risk(evaluation_input)
    second = evaluate_pure_risk(evaluation_input)
    assert first == second
    assert first.decision == "APPROVED"
    assert first.approved_risk_pct == Decimal("1.0000")
    assert first.approved_risk_amount == Decimal("100.00")
    assert first.position_size == Decimal("0.14")
    assert first.semantic_fingerprint == second.semantic_fingerprint


@pytest.mark.parametrize(
    ("caller", "normalized", "approved", "decision"),
    [
        (None, Decimal("1.0"), Decimal("1.0000"), "APPROVED"),
        (Decimal("0"), Decimal("1.0"), Decimal("1.0000"), "APPROVED"),
        (Decimal("0.5"), Decimal("0.5"), Decimal("0.5000"), "APPROVED"),
        (Decimal("1.0"), Decimal("1.0"), Decimal("1.0000"), "APPROVED"),
        (Decimal("2.0"), Decimal("2.0"), Decimal("1.0000"), "REDUCED"),
        (Decimal("-0.1"), Decimal("-0.1"), Decimal("0"), "BLOCKED"),
    ],
)
def test_requested_risk_normalization_matrix(caller, normalized, approved, decision):
    result = evaluate_pure_risk(make_input(caller=caller))
    assert result.caller_requested_risk_pct == caller
    assert result.normalized_requested_risk_pct == normalized
    assert result.target_risk_pct == normalized
    assert result.approved_risk_pct == approved
    assert result.decision == decision


def test_blocked_result_retains_caller_normalized_and_news_target():
    news = PureNewsState(availability=NewsAvailability.AVAILABLE, events=(_news_event(10),))
    result = evaluate_pure_risk(
        make_input(
            caller=Decimal("0.50"),
            news=news,
            account_updates={"as_of": AT - dt.timedelta(seconds=61)},
        )
    )
    assert result.decision == "BLOCKED"
    assert result.caller_requested_risk_pct == Decimal("0.50")
    assert result.normalized_requested_risk_pct == Decimal("0.50")
    assert result.target_risk_pct == Decimal("0.250")
    assert result.approved_risk_pct == Decimal("0")
    assert result.normalized_requested_risk_amount == Decimal("50.00")
    assert result.target_risk_amount == Decimal("25.00")
    assert result.approved_risk_amount == Decimal("0")
    assert result.warning_codes == ()
    assert result.warnings_th == ()


@pytest.mark.parametrize("state", [KillSwitchInputState.ACTIVE, KillSwitchInputState.UNKNOWN])
def test_kill_switch_active_and_unknown_fail_closed(state):
    result = evaluate_pure_risk(make_input(kill_switch=PureKillSwitchInput(state=state)))
    assert result.decision == "BLOCKED"
    assert result.blocked_codes[0].value.startswith("KILL_SWITCH_")


@pytest.mark.parametrize("state", [DataHealthInputState.TRIGGERED, DataHealthInputState.UNKNOWN])
def test_data_health_triggered_and_unknown_fail_closed(state):
    result = evaluate_pure_risk(make_input(data_health=PureDataHealthInput(state=state)))
    assert result.decision == "BLOCKED"
    assert result.safety_trigger_facts.data_health_state == state


def test_data_health_degraded_does_not_invent_a_new_block_policy():
    result = evaluate_pure_risk(make_input(data_health=PureDataHealthInput(state=DataHealthInputState.DEGRADED)))
    assert result.decision == "APPROVED"


@pytest.mark.parametrize(
    ("seconds_old", "blocked"),
    [(5, False), (5.000001, True)],
)
def test_quote_freshness_boundary(seconds_old, blocked):
    quote = PureQuoteState(
        availability=QuoteAvailability.AVAILABLE,
        timestamp=AT - dt.timedelta(seconds=seconds_old),
        bid=Decimal("2500.00"),
        ask=Decimal("2500.30"),
        spread=Decimal("0.30"),
        source="simulated",
        mode="SIMULATED",
        status="CONNECTED",
    )
    assert (evaluate_pure_risk(make_input(quote=quote)).decision == "BLOCKED") is blocked


@pytest.mark.parametrize(
    ("seconds_old", "blocked"),
    [(60, False), (60.000001, True)],
)
def test_account_freshness_boundary(seconds_old, blocked):
    result = evaluate_pure_risk(make_input(account_updates={"as_of": AT - dt.timedelta(seconds=seconds_old)}))
    assert (result.decision == "BLOCKED") is blocked


@pytest.mark.parametrize(
    ("seconds_old", "blocked"),
    [(86400, False), (86400.000001, True)],
)
def test_symbol_spec_freshness_boundary(seconds_old, blocked):
    result = evaluate_pure_risk(
        make_input(spec_updates={"observed_at": AT - dt.timedelta(seconds=seconds_old)})
    )
    assert (result.decision == "BLOCKED") is blocked


def test_quote_unavailable_and_excessive_spread_block():
    unavailable = PureQuoteState(availability=QuoteAvailability.UNAVAILABLE)
    assert evaluate_pure_risk(make_input(quote=unavailable)).decision == "BLOCKED"
    wide = PureQuoteState(
        availability=QuoteAvailability.AVAILABLE,
        timestamp=AT,
        bid=Decimal("2500.00"),
        ask=Decimal("2501.51"),
        spread=Decimal("1.51"),
        source="simulated",
        mode="SIMULATED",
        status="CONNECTED",
    )
    assert evaluate_pure_risk(make_input(quote=wide)).decision == "BLOCKED"


@pytest.mark.parametrize(
    ("field", "value", "blocked"),
    [
        ("daily_realized_pnl", Decimal("-299.99"), False),
        ("daily_realized_pnl", Decimal("-300.00"), True),
        ("daily_realized_pnl", Decimal("-300.01"), True),
        ("weekly_realized_pnl", Decimal("-599.99"), False),
        ("weekly_realized_pnl", Decimal("-600.00"), True),
        ("weekly_realized_pnl", Decimal("-600.01"), True),
    ],
)
def test_loss_boundaries(field, value, blocked):
    result = evaluate_pure_risk(make_input(account_updates={field: value}))
    assert (result.decision == "BLOCKED") is blocked


@pytest.mark.parametrize(
    ("equity", "blocked"),
    [(Decimal("9000.01"), False), (Decimal("9000.00"), True), (Decimal("8999.99"), True)],
)
def test_drawdown_boundary(equity, blocked):
    result = evaluate_pure_risk(make_input(account_updates={"equity": equity, "peak_equity": Decimal("10000")}))
    assert (result.decision == "BLOCKED") is blocked


@pytest.mark.parametrize(
    ("minutes", "decision"),
    [
        (Decimal("15"), "REDUCED"),
        (Decimal("5.0001"), "REDUCED"),
        (Decimal("5"), "BLOCKED"),
        (Decimal("0"), "BLOCKED"),
        (Decimal("-0.0001"), "APPROVED"),
        (Decimal("-15"), "APPROVED"),
        (Decimal("-15.0001"), "APPROVED"),
    ],
)
def test_news_window_boundaries(minutes, decision):
    result = evaluate_pure_risk(
        make_input(news=PureNewsState(availability=NewsAvailability.AVAILABLE, events=(_news_event(minutes),)))
    )
    assert result.decision == decision


def test_news_unavailable_and_post_news_spread_block():
    unavailable = PureNewsState(availability=NewsAvailability.UNAVAILABLE)
    assert evaluate_pure_risk(make_input(news=unavailable)).decision == "BLOCKED"
    quote = PureQuoteState(
        availability=QuoteAvailability.AVAILABLE,
        timestamp=AT,
        bid=Decimal("2500.00"),
        ask=Decimal("2501.21"),
        spread=Decimal("1.21"),
        source="simulated",
        mode="SIMULATED",
        status="CONNECTED",
    )
    post = PureNewsState(availability=NewsAvailability.AVAILABLE, events=(_news_event(-1),))
    result = evaluate_pure_risk(make_input(news=post, quote=quote))
    assert result.decision == "BLOCKED"
    assert result.safety_trigger_facts.quote_safety_state.value == "POST_NEWS_SPREAD_BLOCKED"


@pytest.mark.parametrize("status", ["INVALIDATED", "EXPIRED", "SUPERSEDED"])
def test_candidate_terminal_states_block(status):
    result = evaluate_pure_risk(make_input(candidate_status=status))
    assert result.decision == "BLOCKED"
    assert "CANDIDATE_TERMINAL" in {code.value for code in result.blocked_codes}


def test_plan_status_and_expiry_block():
    invalid_status = _plan().model_copy(update={"status": "INVALID"})
    valid_input = make_input()
    invalid_status_input = valid_input.model_copy(
        update={
            "trade_plan": invalid_status,
            "candidate": valid_input.candidate.model_copy(update={"plan": invalid_status}),
        }
    )
    with pytest.raises(ValidationError):
        evaluate_pure_risk(invalid_status_input)
    expired = TradePlanSuggestion(
        **{
            **_plan().model_dump(mode="python"),
            "as_of": AT - dt.timedelta(hours=2),
            "expires_at": AT,
        }
    )
    assert evaluate_pure_risk(make_input(plan=expired)).decision == "BLOCKED"


def test_equity_zero_cooldown_and_unattributed_open_risk_block():
    assert evaluate_pure_risk(make_input(account_updates={"equity": Decimal("0")})).decision == "BLOCKED"
    cooldown = evaluate_pure_risk(
        make_input(
            account_updates={
                "consecutive_losses": 3,
                "last_loss_at": AT,
                "cooldown_until": AT + dt.timedelta(minutes=60),
            }
        )
    )
    assert cooldown.decision == "BLOCKED"
    open_risk = evaluate_pure_risk(
        make_input(
            account_updates={"open_risk_pct": Decimal("0.5")},
            portfolio_updates={"open_risk_pct": Decimal("0.5")},
        )
    )
    assert open_risk.decision == "BLOCKED"


@pytest.mark.parametrize(
    "portfolio_updates",
    [
        {
            "reservation_integrity": ReservationIntegrityState.DUPLICATE_ACTIVE_RESERVATION,
            "duplicate_candidate_id": "cand_other",
        },
        {"reservation_integrity": ReservationIntegrityState.UNKNOWN},
        {"active_reservation_count": 3},
        {"reserved_risk_pct": Decimal("2.95")},
        {"symbol_risk_pct": Decimal("1.95")},
        {"directional_risk_pct": Decimal("1.95")},
    ],
)
def test_portfolio_block_matrix(portfolio_updates):
    result = evaluate_pure_risk(make_input(portfolio_updates=portfolio_updates))
    assert result.decision == "BLOCKED"
    assert result.approved_risk_pct == Decimal("0")


def test_per_trade_and_portfolio_reductions():
    per_trade = evaluate_pure_risk(make_input(caller=Decimal("2")))
    assert per_trade.decision == "REDUCED"
    assert per_trade.approved_risk_pct == Decimal("1.0000")
    portfolio = evaluate_pure_risk(
        make_input(
            portfolio_updates={
                "reserved_risk_pct": Decimal("2.5"),
                "symbol_risk_pct": Decimal("0"),
                "directional_risk_pct": Decimal("0"),
                "active_reservation_count": 1,
            }
        )
    )
    assert portfolio.decision == "REDUCED"
    assert portfolio.approved_risk_pct == Decimal("0.5000")


def test_position_sizing_failure_matrix():
    below_minimum = _plan().model_copy(update={"entry_upper": Decimal("2500"), "stop_loss": Decimal("2300")})
    assert evaluate_pure_risk(make_input(plan=below_minimum)).decision == "BLOCKED"
    valid_input = make_input()
    invalid_long = _plan().model_copy(update={"stop_loss": Decimal("2501")})
    invalid_long_input = valid_input.model_copy(
        update={
            "trade_plan": invalid_long,
            "candidate": valid_input.candidate.model_copy(update={"plan": invalid_long}),
        }
    )
    with pytest.raises(ValidationError):
        evaluate_pure_risk(invalid_long_input)
    invalid_short = _plan(direction="SHORT").model_copy(update={"stop_loss": Decimal("2501")})
    short_input = make_input(plan=_plan(direction="SHORT"))
    invalid_short_input = short_input.model_copy(
        update={
            "trade_plan": invalid_short,
            "candidate": short_input.candidate.model_copy(update={"plan": invalid_short}),
        }
    )
    with pytest.raises(ValidationError):
        evaluate_pure_risk(invalid_short_input)


def test_fingerprint_none_zero_distinct_and_decimal_spelling_invariant():
    none_result = evaluate_pure_risk(make_input(caller=None))
    zero_result = evaluate_pure_risk(make_input(caller=Decimal("0")))
    one_a = evaluate_pure_risk(make_input(caller=Decimal("1.0")))
    one_b = evaluate_pure_risk(make_input(caller=Decimal("1.00")))
    assert none_result.semantic_fingerprint != zero_result.semantic_fingerprint
    assert one_a.semantic_fingerprint == one_b.semantic_fingerprint


def test_fingerprint_sensitivity_for_semantic_dependencies():
    baseline = evaluate_pure_risk(make_input()).semantic_fingerprint
    variants = [
        make_input(as_of=AT + dt.timedelta(microseconds=1)),
        make_input(caller=Decimal("0")),
        make_input(policy_updates={"max_risk_per_trade_pct": Decimal("0.9")}),
        make_input(account_updates={"equity": Decimal("9999")}),
        make_input(account_updates={"daily_realized_pnl": Decimal("-1")}),
        make_input(account_updates={"weekly_realized_pnl": Decimal("-1")}),
        make_input(kill_switch=PureKillSwitchInput(state=KillSwitchInputState.UNKNOWN)),
        make_input(data_health=PureDataHealthInput(state=DataHealthInputState.DEGRADED)),
        make_input(spec_updates={"tick_value": Decimal("1.1")}),
        make_input(portfolio_updates={"reserved_risk_pct": Decimal("0.1")}),
        make_input(portfolio_updates={"symbol_risk_pct": Decimal("0.1")}),
        make_input(portfolio_updates={"directional_risk_pct": Decimal("0.1")}),
        make_input(candidate_status="INVALIDATED"),
        make_input(news=PureNewsState(availability=NewsAvailability.AVAILABLE, events=(_news_event(10),))),
    ]
    assert all(evaluate_pure_risk(variant).semantic_fingerprint != baseline for variant in variants)


def test_contracts_and_result_are_deeply_immutable():
    evaluation_input = make_input()
    result = evaluate_pure_risk(evaluation_input)
    with pytest.raises(ValidationError):
        evaluation_input.as_of = AT + dt.timedelta(seconds=1)
    with pytest.raises(ValidationError):
        evaluation_input.portfolio.reserved_risk_pct = Decimal("1")
    with pytest.raises(ValidationError):
        evaluation_input.kill_switch.state = KillSwitchInputState.ACTIVE
    with pytest.raises(ValidationError):
        result.decision = "BLOCKED"


def test_contract_rejects_naive_time_and_extra_fields():
    values = make_input().model_dump(mode="python")
    values["as_of"] = dt.datetime(2026, 9, 10, 12, 0)
    with pytest.raises(ValidationError):
        PureRiskEvaluationInput(**values)
    with pytest.raises(ValidationError):
        PureKillSwitchInput(state=KillSwitchInputState.INACTIVE, hidden_lookup=True)


def test_contract_rejects_news_revision_not_yet_available():
    future_event = _news_event(10).model_copy(update={"available_at": AT + dt.timedelta(seconds=1)})
    with pytest.raises(ValidationError):
        make_input(news=PureNewsState(availability=NewsAvailability.AVAILABLE, events=(future_event,)))


def test_d2b1_iv_p2_001_symbol_specification_authority(monkeypatch):
    valid_input = make_input()
    valid_payload = valid_input.model_dump(mode="python", round_trip=True)
    assert PureRiskEvaluationInput.model_validate(valid_payload) == valid_input

    wrong_spec_payload = valid_input.symbol_specification.model_dump(mode="python")
    wrong_spec_payload["symbol"] = "EURUSD"
    wrong_spec = SymbolSpecification.model_validate(wrong_spec_payload)
    invalid_payload = dict(valid_payload)
    invalid_payload["symbol_specification"] = wrong_spec
    with pytest.raises(ValidationError, match="SymbolSpecification symbol must match candidate"):
        PureRiskEvaluationInput.model_validate(invalid_payload)

    bypassed = valid_input.model_copy(update={"symbol_specification": wrong_spec})
    sizing_called = False

    def forbidden_sizing(**kwargs):
        nonlocal sizing_called
        sizing_called = True
        raise AssertionError("wrong-symbol specification reached sizing")

    monkeypatch.setattr(policy_core, "calculate_position_size", forbidden_sizing)
    with pytest.raises(ValidationError, match="SymbolSpecification symbol must match candidate"):
        evaluate_pure_risk(bypassed)
    assert not sizing_called


@pytest.mark.parametrize(
    "case",
    [
        "portfolio_count",
        "portfolio_open_risk",
        "portfolio_symbol",
        "plan_candidate",
        "plan_symbol",
        "spec_symbol",
    ],
)
def test_d2b1_iv_p2_002_outer_model_copy_attacks_rejected(case):
    base = make_input()
    if case == "portfolio_count":
        supplied = base.model_copy(
            update={"portfolio": base.portfolio.model_copy(update={"open_position_count": 1})}
        )
    elif case == "portfolio_open_risk":
        supplied = base.model_copy(
            update={"portfolio": base.portfolio.model_copy(update={"open_risk_pct": Decimal("0.5")})}
        )
    elif case == "portfolio_symbol":
        supplied = base.model_copy(update={"portfolio": base.portfolio.model_copy(update={"symbol": "EURUSD"})})
    elif case == "plan_candidate":
        supplied = base.model_copy(
            update={"trade_plan": base.trade_plan.model_copy(update={"candidate_id": "cand_other"})}
        )
    elif case == "plan_symbol":
        supplied = base.model_copy(
            update={"trade_plan": base.trade_plan.model_copy(update={"symbol": "EURUSD"})}
        )
    else:
        supplied = base.model_copy(
            update={"symbol_specification": base.symbol_specification.model_copy(update={"symbol": "EURUSD"})}
        )
    with pytest.raises(ValidationError):
        evaluate_pure_risk(supplied)


@pytest.mark.parametrize(
    "case",
    [
        "quote",
        "spec",
        "policy",
        "portfolio",
        "news",
        "news_event",
        "account",
        "candidate",
        "kill_switch",
        "data_health",
    ],
)
def test_d2b1_iv_p2_002_nested_model_copy_attacks_rejected(case):
    base = make_input()
    if case == "quote":
        nested = base.quote.model_copy(update={"ask": Decimal("2502.00")})
        supplied = base.model_copy(update={"quote": nested})
    elif case == "spec":
        nested = base.symbol_specification.model_copy(
            update={"volume_min": Decimal("11"), "volume_max": Decimal("10")}
        )
        supplied = base.model_copy(update={"symbol_specification": nested})
    elif case == "policy":
        nested = base.policy.model_copy(
            update={"max_risk_per_trade_pct": Decimal("4"), "max_account_risk_pct": Decimal("3")}
        )
        supplied = base.model_copy(update={"policy": nested})
    elif case == "portfolio":
        nested = base.portfolio.model_copy(
            update={
                "reservation_integrity": ReservationIntegrityState.DUPLICATE_ACTIVE_RESERVATION,
                "duplicate_candidate_id": None,
            }
        )
        supplied = base.model_copy(update={"portfolio": nested})
    elif case == "news":
        nested = base.news.model_copy(
            update={"availability": NewsAvailability.UNAVAILABLE, "events": (_news_event(10),)}
        )
        supplied = base.model_copy(update={"news": nested})
    elif case == "news_event":
        invalid_event = _news_event(10).model_copy(update={"scheduled_at": dt.datetime(2026, 9, 10, 12, 10)})
        supplied = base.model_copy(update={"news": base.news.model_copy(update={"events": (invalid_event,)})})
    elif case == "account":
        supplied = base.model_copy(update={"account": base.account.model_copy(update={"balance": Decimal("-1")})})
    elif case == "candidate":
        supplied = base.model_copy(update={"candidate": base.candidate.model_copy(update={"score": 101})})
    elif case == "kill_switch":
        supplied = base.model_copy(update={"kill_switch": base.kill_switch.model_copy(update={"state": "INVALID"})})
    else:
        supplied = base.model_copy(update={"data_health": base.data_health.model_copy(update={"threshold": 0})})
    if case == "kill_switch":
        with pytest.warns(UserWarning, match="Pydantic serializer warnings"):
            with pytest.raises(ValidationError):
                evaluate_pure_risk(supplied)
    else:
        with pytest.raises(ValidationError):
            evaluate_pure_risk(supplied)


def test_d2b1_iv_p2_002_model_construct_attack_rejected():
    base = make_input()
    forged_portfolio = PortfolioExposureSnapshot.model_construct(
        **{**base.portfolio.__dict__, "open_position_count": 1}
    )
    supplied = PureRiskEvaluationInput.model_construct(
        **{**base.__dict__, "portfolio": forged_portfolio}
    )
    with pytest.raises(ValidationError, match="open-position count"):
        evaluate_pure_risk(supplied)


def test_d2b1_iv_p2_002_valid_input_is_unchanged_and_fingerprinted_from_prepared(monkeypatch):
    supplied = make_input(caller=Decimal("1.00"))
    original_dump = supplied.model_dump(mode="python", round_trip=True)
    captured = {}
    original_fingerprint = policy_core.compute_pure_risk_fingerprint

    def capture_fingerprint(prepared, normalized, target):
        captured["prepared"] = prepared
        return original_fingerprint(prepared, normalized, target)

    monkeypatch.setattr(policy_core, "compute_pure_risk_fingerprint", capture_fingerprint)
    result = evaluate_pure_risk(supplied)
    canonical_result = evaluate_pure_risk(PureRiskEvaluationInput.model_validate(original_dump))
    assert result == canonical_result
    assert supplied.model_dump(mode="python", round_trip=True) == original_dump
    assert captured["prepared"] is not supplied
    assert captured["prepared"] == supplied


def test_d2b1_iv_p2_003_ambient_decimal_context_cannot_change_result():
    evaluation_input = make_input(
        account_updates={
            "balance": Decimal("10000.5"),
            "equity": Decimal("10000.5"),
            "free_margin": Decimal("10000.5"),
            "peak_equity": Decimal("10000.5"),
        }
    )
    results = []
    for rounding, precision in (
        (ROUND_HALF_EVEN, 28),
        (ROUND_HALF_UP, 28),
        (ROUND_DOWN, 28),
        (ROUND_UP, 28),
        (ROUND_UP, 9),
    ):
        with localcontext() as caller_context:
            caller_context.rounding = rounding
            caller_context.prec = precision
            results.append(evaluate_pure_risk(evaluation_input))
    assert all(result == results[0] for result in results[1:])
    assert results[0].approved_risk_amount == Decimal("100.00")


def test_d2b1_iv_p2_003_decimal_fingerprint_rendering_is_context_independent():
    evaluation_input = make_input(caller=Decimal("1.00"))
    payloads = []
    for rounding, precision in ((ROUND_HALF_EVEN, 28), (ROUND_HALF_UP, 9), (ROUND_DOWN, 6)):
        with localcontext() as caller_context:
            caller_context.rounding = rounding
            caller_context.prec = precision
            payloads.append(
                build_pure_risk_semantic_payload(
                    evaluation_input,
                    Decimal("1.0000"),
                    Decimal("1E0"),
                )
            )
    assert len(set(payloads)) == 1
    assert {_canonical_decimal(value) for value in (Decimal("1.0"), Decimal("1.00"), Decimal("1E0"))} == {"1"}
    assert {_canonical_decimal(value) for value in (Decimal("0"), Decimal("-0"), Decimal("0.00"))} == {"0"}
    assert _canonical_decimal(Decimal("1000.0")) == "1000"
