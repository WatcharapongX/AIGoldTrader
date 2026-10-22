"""D2C stateless replay authority, direct-pure parity, and adversarial acceptance."""

import datetime as dt
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.backtesting import risk_replay as integration
from app.services.backtesting.domain import BacktestRunManifest, NewsVintageCoverage
from app.services.backtesting.fingerprint import config_fingerprint, coverage_fingerprint, historical_data_fingerprint
from app.services.backtesting.replay import replay
from app.services.backtesting.risk_replay import replay_risk
from app.services.backtesting.risk_replay_domain import (
    BacktestSymbolSpecAssumption,
    ReplayRiskEvent,
    RiskEvaluationStatus,
    RiskReplayConfig,
    RiskReplayError,
    RiskReplayFailureCode,
    RiskReplayResult,
)
from app.services.backtesting.risk_replay_fingerprint import risk_configuration_fingerprint, risk_event_fingerprint
from app.services.market_data.domain import SECONDS, Timeframe
from app.services.news.domain import EconomicEvent, ObservedQuote
from app.services.risk.domain import RiskPolicy
from app.services.risk.policy_core import evaluate_pure_risk
from app.services.risk.policy_domain import NewsAvailability, QuoteAvailability
from app.services.strategy.domain import Evidence, Target, TradePlanSuggestion
from app.services.strategy.engine import REGISTRY
from tests.test_backtesting_d2a import (
    END,
    START,
    WARMUP,
    candles,
    inputs,
    manifest,
    replace_coverage,
    replace_usable_end,
)

D = Decimal


def config(*, caller=None, news=False, policy_updates=None, spec_updates=None):
    return RiskReplayConfig(
        policy=RiskPolicy(news_risk_enabled=news, **(policy_updates or {})),
        caller_requested_risk_pct=caller,
        symbol_specification=BacktestSymbolSpecAssumption(
            **{
                "tick_size": D("0.01"),
                "tick_value": D("1"),
                "contract_size": D("100"),
                "volume_min": D("0.01"),
                "volume_max": D("10"),
                "volume_step": D("0.01"),
                "digits": 2,
                **(spec_updates or {}),
            }
        ),
    )


def quote(at, *, observed=None, bid="2000", ask="2000.3"):
    return ObservedQuote(timestamp=at, observed_at=observed or at, bid=D(bid), ask=D(ask), source="simulated")


def fresh_quotes():
    return tuple(quote(START + dt.timedelta(minutes=5 * i)) for i in range(17))


@pytest.fixture
def plan_strategy(monkeypatch):
    """Test-only suggestion fixture at the existing Strategy seam; real D2A still runs."""
    original = REGISTRY["STRAT01"].evaluate

    def evaluate(context, profile, strategy_config):
        candidate = original(context, profile, strategy_config)
        plan = TradePlanSuggestion(
            id="fixture_plan_" + candidate.id,
            candidate_id=candidate.id,
            symbol="XAUUSD",
            direction="LONG",
            entry_type="LIMIT_ZONE",
            entry_lower=D("2000"),
            entry_upper=D("2002"),
            entry_source_id="test_entry",
            stop_loss=D("1995"),
            stop_source_id="test_stop",
            invalidation_th="test-only structural invalidation",
            targets=(
                Target(name="TP1", price=D("2010"), source_id="test_target_1", rr=D("1.1")),
                Target(name="TP2", price=D("2020"), source_id="test_target_2", rr=D("2.5")),
            ),
            score=85,
            evidence=(Evidence(code="TEST", description_th="explicit test-only suggestion"),),
            warnings_th=(),
            news_state="CALM",
            status="SUGGESTION_ONLY",
            as_of=context.as_of,
            context_id=candidate.context_id,
            expires_at=context.as_of + dt.timedelta(hours=1),
        )
        return candidate.model_copy(
            update={"direction": "LONG", "status": "READY", "confirmed_at": context.as_of, "plan": plan}
        )

    monkeypatch.setattr(REGISTRY["STRAT01"], "evaluate", evaluate)


@pytest.fixture
def captured(monkeypatch):
    observed = []

    def evaluate(value):
        observed.append(value)
        return evaluate_pure_risk(value)

    monkeypatch.setattr(integration, "evaluate_pure_risk", evaluate)
    return observed


def scheduled_news(*, scheduled=START + dt.timedelta(minutes=10), available=WARMUP, version=1, impact="HIGH"):
    # Synthetic archived-LIVE-shaped input solely for authority tests, not historical market truth.
    return EconomicEvent(
        id="test_calendar_1",
        provider_event_id="test_calendar_1",
        occurrence_key="test_calendar_1",
        event_name="Test US high impact",
        event_code="TEST",
        group_id="test_group",
        country="US",
        currency="USD",
        category="OTHER",
        impact=impact,
        scheduled_at=scheduled,
        actual=None,
        forecast=None,
        previous=None,
        unit="NUMBER",
        status="SCHEDULED",
        source="historical_news",
        source_mode="LIVE",
        updated_at=available,
        available_at=available,
        revision_version=version,
    )


