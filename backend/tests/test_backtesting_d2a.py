"""D2A causal replay, projection, determinism, and bounded-failure acceptance."""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.backtesting.domain import (
    REPLAY_ENGINE_VERSION,
    BacktestProvenance,
    BacktestRunConfig,
    BacktestRunManifest,
    CostAssumptions,
    CoverageStatus,
    DataCoverage,
    NewsVintageCoverage,
    TimeframeCoverage,
)
from app.services.backtesting.fingerprint import config_fingerprint, coverage_fingerprint, resource_policy_fingerprint
from app.services.backtesting.policy import BacktestResourcePolicy
from app.services.backtesting.replay import make_replay_inputs, replay
from app.services.backtesting.replay_domain import ReplayClock, ReplayError, ReplayFailureCode, ReplayStrategyEvent
from app.services.market_data.domain import SECONDS, Candle, Timeframe, bucket
from app.services.news.domain import EconomicEvent, ObservedQuote

D = Decimal
UTC = dt.UTC
WARMUP = dt.datetime(2025, 1, 6, 8, tzinfo=UTC)
START = dt.datetime(2025, 1, 6, 10, 40, tzinfo=UTC)
END = dt.datetime(2025, 1, 6, 12, tzinfo=UTC)
FRAMES = tuple(Timeframe)


def candle(timeframe: Timeframe, opened: dt.datetime, price: str = "2000") -> Candle:
    value = D(price)
    return Candle(
        symbol="XAUUSD",
        timeframe=timeframe,
        open_time=bucket(opened, timeframe),
        open=value,
        high=value + D("1"),
        low=value - D("1"),
        close=value + D("0.25"),
        volume=D("10"),
        bid_close=value + D("0.25"),
        ask_close=None,
        source="simulated",
        is_closed=True,
    )


def candles() -> dict[Timeframe, tuple[Candle, ...]]:
    result: dict[Timeframe, tuple[Candle, ...]] = {}
    for timeframe in FRAMES:
        step = dt.timedelta(seconds=SECONDS[timeframe])
        anchor = bucket(START, timeframe)
        result[timeframe] = tuple(candle(timeframe, anchor - step * offset, str(2000 + offset)) for offset in (2, 1))
    result[Timeframe.M1] = tuple(
        candle(Timeframe.M1, WARMUP + dt.timedelta(minutes=index), str(2000 + index % 7)) for index in range(240)
    )
    result[Timeframe.M5] = tuple(
        candle(Timeframe.M5, dt.datetime(2025, 1, 6, 10, minute, tzinfo=UTC), str(2000 + minute / 10))
        for minute in (30, 35, 40, 45, 50, 55)
    )
    result[Timeframe.H1] = (
        candle(Timeframe.H1, dt.datetime(2025, 1, 6, 8, tzinfo=UTC), "1998"),
        candle(Timeframe.H1, dt.datetime(2025, 1, 6, 9, tzinfo=UTC), "1999"),
        candle(Timeframe.H1, dt.datetime(2025, 1, 6, 10, tzinfo=UTC), "2000"),
    )
    return result