def archived_inputs(events=(), *, quotes=None, vintage_updates=None, values=None):
    kwargs = dict(
        news_events=events,
        quotes=fresh_quotes() if quotes is None else quotes,
        news_source="historical_news",
        news_mode="LIVE",
        calendar_available=True,
    )
    vintage = NewsVintageCoverage(
        **{
            "required": False,
            "available": True,
            "source": "historical_news",
            "vintage_start": WARMUP,
            "vintage_end": END,
            "availability_verified_at": END,
            **(vintage_updates or {}),
        }
    )
    base = replace_coverage(manifest(values=values, **kwargs), news_vintages=vintage)
    return inputs(values, manifest=base, **kwargs)


def assert_failure(code, operation):
    with pytest.raises(RiskReplayError) as error:
        operation()
    assert error.value.code is code
    assert str(error.value) == code.value


def test_real_strategy_no_plan_never_calls_risk_and_preserves_exact_linkage(monkeypatch):
    def forbidden(_):
        pytest.fail("A missing plan must not be evaluated")

    monkeypatch.setattr(integration, "evaluate_pure_risk", forbidden)
    source_inputs = inputs()
    source = replay(source_inputs, stop_at=START + dt.timedelta(minutes=10))
    result = replay_risk(source_inputs, config(), stop_at=source.cutoff)
    assert result.strategy_events_seen == result.no_plan_events == len(source.events) == 3
    assert result.risk_events_evaluated == 0
    assert result.source_replay_fingerprint == source.replay_fingerprint
    assert result.source_replay_input_fingerprint == source.replay_input_fingerprint
    for original, event in zip(source.events, result.events, strict=True):
        assert event.as_of == original.as_of
        assert event.candidate_id == original.candidate_id
        assert event.replay_strategy_event_fingerprint == original.event_fingerprint
        assert event.risk_evaluation_status is RiskEvaluationStatus.NOT_EVALUATED_NO_PLAN
        assert event.plan_id is event.pure_risk_result is event.risk_input_fingerprint is None
        assert (
            risk_event_fingerprint(event.model_dump(mode="python", exclude={"risk_event_fingerprint"}))
            == event.risk_event_fingerprint
        )


def test_direct_pure_oracle_same_time_baseline_and_no_state_evolution(plan_strategy, captured):
    source = inputs(quotes=fresh_quotes())
    result = replay_risk(source, config())
    assert result.strategy_events_seen == result.risk_events_evaluated == len(captured) == 17
    assert result.no_plan_events == 0
    assert len({value.account.account_id for value in captured}) == 1
    assert len({value.account.id for value in captured}) == 17
    for event, value in zip(result.events, captured, strict=True):
        assert event.pure_risk_result == evaluate_pure_risk(value)
        assert event.pure_risk_fingerprint == event.pure_risk_result.semantic_fingerprint
        assert event.pure_risk_result.decision == "APPROVED"
        assert value.as_of == value.account.as_of == value.account.observed_at == value.account.state_updated_at
        assert value.as_of == value.candidate.detected_at == value.trade_plan.as_of == event.as_of
        assert value.symbol_specification.observed_at == event.as_of
        assert value.account.balance == value.account.equity == value.account.peak_equity == D("10000")
        assert value.account.free_margin == D("10000")
        assert value.account.floating_pnl == value.account.daily_realized_pnl == value.account.weekly_realized_pnl == 0
        assert value.account.open_risk_pct == value.account.reserved_risk_pct == value.account.open_positions_count == 0
        assert value.account.consecutive_losses == 0
        assert value.account.last_loss_at is value.account.cooldown_until is None
        assert value.account.state_version == 1
        assert value.account.source == "CONFIGURED_TEST" and value.account.trading_mode == "BACKTEST"
        assert value.portfolio.open_risk_pct == value.portfolio.reserved_risk_pct == 0
        assert value.portfolio.symbol_risk_pct == value.portfolio.directional_risk_pct == 0
        assert value.portfolio.active_reservation_count == value.portfolio.open_position_count == 0
        assert value.portfolio.reservation_integrity.value == "OK"
        assert value.kill_switch.state.value == "INACTIVE"
        assert value.kill_switch.source == "BACKTEST_NO_EXTERNAL_KILL_SWITCH"
        assert value.data_health.state.value == "HEALTHY"
        assert value.data_health.source == "BACKTEST_CAUSAL_DATA_ADMISSION"
        assert value.data_health.threshold == value.policy.data_health_consecutive_failures
        assert value.data_health.consecutive_failures == 0
        assert value.candidate_lifecycle_status == "READY" and value.candidate_transition_count == 0
        assert value.symbol_specification.source == "BACKTEST_ASSUMPTION"
        assert value.symbol_specification.broker_server is None
        assert value.news.availability is NewsAvailability.UNAVAILABLE
    assert len({e.pure_risk_result.position_size for e in result.events}) == 1


@pytest.mark.parametrize("caller", [None, D("0"), D("0.5"), D("1"), D("2")])
@pytest.mark.parametrize("news", [False, True])
def test_exact_requested_risk_layers_match_pure(plan_strategy, captured, caller, news):
    source = archived_inputs((scheduled_news(),)) if news else inputs(quotes=fresh_quotes())
    result = replay_risk(source, config(caller=caller, news=news), stop_at=START)
    value = captured[0]
    pure = result.events[0].pure_risk_result
    assert value.caller_requested_risk_pct == pure.caller_requested_risk_pct == caller
    assert pure == evaluate_pure_risk(value)
    assert pure.normalized_requested_risk_pct == (caller or D("1"))
    assert pure.target_risk_pct == (caller or D("1")) * (D("0.5") if news else D("1"))
    assert pure.approved_risk_pct <= pure.target_risk_pct
    assert pure.decision == ("REDUCED" if news or caller == D("2") else "APPROVED")


def test_none_and_zero_are_distinct_audit_inputs_same_target(plan_strategy):
    source = inputs(quotes=fresh_quotes())
    first = replay_risk(source, config(), stop_at=START)
    second = replay_risk(source, config(caller=D("0")), stop_at=START)
    assert first.events[0].pure_risk_result.target_risk_pct == second.events[0].pure_risk_result.target_risk_pct
    assert first.risk_configuration_fingerprint != second.risk_configuration_fingerprint
    assert first.events[0].pure_risk_fingerprint != second.events[0].pure_risk_fingerprint


@pytest.mark.parametrize("caller", [D("-0.1"), D("NaN"), D("Infinity"), D("100.01"), D("0.000000001")])
def test_invalid_requested_risk_is_rejected(caller):
    with pytest.raises(ValidationError):
        config(caller=caller)


@pytest.mark.parametrize(
    "updates",
    [
        {"symbol": "EURUSD"},
        {"source": "broker"},
        {"tick_value": D("0")},
        {"tick_size": D("Infinity")},
        {"volume_step": D("0.1")},
        {"volume_max": D("0.001")},
        {"digits": 6},
    ],
)
def test_invalid_symbol_assumption_is_rejected(updates):
    with pytest.raises(ValidationError):
        config(spec_updates=updates)


def test_complete_policy_spec_and_caller_content_bind_configuration():
    base = config()
    for field in RiskPolicy.model_fields:
        payload = base.policy.model_dump(mode="python")
        current = payload[field]
        if field == "version":
            changed = "different-policy"
        elif isinstance(current, bool):
            changed = not current
        elif isinstance(current, int):
            changed = current + 1
        else:
            changed = current + D("0.001")
        # Fingerprint binds all fields independent of admission constraints for this hash-only probe.
        policy = base.policy.model_copy(update={field: changed})
        assert risk_configuration_fingerprint(
            base.model_copy(update={"policy": policy})
        ) != risk_configuration_fingerprint(base)
    for field in BacktestSymbolSpecAssumption.model_fields:
        if field in ("symbol", "source"):
            continue
        current = getattr(base.symbol_specification, field)
        changed = current + (1 if field == "digits" else D("0.001"))
        spec = base.symbol_specification.model_copy(update={field: changed})
        assert risk_configuration_fingerprint(
            base.model_copy(update={"symbol_specification": spec})
        ) != risk_configuration_fingerprint(base)


def test_mutated_or_constructed_config_and_policy_version_fail_closed():
    good = config()
    wrong_policy = good.model_copy(update={"policy": good.policy.model_copy(update={"version": "wrong"})})
    assert_failure(RiskReplayFailureCode.CONFIGURATION_INVALID, lambda: replay_risk(inputs(), wrong_policy))
    bad_spec = good.symbol_specification.model_copy(update={"tick_value": D("0")})
    assert_failure(
        RiskReplayFailureCode.SYMBOL_SPEC_INVALID,
        lambda: replay_risk(inputs(), good.model_copy(update={"symbol_specification": bad_spec})),
    )
    bad_caller = good.model_copy(update={"caller_requested_risk_pct": D("NaN")})
    assert_failure(RiskReplayFailureCode.CONFIGURATION_INVALID, lambda: replay_risk(inputs(), bad_caller))


def test_news_risk_requires_historical_vintage_even_for_nonnews_no_plan_strategy(captured):
    assert_failure(RiskReplayFailureCode.NEWS_UNAVAILABLE, lambda: replay_risk(inputs(), config(news=True)))
    assert captured == []
    result = replay_risk(archived_inputs(), config(news=True), stop_at=START)
    assert result.no_plan_events == 1  # A complete empty calendar is not missing coverage.


@pytest.mark.parametrize(
    "changes",
    [
        {
            "available": False,
            "source": None,
            "vintage_start": None,
            "vintage_end": None,
            "availability_verified_at": None,
        },
        {"vintage_start": START + dt.timedelta(minutes=1)},
        {"vintage_end": END - dt.timedelta(minutes=1)},
        {"source": "another_source"},
    ],
)
def test_incomplete_or_mismatched_risk_news_vintage_rejected(changes):
    assert_failure(
        RiskReplayFailureCode.NEWS_UNAVAILABLE,
        lambda: replay_risk(archived_inputs(vintage_updates=changes), config(news=True)),
    )