def manifest(*, strategy_id="STRAT01", profile_id="research", values=None) -> BacktestRunManifest:
    values = values or candles()
    config = BacktestRunConfig(
        start=START,
        end=END,
        timeframe=Timeframe.M5,
        strategy_id=strategy_id,
        profile_id=profile_id,
        initial_balance=D("10000"),
        costs=CostAssumptions(
            spread_price=D("0.3"), slippage_price_per_side=D("0.01"), commission_usd_per_lot_per_side=D("3.5")
        ),
    )
    frame_coverage = tuple(
        TimeframeCoverage(
            timeframe=timeframe,
            available_start=WARMUP,
            available_end=END,
            requested_events=len(values[timeframe]),
            available_events=len(values[timeframe]),
            source="simulated",
        )
        for timeframe in FRAMES
    )
    news_required = strategy_id in ("STRAT05", "STRAT06")
    news = NewsVintageCoverage(
        required=news_required,
        available=news_required,
        source="fixture_news" if news_required else None,
        vintage_start=WARMUP if news_required else None,
        vintage_end=END if news_required else None,
        availability_verified_at=END if news_required else None,
    )
    coverage = DataCoverage(
        requested_start=START,
        requested_end=END,
        warmup_start=WARMUP,
        usable_start=START,
        usable_end=END,
        timeframe=Timeframe.M5,
        source="simulated",
        requested_primary_events=len(values[Timeframe.M5]),
        available_primary_events=len(values[Timeframe.M5]),
        total_candle_inputs=sum(map(len, values.values())),
        required_timeframes=FRAMES,
        timeframe_coverage=frame_coverage,
        news_vintages=news,
        data_fingerprint="a" * 64,
        status=CoverageStatus.SUFFICIENT,
    )
    provenance = BacktestProvenance(
        market_source="simulated",
        timeframes=FRAMES,
        requested_start=START,
        requested_end=END,
        usable_start=START,
        usable_end=END,
        strategy_id=strategy_id,
        strategy_version="strategy-1.2.1",
        profile_id=profile_id,
        risk_policy_version="risk-policy-1.0.0",
        costs=config.costs,
        data_coverage_fingerprint=coverage_fingerprint(coverage),
        data_fingerprint=coverage.data_fingerprint,
        configuration_fingerprint=config_fingerprint(config),
    )
    return BacktestRunManifest(
        config=config,
        coverage=coverage,
        provenance=provenance,
        resource_policy_fingerprint=resource_policy_fingerprint(BacktestResourcePolicy()),
    )


def inputs(values=None, **changes):
    values = values or candles()
    args = {"manifest": manifest(values=values), "candles": values, "tick_size": D("0.01")}
    args.update(changes)
    return make_replay_inputs(**args)


def event(replay_result, at):
    return next(item for item in replay_result.events if item.as_of == at)


def semantic(result):
    return tuple(item.model_dump(mode="json") for item in result.events)


def news_revision(*, version: int, available_at: dt.datetime, actual: str) -> EconomicEvent:
    scheduled = dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC)
    return EconomicEvent(
        id="nfp-2025-01",
        provider_event_id="nfp-2025-01",
        occurrence_key="nfp-2025-01",
        event_name="Non-Farm Payrolls",
        event_code="NFP",
        group_id="labor-2025-01",
        country="US",
        currency="USD",
        category="EMPLOYMENT",
        impact="HIGH",
        scheduled_at=scheduled,
        actual=D(actual),
        forecast=D("150"),
        previous=D("140"),
        revised_previous=D("141") if version > 1 else None,
        previous_before_revision=D("140") if version > 1 else None,
        unit="THOUSANDS",
        status="REVISED" if version > 1 else "RELEASED",
        source="fixture_news",
        source_mode="FIXTURE",
        updated_at=available_at,
        available_at=available_at,
        released_at=scheduled,
        revision_version=version,
        direction_rule="HIGHER_IS_POSITIVE",
    )


def test_replay_clock_requires_aware_strictly_monotonic_utc():
    clock = ReplayClock()
    offset = dt.datetime(2025, 1, 6, 17, 0, tzinfo=dt.timezone(dt.timedelta(hours=7)))
    assert clock.advance(offset) == dt.datetime(2025, 1, 6, 10, 0, tzinfo=UTC)
    with pytest.raises(ReplayError) as repeated:
        clock.advance(offset)
    assert repeated.value.code is ReplayFailureCode.NON_MONOTONIC
    with pytest.raises(ReplayError) as naive:
        ReplayClock().advance(offset.replace(tzinfo=None))
    assert naive.value.code is ReplayFailureCode.INPUT_INVALID


def test_primary_events_are_m5_closes_and_warmup_is_not_reported():
    result = replay(inputs(), stop_at=dt.datetime(2025, 1, 6, 10, 50, tzinfo=UTC))
    assert [item.as_of for item in result.events] == [
        dt.datetime(2025, 1, 6, 10, 40, tzinfo=UTC),
        dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC),
        dt.datetime(2025, 1, 6, 10, 50, tzinfo=UTC),
    ]
    assert result.primary_events_processed == 4
    assert all(item.context.mode == "REPLAY" for item in result.events)