def test_fixture_calendar_is_not_historical_news_authority():
    source = inputs(news_source="fixture_news", news_mode="FIXTURE", calendar_available=True)
    vintage = NewsVintageCoverage(
        required=False,
        available=True,
        source="fixture_news",
        vintage_start=WARMUP,
        vintage_end=END,
        availability_verified_at=END,
    )
    source = source.model_copy(update={"manifest": replace_coverage(source.manifest, news_vintages=vintage)})
    assert_failure(RiskReplayFailureCode.NEWS_UNAVAILABLE, lambda: replay_risk(source, config(news=True)))


@pytest.mark.parametrize("strategy", ["STRAT05", "STRAT06"])
def test_disabled_risk_news_does_not_bypass_strategy_news_admission(strategy):
    # Factory bypass retains the manifest; D2C must still invoke authoritative D2A preparation.
    base = inputs()
    source = base.model_copy(update={"manifest": manifest(strategy_id=strategy)})
    assert_failure(RiskReplayFailureCode.NEWS_UNAVAILABLE, lambda: replay_risk(source, config()))


def test_news_latest_known_revision_pre_reduction_blackout_and_future_invariance(plan_strategy, captured):
    original = scheduled_news()
    future = scheduled_news(available=START + dt.timedelta(minutes=30), version=2, impact="LOW")
    source = archived_inputs((original,))
    suffix = archived_inputs((original, future))
    first = replay_risk(source, config(news=True), stop_at=START + dt.timedelta(minutes=5))
    assert [e.pure_risk_result.decision for e in first.events] == ["REDUCED", "BLOCKED"]
    assert all(value.news.events[0].revision_version == 1 for value in captured)
    second = replay_risk(suffix, config(news=True), stop_at=first.cutoff)
    assert first.events == second.events
    assert first.risk_replay_fingerprint == second.risk_replay_fingerprint
    assert first.risk_replay_input_fingerprint != second.risk_replay_input_fingerprint
    captured.clear()
    replay_risk(suffix, config(news=True), stop_at=START + dt.timedelta(minutes=30))
    assert captured[-1].news.events[0].revision_version == 2
    assert captured[-1].news.events[0].impact == "LOW"


@pytest.mark.parametrize(
    "quotes,availability,decision",
    [
        ((), QuoteAvailability.UNAVAILABLE, "BLOCKED"),
        ((quote(START - dt.timedelta(seconds=20)),), QuoteAvailability.AVAILABLE, "BLOCKED"),
        ((quote(START),), QuoteAvailability.AVAILABLE, "APPROVED"),
        ((quote(START, ask="2002"),), QuoteAvailability.AVAILABLE, "BLOCKED"),
    ],
)
def test_quote_absent_stale_fresh_and_spread_remain_pure_policy_results(
    plan_strategy, captured, quotes, availability, decision
):
    result = replay_risk(inputs(quotes=quotes), config(), stop_at=START)
    assert captured[0].quote.availability is availability
    assert result.events[0].pure_risk_result.decision == decision
    assert result.risk_events_evaluated == 1
    assert result.events[0].pure_risk_result == evaluate_pure_risk(captured[0])


def test_latest_market_timestamp_and_observation_both_required(plan_strategy, captured):
    earlier = quote(START - dt.timedelta(seconds=2))
    observed_future = quote(START - dt.timedelta(seconds=1), observed=START + dt.timedelta(seconds=1), ask="2009")
    timestamp_future = quote(START + dt.timedelta(seconds=1), ask="2009")
    result = replay_risk(inputs(quotes=(earlier, observed_future, timestamp_future)), config(), stop_at=START)
    assert captured[0].quote.timestamp == earlier.timestamp
    assert result.events[0].quote_observed_at == earlier.observed_at
    assert result.events[0].pure_risk_result.decision == "APPROVED"


def test_future_only_quote_is_unavailable_not_candle_fallback(plan_strategy, captured):
    result = replay_risk(inputs(quotes=(quote(START + dt.timedelta(seconds=1)),)), config(), stop_at=START)
    assert captured[0].quote.availability is QuoteAvailability.UNAVAILABLE
    assert result.events[0].quote_timestamp is result.events[0].quote_observed_at is None
    assert result.events[0].pure_risk_result.decision == "BLOCKED"


def test_prefix_only_source_and_future_candle_and_quote_mutations_do_not_change_prior_output(plan_strategy):
    prefix_cutoff = START + dt.timedelta(minutes=5)
    values = candles()
    source = inputs(values, quotes=fresh_quotes())
    first = replay_risk(source, config(), stop_at=prefix_cutoff)
    changed = dict(values)
    future = values[Timeframe.M1][-1].model_copy(update={"volume": D("777")})
    changed[Timeframe.M1] = values[Timeframe.M1][:-1] + (future,)
    second = replay_risk(
        inputs(changed, quotes=fresh_quotes()[:-1] + (quote(END, ask="2009"),)), config(), stop_at=prefix_cutoff
    )
    assert first.events == second.events
    assert first.risk_replay_fingerprint == second.risk_replay_fingerprint
    assert first.risk_replay_input_fingerprint != second.risk_replay_input_fingerprint
    # Full source versus source truncated to the causal candle prefix; keep the same requested period/seed.
    prefix = {frame: tuple(c for c in bars if c.open_time <= prefix_cutoff) for frame, bars in values.items()}
    prefix_quotes = tuple(q for q in fresh_quotes() if q.timestamp <= prefix_cutoff)
    governed = replace_usable_end(source.manifest, prefix_cutoff)
    frame_coverage = tuple(
        frame.model_copy(
            update={
                "available_end": prefix[frame.timeframe][-1].open_time + dt.timedelta(seconds=SECONDS[frame.timeframe]),
                "requested_events": len(prefix[frame.timeframe]),
                "available_events": len(prefix[frame.timeframe]),
            }
        )
        for frame in governed.coverage.timeframe_coverage
    )
    governed = replace_coverage(
        governed,
        timeframe_coverage=frame_coverage,
        requested_primary_events=len(prefix[Timeframe.M5]),
        available_primary_events=len(prefix[Timeframe.M5]),
        total_candle_inputs=sum(map(len, prefix.values())),
        data_fingerprint=historical_data_fingerprint(
            symbol="XAUUSD",
            source="simulated",
            candles=prefix,
            quotes=prefix_quotes,
            news_source="historical_unavailable",
            news_mode="UNAVAILABLE",
            calendar_available=False,
        ),
    )
    prefix_result = replay_risk(
        inputs(prefix, manifest=governed, quotes=prefix_quotes), config(), stop_at=prefix_cutoff
    )
    assert prefix_result.events == first.events
    assert prefix_result.risk_replay_fingerprint == first.risk_replay_fingerprint
    shorter_config = governed.config.model_copy(update={"end": prefix_cutoff})
    shorter_coverage = governed.coverage.model_copy(update={"requested_end": prefix_cutoff})
    shorter_provenance = governed.provenance.model_copy(
        update={
            "requested_end": prefix_cutoff,
            "configuration_fingerprint": config_fingerprint(shorter_config),
            "data_coverage_fingerprint": coverage_fingerprint(shorter_coverage),
        }
    )
    shorter_manifest = BacktestRunManifest(
        config=shorter_config,
        coverage=shorter_coverage,
        provenance=shorter_provenance,
        resource_policy_fingerprint=governed.resource_policy_fingerprint,
    )
    shorter = replay_risk(inputs(prefix, manifest=shorter_manifest, quotes=prefix_quotes), config())
    assert shorter.events == first.events
    assert shorter.risk_replay_fingerprint == first.risk_replay_fingerprint
    assert shorter.risk_replay_input_fingerprint != first.risk_replay_input_fingerprint


def test_cutoff_full_and_prefix_results_match_at_each_event(plan_strategy):
    source = inputs(quotes=fresh_quotes())
    full = replay_risk(source, config())
    for at in (event.as_of for event in full.events):
        prefix = replay_risk(source, config(), stop_at=at)
        assert prefix.events == tuple(event for event in full.events if event.as_of <= at)
        assert prefix.cutoff == at


def test_private_snapshot_resists_mutation_during_replay(plan_strategy, monkeypatch):
    source = inputs(quotes=fresh_quotes())
    configuration = config()
    expected = replay_risk(source, configuration, stop_at=START + dt.timedelta(minutes=5))
    original = integration.replay

    def mutate(private, **kwargs):
        source.candles[Timeframe.M1][0].volume = D("999")
        object.__setattr__(configuration.policy, "max_risk_per_trade_pct", D("5"))
        return original(private, **kwargs)

    monkeypatch.setattr(integration, "replay", mutate)
    assert replay_risk(source, configuration, stop_at=expected.cutoff) == expected
    assert_failure(RiskReplayFailureCode.INPUT_INVALID, lambda: replay_risk(source, config(), stop_at=START))


def test_initial_balance_changes_baseline_sizing_and_identity(plan_strategy, captured):
    source = inputs(quotes=fresh_quotes())
    first = replay_risk(source, config(), stop_at=START)
    base = source.manifest
    changed_config = base.config.model_copy(update={"initial_balance": D("20000")})
    provenance = base.provenance.model_copy(update={"configuration_fingerprint": config_fingerprint(changed_config)})
    changed_manifest = BacktestRunManifest(
        config=changed_config,
        coverage=base.coverage,
        provenance=provenance,
        resource_policy_fingerprint=base.resource_policy_fingerprint,
    )
    second = replay_risk(source.model_copy(update={"manifest": changed_manifest}), config(), stop_at=START)
    assert captured[1].account.balance == D("20000")
    assert captured[0].account.account_id != captured[1].account.account_id
    assert (
        second.events[0].pure_risk_result.approved_risk_amount
        == 2 * first.events[0].pure_risk_result.approved_risk_amount
    )
    assert second.events[0].pure_risk_result.position_size > first.events[0].pure_risk_result.position_size