def test_higher_timeframe_is_visible_only_at_its_own_close():
    result = replay(inputs(), stop_at=dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC))
    before = event(result, dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC)).context.frame(Timeframe.H1)
    boundary = event(result, dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC)).context.frame(Timeframe.H1)
    assert before is not None and boundary is not None
    assert before.bars == 2
    assert boundary.bars == 3
    for timeframe in (Timeframe.H4, Timeframe.D1, Timeframe.W1):
        frame = event(result, dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC)).context.frame(timeframe)
        assert frame is not None
        assert all(
            item.open_time + dt.timedelta(seconds=SECONDS[timeframe]) <= frame.as_of
            for item in frame.candles
        )


def test_full_input_cutoff_equals_causal_prefix_for_multiple_cutoffs():
    values = candles()
    governed_manifest = manifest(values=values)
    for cutoff in (
        dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC),
        dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC),
        dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC),
    ):
        prefix = {
            timeframe: tuple(
                item
                for item in frame
                if item.open_time + dt.timedelta(seconds=SECONDS[timeframe]) <= cutoff
            )
            for timeframe, frame in values.items()
        }
        full = replay(make_replay_inputs(manifest=governed_manifest, candles=values), stop_at=cutoff)
        causal = replay(make_replay_inputs(manifest=governed_manifest, candles=prefix), stop_at=cutoff)
        assert semantic(full) == semantic(causal)
        assert full.replay_fingerprint == causal.replay_fingerprint


def test_future_primary_candle_mutation_and_removal_do_not_change_prefix():
    values = candles()
    cutoff = dt.datetime(2025, 1, 6, 10, 50, tzinfo=UTC)
    mutated = dict(values)
    future = values[Timeframe.M5][-1]
    mutated[Timeframe.M5] = values[Timeframe.M5][:-1] + (
        future.model_copy(
            update={
                "open": D("2500"),
                "high": D("2502"),
                "low": D("2499"),
                "close": D("2501"),
                "volume": D("99"),
                "bid_close": D("2501"),
            }
        ),
    )
    assert semantic(replay(inputs(values), stop_at=cutoff)) == semantic(replay(inputs(mutated), stop_at=cutoff))
    removed = dict(values)
    removed[Timeframe.M5] = values[Timeframe.M5][:-1]
    governed_manifest = manifest(values=values)
    full = replay(make_replay_inputs(manifest=governed_manifest, candles=values), stop_at=cutoff)
    without_future = replay(make_replay_inputs(manifest=governed_manifest, candles=removed), stop_at=cutoff)
    assert semantic(full) == semantic(without_future)
    assert full.replay_fingerprint == without_future.replay_fingerprint


@pytest.mark.parametrize("timeframe", [Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1])
def test_future_higher_timeframe_mutation_does_not_change_prefix_analysis_or_candidate(timeframe):
    values = candles()
    cutoff = dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC)
    mutated = dict(values)
    current_open = bucket(cutoff, timeframe)
    existing = values[timeframe]
    future = next((item for item in existing if item.open_time == current_open), candle(timeframe, current_open))
    baseline = tuple(item for item in existing if item.open_time < current_open) + (future,)
    values = {**values, timeframe: baseline}
    mutated[timeframe] = baseline[:-1] + (
        future.model_copy(update={"high": D("2600"), "close": D("2500"), "bid_close": D("2500")}),
    )
    left = replay(inputs(values), stop_at=cutoff)
    right = replay(inputs(mutated), stop_at=cutoff)
    assert semantic(left) == semantic(right)
    left_frame = left.events[-1].context.frame(timeframe)
    right_frame = right.events[-1].context.frame(timeframe)
    assert left_frame is not None and right_frame is not None
    assert left_frame.analysis_json == right_frame.analysis_json
    assert left.events[-1].candidate == right.events[-1].candidate


def test_final_forming_higher_timeframe_is_accepted_but_never_visible():
    values = candles()
    forming = values[Timeframe.H1][-1].model_copy(update={"is_closed": False})
    changed = dict(values)
    changed[Timeframe.H1] = values[Timeframe.H1][:-1] + (forming,)
    result = replay(inputs(changed), stop_at=dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC))
    frame = event(result, dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC)).context.frame(Timeframe.H1)
    assert frame is not None and frame.bars == 2