def test_repeat_json_and_fingerprints_ignore_ambient_decimal_context(plan_strategy):
    source = inputs(quotes=fresh_quotes())
    configuration = config(caller=D("0.33333333"))
    expected = replay_risk(source, configuration, stop_at=START).model_dump_json()
    for precision, rounding in ((3, ROUND_UP), (9, ROUND_DOWN), (50, ROUND_UP)):
        with localcontext() as context:
            context.prec = precision
            context.rounding = rounding
            context.Emax = 9
            context.Emin = -9
            assert replay_risk(source, configuration, stop_at=START).model_dump_json() == expected


def test_terminal_candidate_status_is_not_filtered(plan_strategy, captured, monkeypatch):
    original = REGISTRY["STRAT01"].evaluate

    def cancelled(*args):
        return original(*args).model_copy(update={"status": "INVALIDATED"})

    monkeypatch.setattr(REGISTRY["STRAT01"], "evaluate", cancelled)
    result = replay_risk(inputs(quotes=fresh_quotes()), config(), stop_at=START)
    assert result.risk_events_evaluated == 1
    assert captured[0].candidate_lifecycle_status == "INVALIDATED"
    assert result.events[0].pure_risk_result.decision == "BLOCKED"


def test_public_errors_resource_causality_and_pure_failure_are_stable(plan_strategy, monkeypatch):
    source = inputs(quotes=fresh_quotes())
    monkeypatch.setattr(integration, "MAX_CANDIDATES_PER_RUN", 0)
    assert_failure(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED, lambda: replay_risk(source, config(), stop_at=START))
    monkeypatch.setattr(integration, "MAX_CANDIDATES_PER_RUN", 100000)
    monkeypatch.setattr(integration, "MAX_ESTIMATED_OUTPUT_BYTES", 1)
    assert_failure(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED, lambda: replay_risk(source, config(), stop_at=START))
    monkeypatch.setattr(integration, "MAX_ESTIMATED_OUTPUT_BYTES", 128 * 1024 * 1024)

    def broken(_):
        raise RuntimeError("internal failure must not escape as public text")

    monkeypatch.setattr(integration, "evaluate_pure_risk", broken)
    assert_failure(RiskReplayFailureCode.POLICY_EVALUATION_FAILED, lambda: replay_risk(source, config(), stop_at=START))


def test_plan_future_time_is_rejected_before_pure_call(plan_strategy, captured, monkeypatch):
    original = REGISTRY["STRAT01"].evaluate

    def future(*args):
        candidate = original(*args)
        return candidate.model_copy(
            update={
                "plan": candidate.plan.model_copy(update={"as_of": candidate.detected_at + dt.timedelta(minutes=1)})
            }
        )

    monkeypatch.setattr(REGISTRY["STRAT01"], "evaluate", future)
    assert_failure(RiskReplayFailureCode.CAUSALITY_VIOLATION, lambda: replay_risk(inputs(), config(), stop_at=START))
    assert captured == []


def test_news_projection_bound_fails_closed(plan_strategy):
    events = tuple(scheduled_news().model_copy(update={"id": f"test_news_{i}"}) for i in range(201))
    source = archived_inputs(events)
    assert_failure(
        RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED,
        lambda: integration._news_at(source, config(news=True), START),
    )
    # Existing D2A news-context max_length admission fires first in the full orchestrator.
    assert_failure(
        RiskReplayFailureCode.CAUSALITY_VIOLATION, lambda: replay_risk(source, config(news=True), stop_at=START)
    )


def test_contracts_are_frozen_and_reject_counter_order_and_evidence_mismatch():
    result = replay_risk(inputs(), config(), stop_at=START + dt.timedelta(minutes=5))
    with pytest.raises(ValidationError):
        result.no_plan_events = 100
    for update in ({"events": result.events[::-1]}, {"no_plan_events": 0}, {"cutoff": WARMUP}):
        with pytest.raises(ValidationError):
            RiskReplayResult.model_validate({**result.model_dump(mode="python"), **update})
    no_plan = result.events[0]
    with pytest.raises(ValidationError):
        ReplayRiskEvent.model_validate({**no_plan.model_dump(mode="python"), "plan_id": "fabricated"})
    with pytest.raises(ValidationError):
        ReplayRiskEvent.model_validate({**no_plan.model_dump(mode="python"), "risk_evaluation_status": "EVALUATED"})


@pytest.mark.parametrize(
    "perturb", ["reversed", "duplicate", "beyond_cutoff", "naive_event_as_of", "naive_cutoff", "non_event"]
)
def test_perturbed_d2a_event_order_fails_with_stable_causality_code(monkeypatch, perturb):
    """D2C-IV-P2-001/D2C-IV-P3-001: perturbed D2A streams must not leak raw errors."""
    source_inputs = inputs()
    source = replay(source_inputs, stop_at=START + dt.timedelta(minutes=10))
    assert len(source.events) >= 2
    if perturb == "reversed":
        perturbed_events = source.events[::-1]
        forged = source.model_copy(update={"events": perturbed_events})
    elif perturb == "duplicate":
        perturbed_events = (source.events[0],) + source.events
        forged = source.model_copy(update={"events": perturbed_events})
    elif perturb == "naive_event_as_of":
        naive = source.events[-1].model_copy(update={"as_of": source.events[-1].as_of.replace(tzinfo=None)})
        forged = source.model_copy(update={"events": source.events[:-1] + (naive,)})
    elif perturb == "naive_cutoff":
        forged = source.model_copy(update={"cutoff": source.cutoff.replace(tzinfo=None)})
    elif perturb == "non_event":
        forged = source.model_copy(update={"events": (None,) + source.events})
    else:
        late = source.events[-1].model_copy(update={"as_of": source.cutoff + dt.timedelta(minutes=1)})
        perturbed_events = source.events[:-1] + (late,)
        forged = source.model_copy(update={"events": perturbed_events})
    # raising=True (string form): fail loudly if the seam is ever renamed.
    monkeypatch.setattr(integration, "replay", lambda *args, **kwargs: forged, raising=True)
    with pytest.raises(RiskReplayError) as error:
        replay_risk(source_inputs, config(), stop_at=source.cutoff)
    assert not isinstance(error.value, (TypeError, ValidationError))
    assert error.value.code is RiskReplayFailureCode.CAUSALITY_VIOLATION
    assert str(error.value) == RiskReplayFailureCode.CAUSALITY_VIOLATION.value


def _plan_bearing_source():
    source_inputs = inputs(quotes=fresh_quotes())
    source = replay(source_inputs, stop_at=START)
    assert source.events and source.events[0].trade_plan is not None
    return source_inputs, source


def test_forged_plain_object_event(plan_strategy, captured, monkeypatch):
    """D2C-IV-P2-003: a duck-typed copy of a real plan event must not be evaluated."""
    source_inputs, source = _plan_bearing_source()
    real = source.events[0]
    forged_event = SimpleNamespace(
        as_of=real.as_of,
        profile_id=real.profile_id,
        strategy_id=real.strategy_id,
        context_id=real.context_id,
        candidate_id=real.candidate_id,
        candidate_status=real.candidate_status,
        context=real.context,
        candidate=real.candidate,
        trade_plan=real.trade_plan,
        event_fingerprint=real.event_fingerprint,
    )
    forged = source.model_copy(update={"events": (forged_event,)})
    monkeypatch.setattr(integration, "replay", lambda *args, **kwargs: forged, raising=True)
    assert_failure(
        RiskReplayFailureCode.CAUSALITY_VIOLATION,
        lambda: replay_risk(source_inputs, config(), stop_at=source.cutoff),
    )
    assert captured == []


def test_partial_object_event(plan_strategy, captured, monkeypatch):
    """D2C-IV-P3-002a: an object with only sort keys must fail stably, not AttributeError."""
    source_inputs, source = _plan_bearing_source()
    real = source.events[0]
    partial_event = SimpleNamespace(
        as_of=real.as_of,
        profile_id=real.profile_id,
        strategy_id=real.strategy_id,
        candidate_id=real.candidate_id,
    )
    forged = source.model_copy(update={"events": (partial_event,)})
    monkeypatch.setattr(integration, "replay", lambda *args, **kwargs: forged, raising=True)
    assert_failure(
        RiskReplayFailureCode.CAUSALITY_VIOLATION,
        lambda: replay_risk(source_inputs, config(), stop_at=source.cutoff),
    )
    assert captured == []


def test_bogus_trade_plan_object(plan_strategy, captured, monkeypatch):
    """D2C-IV-P3-002b: trade_plan=object() must fail stably, not AttributeError."""
    source_inputs, source = _plan_bearing_source()
    bogus_event = source.events[0].model_copy(update={"trade_plan": object()})
    forged = source.model_copy(update={"events": (bogus_event,)})
    monkeypatch.setattr(integration, "replay", lambda *args, **kwargs: forged, raising=True)
    assert_failure(
        RiskReplayFailureCode.CAUSALITY_VIOLATION,
        lambda: replay_risk(source_inputs, config(), stop_at=source.cutoff),
    )
    assert captured == []


def test_adapter_accepts_inputs_not_external_replay_results():
    assert_failure(RiskReplayFailureCode.INPUT_INVALID, lambda: replay_risk(replay(inputs()), config()))
    assert_failure(
        RiskReplayFailureCode.INPUT_INVALID, lambda: replay_risk(inputs(), config(), stop_at=START.replace(tzinfo=None))
    )