def test_future_news_revision_is_invisible_before_available_at_and_visible_after():
    first = news_revision(version=1, available_at=dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC), actual="180")
    future = news_revision(version=2, available_at=dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC), actual="220")
    altered = future.model_copy(update={"actual": D("90"), "previous": D("120"), "revised_previous": D("121")})
    values = candles()
    common = dict(
        manifest=manifest(strategy_id="STRAT05", profile_id="news", values=values),
        candles=values,
        tick_size=D("0.01"),
        news_source="fixture_news",
        news_mode="FIXTURE",
        calendar_available=True,
    )
    before = dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC)
    original = replay(make_replay_inputs(news_events=(first, future), **common), stop_at=before)
    changed = replay(make_replay_inputs(news_events=(first, altered), **common), stop_at=before)
    assert semantic(original) == semantic(changed)
    after_original = replay(make_replay_inputs(news_events=(first, future), **common), stop_at=END)
    after_changed = replay(make_replay_inputs(news_events=(first, altered), **common), stop_at=END)
    assert semantic(after_original) != semantic(after_changed)


def test_delayed_quote_and_future_quote_mutation_do_not_change_earlier_output():
    values = candles()
    delayed = tuple(
        ObservedQuote(
            timestamp=dt.datetime(2025, 1, 6, 10, 54, second=second, tzinfo=UTC),
            observed_at=dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC),
            bid=D("2000"),
            ask=D("2000.2") + D(second) / 100,
            source="simulated",
        )
        for second in (10, 30, 50)
    )
    changed = delayed[:-1] + (delayed[-1].model_copy(update={"ask": D("2004")}),)
    cutoff = dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC)
    common = dict(
        manifest=manifest(strategy_id="STRAT05", profile_id="news", values=values),
        candles=values,
        tick_size=D("0.01"),
        news_source="fixture_news",
        news_mode="FIXTURE",
        calendar_available=True,
    )
    assert semantic(replay(make_replay_inputs(quotes=delayed, **common), stop_at=cutoff)) == semantic(
        replay(make_replay_inputs(quotes=changed, **common), stop_at=cutoff)
    )
    assert semantic(replay(make_replay_inputs(quotes=delayed, **common), stop_at=END)) != semantic(
        replay(make_replay_inputs(quotes=changed, **common), stop_at=END)
    )


def test_selected_profile_strategy_is_authoritative_and_invalid_pair_rejects():
    result = replay(inputs(), stop_at=START)
    assert {(item.profile_id, item.strategy_id) for item in result.events} == {("research", "STRAT01")}
    values = candles()
    invalid_manifest = manifest(strategy_id="STRAT02", profile_id="smc", values=values)
    with pytest.raises(ReplayError) as error:
        make_replay_inputs(manifest=invalid_manifest, candles=values)
    assert error.value.code is ReplayFailureCode.STRATEGY_CONFIG_INVALID


def test_second_non_news_profile_strategy_pair_uses_existing_engine():
    values = candles()
    governed = manifest(strategy_id="STRAT02", profile_id="trend", values=values)
    result = replay(make_replay_inputs(manifest=governed, candles=values), stop_at=START)
    assert {(item.profile_id, item.strategy_id) for item in result.events} == {("trend", "STRAT02")}
    assert all(item.candidate.strategy_version == "strategy-1.2.1" for item in result.events)


def test_strategy_version_must_match_manifest():
    from app.services.strategy.domain import StrategyConfig

    values = candles()
    with pytest.raises(ReplayError) as version:
        make_replay_inputs(
            manifest=manifest(values=values),
            candles=values,
            strategy_config=StrategyConfig(version="strategy-9.9.9"),
        )
    assert version.value.code is ReplayFailureCode.STRATEGY_CONFIG_INVALID


def test_repeat_determinism_event_order_and_no_outcome_fields():
    first = replay(inputs(), stop_at=END)
    second = replay(inputs(), stop_at=END)
    assert first == second
    assert first.replay_fingerprint == second.replay_fingerprint
    keys = [(e.as_of, e.profile_id, e.strategy_id, e.candidate_id) for e in first.events]
    assert keys == sorted(keys) and len(keys) == len(set(keys))
    forbidden = {"entry_reached", "filled", "win", "loss", "tp_hit", "sl_hit"}
    assert all(forbidden.isdisjoint(type(item).model_fields) for item in first.events)
    assert all(item.trade_plan is None or item.trade_plan.status == "SUGGESTION_ONLY" for item in first.events)