@pytest.mark.parametrize("caller", [None, D("0"), D("0.5"), D("1"), D("2")])
@pytest.mark.parametrize("blocked", ["NO_QUOTE", "STALE_QUOTE", "BELOW_MIN_SIZE", "BLACKOUT"])
def test_requested_layers_on_blocked_paths_match_exact_direct_pure(plan_strategy, captured, caller, blocked):
    if blocked == "BLACKOUT":
        source = archived_inputs((scheduled_news(scheduled=START + dt.timedelta(minutes=3)),))
        configuration = config(caller=caller, news=True)
    else:
        quotes = (
            ()
            if blocked == "NO_QUOTE"
            else ((quote(START - dt.timedelta(seconds=20)),) if blocked == "STALE_QUOTE" else (quote(START),))
        )
        source = inputs(quotes=quotes)
        configuration = config(
            caller=caller, spec_updates={"tick_value": D("10000")} if blocked == "BELOW_MIN_SIZE" else None
        )
    result = replay_risk(source, configuration, stop_at=START)
    pure = result.events[0].pure_risk_result
    assert pure == evaluate_pure_risk(captured[0])
    assert pure.decision == "BLOCKED"
    assert pure.caller_requested_risk_pct == caller
    assert pure.normalized_requested_risk_pct == (caller or D("1"))
    assert pure.approved_risk_pct == pure.approved_risk_amount == pure.position_size == 0


def test_usable_end_is_hard_ceiling_and_warmup_is_not_reportable(plan_strategy):
    source = inputs(quotes=fresh_quotes())
    usable_end = START + dt.timedelta(minutes=10)
    source = source.model_copy(update={"manifest": replace_usable_end(source.manifest, usable_end)})
    result = replay_risk(source, config(), stop_at=END + dt.timedelta(days=1))
    assert result.cutoff == usable_end
    assert result.strategy_events_seen == 3
    warmup = replay_risk(source, config(), stop_at=START - dt.timedelta(minutes=5))
    assert warmup.strategy_events_seen == warmup.risk_events_evaluated == warmup.no_plan_events == 0
    assert warmup.events == ()


def test_total_output_envelope_is_bounded_even_without_evaluated_events(monkeypatch):
    source = inputs()
    result = replay_risk(source, config(), stop_at=START)
    wire_size = len(result.model_dump_json().encode("utf-8"))
    monkeypatch.setattr(integration, "MAX_ESTIMATED_OUTPUT_BYTES", wire_size)
    assert replay_risk(source, config(), stop_at=START) == result
    monkeypatch.setattr(integration, "MAX_ESTIMATED_OUTPUT_BYTES", wire_size - 1)
    assert_failure(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED, lambda: replay_risk(source, config(), stop_at=START))


def test_d2a_resource_rejection_is_preserved_as_stable_d2c_failure(monkeypatch):
    from app.services.backtesting import replay as replay_module

    source = inputs(quotes=fresh_quotes())
    monkeypatch.setattr(replay_module, "_MAX_QUOTES", 1)
    assert_failure(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED, lambda: replay_risk(source, config(), stop_at=START))


def test_quote_observation_identity_is_bound_without_changing_pure_policy(plan_strategy):
    first_quote = quote(START - dt.timedelta(seconds=2))
    changed_quote = first_quote.model_copy(update={"observed_at": START - dt.timedelta(seconds=1)})
    first = replay_risk(inputs(quotes=(first_quote,)), config(), stop_at=START)
    second = replay_risk(inputs(quotes=(changed_quote,)), config(), stop_at=START)
    assert first.events[0].pure_risk_result.model_dump(
        exclude={"semantic_payload", "semantic_fingerprint"}
    ) == second.events[0].pure_risk_result.model_dump(exclude={"semantic_payload", "semantic_fingerprint"})
    assert first.events[0].risk_input_fingerprint != second.events[0].risk_input_fingerprint
    assert first.events[0].risk_event_fingerprint != second.events[0].risk_event_fingerprint


def test_duplicate_revision_conflict_is_rejected_in_private_admission():
    source = archived_inputs((scheduled_news(),))
    conflict = scheduled_news().model_copy(update={"impact": "LOW"})
    forged = source.model_copy(update={"news_events": source.news_events + (conflict,)})
    assert_failure(RiskReplayFailureCode.INPUT_INVALID, lambda: replay_risk(forged, config(news=True), stop_at=START))


def test_policy_canonical_expansion_is_bounded_before_hash_allocation():
    huge = config(policy_updates={"min_volume": D("1e-1000000000")})
    assert_failure(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED, lambda: replay_risk(inputs(), huge, stop_at=START))


def test_evaluated_event_hash_recomputes_from_complete_normalized_contract(plan_strategy):
    evaluated = replay_risk(inputs(quotes=fresh_quotes()), config(), stop_at=START).events[0]
    assert (
        risk_event_fingerprint(evaluated.model_dump(mode="python", exclude={"risk_event_fingerprint"}))
        == evaluated.risk_event_fingerprint
    )