def test_replay_event_can_preserve_existing_suggestion_only_tradeplan():
    from app.services.strategy.domain import KeyLevel
    from app.services.strategy.engine import structural_plan

    original = replay(inputs(), stop_at=START).events[0]
    levels = tuple(
        KeyLevel(
            id=f"target-{index}",
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            kind="EXTERNAL_HIGH",
            price=price,
            origin=START - dt.timedelta(hours=2),
            confirmed_at=START - dt.timedelta(hours=1),
            valid_from=START - dt.timedelta(hours=1),
            status="CONFIRMED",
            source_ids=(f"swing-{index}",),
            input_id="input",
        )
        for index, price in enumerate((D("2020"), D("2030"), D("2040")))
    )
    projected = original.context.model_copy(update={"key_levels": levels})
    plan = structural_plan(
        context=projected,
        candidate_id=original.candidate.id,
        direction="LONG",
        entry_lower=D("2000"),
        entry_upper=D("2001"),
        entry_id="entry-zone",
        stop_anchor=D("1995"),
        stop_id="stop-swing",
        atr=D("2"),
        score=60,
        evidence=(),
        expires_at=START + dt.timedelta(minutes=30),
        config=inputs().strategy_config,
    )
    assert plan is not None
    candidate = original.candidate.model_copy(
        update={"direction": "LONG", "status": "READY", "confirmed_at": START, "plan": plan}
    )
    item = ReplayStrategyEvent(
        as_of=START,
        profile_id="research",
        strategy_id="STRAT01",
        context_id=candidate.context_id,
        candidate_id=candidate.id,
        candidate_status=candidate.status,
        context=projected,
        candidate=candidate,
        trade_plan=plan,
        event_fingerprint="a" * 64,
    )
    assert item.trade_plan.status == "SUGGESTION_ONLY"


def test_replay_version_is_server_owned_and_current():
    item = manifest()
    assert REPLAY_ENGINE_VERSION == "replay-engine-1.0.0"
    assert item.provenance.replay_engine_version == REPLAY_ENGINE_VERSION
    with pytest.raises(ValidationError):
        BacktestProvenance(**{**item.provenance.model_dump(), "replay_engine_version": "caller-version"})


def test_input_order_duplicates_identity_and_source_fail_closed():
    values = candles()
    for replacement, expected in (
        (values[Timeframe.M5][::-1], ReplayFailureCode.NON_MONOTONIC),
        (values[Timeframe.M5] + (values[Timeframe.M5][-1],), ReplayFailureCode.NON_MONOTONIC),
        (
            values[Timeframe.M5][:-1]
            + (values[Timeframe.M5][-1].model_copy(update={"symbol": "EURUSD"}),),
            ReplayFailureCode.INPUT_INVALID,
        ),
    ):
        changed = dict(values)
        changed[Timeframe.M5] = replacement
        with pytest.raises(ReplayError) as error:
            make_replay_inputs(manifest=manifest(values=values), candles=changed)
        assert error.value.code is expected


class Oversized(Sequence[Candle]):
    def __init__(self, size: int):
        self.size = size

    def __len__(self):
        return self.size

    def __getitem__(self, index):
        raise AssertionError("resource rejection must happen before materialization")


def test_primary_and_total_input_bounds_reject_before_materialization():
    values = candles()
    too_many_primary = dict(values)
    too_many_primary[Timeframe.M5] = Oversized(250_001)
    with pytest.raises(ReplayError) as primary:
        make_replay_inputs(manifest=manifest(values=values), candles=too_many_primary)
    assert primary.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED
    too_many_total = {timeframe: Oversized(120_000) for timeframe in FRAMES}
    with pytest.raises(ReplayError) as total:
        make_replay_inputs(manifest=manifest(values=values), candles=too_many_total)
    assert total.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED


def test_candidate_output_bound_fails_without_complete_partial_result(monkeypatch):
    import app.services.backtesting.replay as replay_module

    monkeypatch.setattr(replay_module, "MAX_CANDIDATES_PER_RUN", 0)
    with pytest.raises(ReplayError) as error:
        replay(inputs(), stop_at=START)
    assert error.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED
