"""D2A causal replay, projection, determinism, and bounded-failure acceptance."""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.analysis.domain import AnalysisConfig
from app.services.analysis.engine import analyze
from app.services.backtesting.domain import (
    REPLAY_ENGINE_VERSION,
    BacktestProvenance,
    BacktestRunConfig,
    BacktestRunManifest,
    CostAssumptions,
    CoverageGap,
    CoverageGapCode,
    CoverageStatus,
    DataCoverage,
    GapExpectation,
    NewsVintageCoverage,
    TimeframeCoverage,
)
from app.services.backtesting.fingerprint import (
    config_fingerprint,
    coverage_fingerprint,
    historical_data_fingerprint,
    replay_configuration_fingerprint,
    replay_input_fingerprint,
    resource_policy_fingerprint,
    run_input_fingerprint,
)
from app.services.backtesting.policy import BacktestResourcePolicy
from app.services.backtesting.replay import _visible_prefix, make_replay_inputs, replay
from app.services.backtesting.replay_domain import (
    ReplayClock,
    ReplayError,
    ReplayFailureCode,
    ReplayInputs,
    ReplayStrategyEvent,
)
from app.services.market_data.domain import SECONDS, Candle, Timeframe, bucket
from app.services.news.domain import EconomicEvent, NewsConfig, ObservedQuote
from app.services.news.engine import build_context as build_news_context
from app.services.strategy.context import build_context as build_strategy_context
from app.services.strategy.domain import StrategyConfig
from app.services.strategy.engine import REGISTRY, profiles
from app.services.strategy.engine import evaluate as evaluate_strategies

D = Decimal
UTC = dt.UTC
WARMUP = dt.datetime(2025, 1, 6, 8, tzinfo=UTC)
START = dt.datetime(2025, 1, 6, 10, 40, tzinfo=UTC)
END = dt.datetime(2025, 1, 6, 12, tzinfo=UTC)
FRAMES = tuple(Timeframe)


def candle(timeframe: Timeframe, opened: dt.datetime, price: str = "2000", *, closed: bool = True) -> Candle:
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
        is_closed=closed,
    )


def candles() -> dict[Timeframe, tuple[Candle, ...]]:
    result: dict[Timeframe, tuple[Candle, ...]] = {}
    for timeframe in FRAMES:
        step = dt.timedelta(seconds=SECONDS[timeframe])
        anchor = bucket(START, timeframe)
        current = bucket(END - dt.timedelta(microseconds=1), timeframe)
        first = anchor - step * 2
        count = int((current - first) / step) + 1
        result[timeframe] = tuple(
            candle(timeframe, first + step * index, str(2000 + index % 7), closed=first + step * (index + 1) <= END)
            for index in range(count)
        )
    result[Timeframe.M1] = tuple(
        candle(Timeframe.M1, WARMUP + dt.timedelta(minutes=index), str(2000 + index % 7)) for index in range(240)
    )
    result[Timeframe.M5] = tuple(
        candle(Timeframe.M5, dt.datetime(2025, 1, 6, 10, 30, tzinfo=UTC) + dt.timedelta(minutes=5 * index))
        for index in range(18)
    )
    result[Timeframe.H1] = (
        candle(Timeframe.H1, dt.datetime(2025, 1, 6, 8, tzinfo=UTC), "1998"),
        candle(Timeframe.H1, dt.datetime(2025, 1, 6, 9, tzinfo=UTC), "1999"),
        candle(Timeframe.H1, dt.datetime(2025, 1, 6, 10, tzinfo=UTC), "2000"),
        candle(Timeframe.H1, dt.datetime(2025, 1, 6, 11, tzinfo=UTC), "2001"),
    )
    return result


def manifest(
    *,
    strategy_id="STRAT01",
    profile_id="research",
    values=None,
    news_events=(),
    quotes=(),
    news_source="historical_unavailable",
    news_mode="UNAVAILABLE",
    calendar_available=False,
    gaps=(),
) -> BacktestRunManifest:
    values = values if values is not None else candles()
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
            available_start=values[timeframe][0].open_time,
            available_end=values[timeframe][-1].open_time + dt.timedelta(seconds=SECONDS[timeframe]),
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
        gaps=gaps,
        news_vintages=news,
        data_fingerprint=historical_data_fingerprint(
            symbol="XAUUSD",
            source="simulated",
            candles=values,
            news_events=tuple(news_events),
            quotes=tuple(quotes),
            news_source=news_source,
            news_mode=news_mode,
            calendar_available=calendar_available,
        ),
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
    values = values if values is not None else candles()
    snapshot_keys = ("news_events", "quotes", "news_source", "news_mode", "calendar_available")
    snapshot = {key: changes[key] for key in snapshot_keys if key in changes}
    governed = changes.pop("manifest", None) or manifest(values=values, **snapshot)
    args = {"manifest": governed, "candles": values, "tick_size": D("0.01")}
    args.update(changes)
    return make_replay_inputs(**args)


def replace_coverage(base: BacktestRunManifest, **changes) -> BacktestRunManifest:
    coverage = DataCoverage(**{**base.coverage.model_dump(mode="python"), **changes})
    provenance = BacktestProvenance(
        **{
            **base.provenance.model_dump(mode="python"),
            "data_coverage_fingerprint": coverage_fingerprint(coverage),
            "data_fingerprint": coverage.data_fingerprint,
        }
    )
    return BacktestRunManifest(
        config=base.config,
        coverage=coverage,
        provenance=provenance,
        resource_policy_fingerprint=base.resource_policy_fingerprint,
    )


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
        assert all(item.open_time + dt.timedelta(seconds=SECONDS[timeframe]) <= frame.as_of for item in frame.candles)


def test_full_input_cutoff_equals_causal_prefix_for_multiple_cutoffs():
    values = candles()
    for cutoff in (
        dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC),
        dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC),
        dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC),
    ):
        mutated = dict(values)
        future = values[Timeframe.M5][-1]
        mutated[Timeframe.M5] = values[Timeframe.M5][:-1] + (
            future.model_copy(update={"high": D("2600"), "close": D("2500"), "bid_close": D("2500")}),
        )
        full = replay(inputs(values), stop_at=cutoff)
        causal = replay(inputs(mutated), stop_at=cutoff)
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
    full = replay(inputs(values), stop_at=cutoff)
    changed = replay(inputs(mutated), stop_at=cutoff)
    assert full.replay_fingerprint == changed.replay_fingerprint


@pytest.mark.parametrize("timeframe", [Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1])
def test_future_higher_timeframe_mutation_does_not_change_prefix_analysis_or_candidate(timeframe):
    values = candles()
    cutoff = dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC)
    mutated = dict(values)
    current_open = bucket(cutoff, timeframe)
    existing = values[timeframe]
    future = next(item for item in existing if item.open_time == current_open)
    mutated[timeframe] = tuple(
        item
        if item.open_time != current_open
        else future.model_copy(update={"high": D("2600"), "close": D("2500"), "bid_close": D("2500")})
        for item in existing
    )
    left = replay(inputs(values), stop_at=cutoff)
    right = replay(inputs(mutated), stop_at=cutoff)
    assert semantic(left) == semantic(right)
    assert left.replay_fingerprint == right.replay_fingerprint
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
    assert frame is not None and frame.bars == 3


def test_future_news_revision_is_invisible_before_available_at_and_visible_after():
    first = news_revision(version=1, available_at=dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC), actual="180")
    future = news_revision(version=2, available_at=dt.datetime(2025, 1, 6, 11, 0, tzinfo=UTC), actual="220")
    altered = future.model_copy(update={"actual": D("90"), "previous": D("120"), "revised_previous": D("121")})
    values = candles()
    common = dict(
        candles=values, tick_size=D("0.01"), news_source="fixture_news", news_mode="FIXTURE", calendar_available=True
    )
    before = dt.datetime(2025, 1, 6, 10, 55, tzinfo=UTC)
    original_events = (first, future)
    changed_events = (first, altered)
    original = replay(
        make_replay_inputs(
            manifest=manifest(
                strategy_id="STRAT05",
                profile_id="news",
                values=values,
                news_events=original_events,
                news_source="fixture_news",
                news_mode="FIXTURE",
                calendar_available=True,
            ),
            news_events=original_events,
            **common,
        ),
        stop_at=before,
    )
    changed = replay(
        make_replay_inputs(
            manifest=manifest(
                strategy_id="STRAT05",
                profile_id="news",
                values=values,
                news_events=changed_events,
                news_source="fixture_news",
                news_mode="FIXTURE",
                calendar_available=True,
            ),
            news_events=changed_events,
            **common,
        ),
        stop_at=before,
    )
    assert semantic(original) == semantic(changed)
    assert original.replay_fingerprint == changed.replay_fingerprint
    after_original = replay(
        make_replay_inputs(
            manifest=manifest(
                strategy_id="STRAT05",
                profile_id="news",
                values=values,
                news_events=original_events,
                news_source="fixture_news",
                news_mode="FIXTURE",
                calendar_available=True,
            ),
            news_events=original_events,
            **common,
        ),
        stop_at=END,
    )
    after_changed = replay(
        make_replay_inputs(
            manifest=manifest(
                strategy_id="STRAT05",
                profile_id="news",
                values=values,
                news_events=changed_events,
                news_source="fixture_news",
                news_mode="FIXTURE",
                calendar_available=True,
            ),
            news_events=changed_events,
            **common,
        ),
        stop_at=END,
    )
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
        candles=values, tick_size=D("0.01"), news_source="fixture_news", news_mode="FIXTURE", calendar_available=True
    )

    def quote_inputs(items):
        return make_replay_inputs(
            manifest=manifest(
                strategy_id="STRAT05",
                profile_id="news",
                values=values,
                quotes=items,
                news_source="fixture_news",
                news_mode="FIXTURE",
                calendar_available=True,
            ),
            quotes=items,
            **common,
        )

    delayed_before = replay(quote_inputs(delayed), stop_at=cutoff)
    changed_before = replay(quote_inputs(changed), stop_at=cutoff)
    assert semantic(delayed_before) == semantic(changed_before)
    assert delayed_before.replay_fingerprint == changed_before.replay_fingerprint
    assert semantic(replay(quote_inputs(delayed), stop_at=END)) != semantic(replay(quote_inputs(changed), stop_at=END))


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
            values[Timeframe.M5][:-1] + (values[Timeframe.M5][-1].model_copy(update={"symbol": "EURUSD"}),),
            ReplayFailureCode.INPUT_INVALID,
        ),
    ):
        changed = dict(values)
        changed[Timeframe.M5] = replacement
        with pytest.raises(ReplayError) as error:
            make_replay_inputs(manifest=manifest(values=values), candles=changed)
        assert error.value.code is expected


class DishonestSequence(Sequence[Candle]):
    def __init__(self, values, reported: int):
        self.values = values
        self.reported = reported

    def __len__(self):
        return self.reported

    def __getitem__(self, index):
        return self.values[index]


def test_primary_and_total_input_bounds_use_bounded_materialization(monkeypatch):
    import app.services.backtesting.replay as replay_module

    values = candles()
    primary = values[Timeframe.M5]
    for reported in (1, len(primary) + 100):
        changed = {**values, Timeframe.M5: DishonestSequence(primary, reported)}
        assert len(make_replay_inputs(manifest=manifest(values=values), candles=changed).candles[Timeframe.M5]) == len(
            primary
        )
    listed = {**values, Timeframe.M5: list(primary)}
    assert make_replay_inputs(manifest=manifest(values=values), candles=listed)
    monkeypatch.setattr(replay_module, "MAX_PRIMARY_REPLAY_EVENTS", len(primary))
    assert make_replay_inputs(manifest=manifest(values=values), candles=values)
    extra = candle(Timeframe.M5, END)
    too_many = {**values, Timeframe.M5: DishonestSequence(primary + (extra,), 1)}
    with pytest.raises(ReplayError) as error:
        make_replay_inputs(manifest=manifest(values=values), candles=too_many)
    assert error.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED

    monkeypatch.setattr(replay_module, "MAX_PRIMARY_REPLAY_EVENTS", 250_000)
    total = sum(map(len, values.values()))
    monkeypatch.setattr(replay_module, "MAX_TOTAL_CANDLE_INPUTS", total)
    assert make_replay_inputs(manifest=manifest(values=values), candles=values)
    monkeypatch.setattr(replay_module, "MAX_TOTAL_CANDLE_INPUTS", total - 1)
    with pytest.raises(ReplayError) as global_limit:
        make_replay_inputs(manifest=manifest(values=values), candles=values)
    assert global_limit.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED


def test_v_d2a_06_forming_m1_is_never_causally_visible():
    values = candles()
    final = values[Timeframe.M1][-1]
    forming = final.model_copy(
        update={
            "open": D("9000"),
            "high": D("9999"),
            "low": D("1"),
            "close": D("8000"),
            "volume": D("999"),
            "bid_close": D("8000"),
            "is_closed": False,
        }
    )
    neutral = final.model_copy(update={"is_closed": False})
    extreme_values = {**values, Timeframe.M1: values[Timeframe.M1][:-1] + (forming,)}
    neutral_values = {**values, Timeframe.M1: values[Timeframe.M1][:-1] + (neutral,)}

    def news_inputs(frame_values):
        return make_replay_inputs(
            manifest=manifest(
                strategy_id="STRAT05",
                profile_id="news",
                values=frame_values,
                news_source="fixture_news",
                news_mode="FIXTURE",
                calendar_available=True,
            ),
            candles=frame_values,
            news_source="fixture_news",
            news_mode="FIXTURE",
            calendar_available=True,
        )

    assert _visible_prefix(extreme_values[Timeframe.M1], Timeframe.M1, END, WARMUP) == _visible_prefix(
        values[Timeframe.M1][:-1], Timeframe.M1, END, WARMUP
    )
    extreme = replay(news_inputs(extreme_values), stop_at=END)
    baseline = replay(news_inputs(neutral_values), stop_at=END)
    assert semantic(extreme) == semantic(baseline)
    assert extreme.replay_fingerprint == baseline.replay_fingerprint
    extreme_event = event(extreme, END)
    baseline_event = event(baseline, END)
    assert extreme_event.context.frame(Timeframe.M1) == baseline_event.context.frame(Timeframe.M1)
    assert extreme_event.context.news_fingerprint == baseline_event.context.news_fingerprint
    assert extreme_event.candidate == baseline_event.candidate
    assert extreme_event.trade_plan == baseline_event.trade_plan
    assert extreme_event.event_fingerprint == baseline_event.event_fingerprint

    closed_values = {
        **values,
        Timeframe.M1: values[Timeframe.M1][:-1] + (forming.model_copy(update={"is_closed": True}),),
    }
    closed = replay(news_inputs(closed_values), stop_at=END)
    frame = event(closed, END).context.frame(Timeframe.M1)
    assert frame is not None and any(item.open_time == final.open_time for item in frame.candles)


def test_v_d2a_10_fixed_warmup_origin_and_boundary_inclusion():
    values = candles()
    boundary = candle(Timeframe.M1, WARMUP - dt.timedelta(minutes=1), "2100")
    governed = {**values, Timeframe.M1: (boundary,) + values[Timeframe.M1]}
    prior = tuple(candle(Timeframe.M1, WARMUP - dt.timedelta(minutes=201 - index), "9000") for index in range(200))
    extended = {**values, Timeframe.M1: prior + governed[Timeframe.M1]}
    left = replay(inputs(governed), stop_at=START)
    right = replay(inputs(extended), stop_at=START)
    assert semantic(left) == semantic(right)
    assert left.replay_fingerprint == right.replay_fingerprint
    frame = left.events[-1].context.frame(Timeframe.M1)
    assert frame is not None
    assert boundary.open_time in {item.open_time for item in frame.candles}
    assert all(item.open_time != prior[-1].open_time for item in frame.candles)


def test_v_d2a_12_13_actual_counts_reconcile_with_manifest():
    values = candles()
    base = manifest(values=values)
    primary_claim = replace_coverage(
        base,
        available_primary_events=base.coverage.available_primary_events + 1,
        requested_primary_events=base.coverage.requested_primary_events + 1,
        total_candle_inputs=base.coverage.total_candle_inputs + 1,
        timeframe_coverage=tuple(
            item.model_copy(
                update={
                    "available_events": item.available_events + 1,
                    "requested_events": item.requested_events + 1,
                }
            )
            if item.timeframe is Timeframe.M5
            else item
            for item in base.coverage.timeframe_coverage
        ),
    )
    with pytest.raises(ReplayError) as primary:
        make_replay_inputs(manifest=primary_claim, candles=values)
    assert primary.value.code is ReplayFailureCode.INPUT_INVALID

    w1_claim = replace_coverage(
        base,
        total_candle_inputs=base.coverage.total_candle_inputs + 1,
        timeframe_coverage=tuple(
            item.model_copy(
                update={
                    "available_events": item.available_events + 1,
                    "requested_events": item.requested_events + 1,
                }
            )
            if item.timeframe is Timeframe.W1
            else item
            for item in base.coverage.timeframe_coverage
        ),
    )
    with pytest.raises(ReplayError) as w1:
        make_replay_inputs(manifest=w1_claim, candles=values)
    assert w1.value.code is ReplayFailureCode.INPUT_INVALID

    frames = list(base.coverage.timeframe_coverage)
    m1_index = next(index for index, item in enumerate(frames) if item.timeframe is Timeframe.M1)
    h1_index = next(index for index, item in enumerate(frames) if item.timeframe is Timeframe.H1)
    frames[m1_index] = frames[m1_index].model_copy(
        update={
            "available_events": frames[m1_index].available_events + 1,
            "requested_events": frames[m1_index].requested_events + 1,
        }
    )
    frames[h1_index] = frames[h1_index].model_copy(
        update={
            "available_events": frames[h1_index].available_events - 1,
            "requested_events": frames[h1_index].requested_events - 1,
        }
    )
    per_frame_claim = replace_coverage(base, timeframe_coverage=tuple(frames))
    with pytest.raises(ReplayError) as per_frame:
        make_replay_inputs(manifest=per_frame_claim, candles=values)
    assert per_frame.value.code is ReplayFailureCode.INPUT_INVALID


def test_v_d2a_12_13_claimed_range_must_be_supported_and_forming_htf_is_accepted():
    values = candles()
    assert make_replay_inputs(manifest=manifest(values=values), candles=values)
    assert not values[Timeframe.W1][-1].is_closed
    base = manifest(values=values)
    frames = tuple(
        item.model_copy(update={"available_start": item.available_start - dt.timedelta(minutes=1)})
        if item.timeframe is Timeframe.M5
        else item
        for item in base.coverage.timeframe_coverage
    )
    unsupported = replace_coverage(base, timeframe_coverage=frames)
    with pytest.raises(ReplayError) as error:
        make_replay_inputs(manifest=unsupported, candles=values)
    assert error.value.code is ReplayFailureCode.INPUT_INVALID


def test_v_d2a_14_historical_snapshot_fingerprint_is_canonical_and_content_bound():
    values = candles()
    base = historical_data_fingerprint(symbol="XAUUSD", source="simulated", candles=values)
    reversed_mapping = dict(reversed(tuple(values.items())))
    assert historical_data_fingerprint(symbol="XAUUSD", source="simulated", candles=reversed_mapping) == base
    assert historical_data_fingerprint(symbol="XAUUSD", source="simulated", candles=values) == base

    changed_candles = dict(values)
    changed_candles[Timeframe.M1] = values[Timeframe.M1][:-1] + (
        values[Timeframe.M1][-1].model_copy(update={"volume": D("11")}),
    )
    assert historical_data_fingerprint(symbol="XAUUSD", source="simulated", candles=changed_candles) != base
    with pytest.raises(ReplayError) as mismatch:
        make_replay_inputs(manifest=manifest(values=values), candles=changed_candles)
    assert mismatch.value.code is ReplayFailureCode.INPUT_INVALID

    first = news_revision(version=1, available_at=START + dt.timedelta(minutes=5), actual="180")
    second = news_revision(version=2, available_at=START + dt.timedelta(minutes=6), actual="190")
    news_args = dict(
        symbol="XAUUSD",
        source="simulated",
        candles=values,
        news_source="fixture_news",
        news_mode="FIXTURE",
        calendar_available=True,
    )
    news_hash = historical_data_fingerprint(news_events=(first, second), **news_args)
    assert historical_data_fingerprint(news_events=(second, first), **news_args) == news_hash
    assert (
        historical_data_fingerprint(news_events=(first, second.model_copy(update={"actual": D("191")})), **news_args)
        != news_hash
    )

    quote = ObservedQuote(timestamp=START, observed_at=START, bid=D("2000"), ask=D("2000.2"), source="simulated")
    quote_hash = historical_data_fingerprint(symbol="XAUUSD", source="simulated", candles=values, quotes=(quote,))
    assert (
        historical_data_fingerprint(
            symbol="XAUUSD",
            source="simulated",
            candles=values,
            quotes=(quote.model_copy(update={"ask": D("2000.3")}),),
        )
        != quote_hash
    )


def test_v_d2a_14_future_snapshot_mutation_does_not_change_causal_output_fingerprint():
    values = candles()
    cutoff = dt.datetime(2025, 1, 6, 10, 50, tzinfo=UTC)
    changed = dict(values)
    changed[Timeframe.M5] = values[Timeframe.M5][:-1] + (
        values[Timeframe.M5][-1].model_copy(update={"volume": D("999")}),
    )
    assert manifest(values=values).coverage.data_fingerprint != manifest(values=changed).coverage.data_fingerprint
    left = replay(inputs(values), stop_at=cutoff)
    right = replay(inputs(changed), stop_at=cutoff)
    assert semantic(left) == semantic(right)
    assert left.replay_fingerprint == right.replay_fingerprint


def test_v_d2a_29_selected_strategy_only_and_canonical_candidate_parity(monkeypatch):
    baseline_inputs = inputs()
    baseline = replay(baseline_inputs, stop_at=START)
    replay_event = baseline.events[-1]
    visible = {
        timeframe: list(_visible_prefix(frame, timeframe, START, WARMUP))
        for timeframe, frame in baseline_inputs.candles.items()
    }
    structure = analyze(
        visible[Timeframe.M1],
        "XAUUSD",
        Timeframe.M1,
        "simulated",
        requested=300,
        config=baseline_inputs.analysis_config,
    )
    news = build_news_context(
        [],
        START,
        source=baseline_inputs.news_source,
        mode=baseline_inputs.news_mode,
        config=baseline_inputs.news_config,
        candles=visible[Timeframe.M1],
        quotes=[],
        structure=structure,
        calendar_available=False,
        market_source="simulated",
    )
    full_context = build_strategy_context(
        candles=visible,
        symbol="XAUUSD",
        source="simulated",
        at=START,
        news=news,
        tick_size=baseline_inputs.tick_size,
        config=baseline_inputs.strategy_config,
        analysis_config=baseline_inputs.analysis_config,
        replay=True,
        quotes=(),
    )
    selected = next(
        item for item in profiles(baseline_inputs.strategy_config, full_context.config_id) if item.id == "research"
    )
    normal = evaluate_strategies(
        full_context,
        baseline_inputs.strategy_config,
        traders=(selected,),
    )
    assert replay_event.candidate == next(item for item in normal.candidates if item.strategy_id == "STRAT01")

    def fail(*_args, **_kwargs):
        raise ValueError("patched strategy failure")

    for strategy_id in ("STRAT02", "STRAT03", "STRAT04", "STRAT05", "STRAT06"):
        monkeypatch.setattr(REGISTRY[strategy_id], "evaluate", fail)
    assert replay(inputs(), stop_at=START).events[-1].candidate == replay_event.candidate
    monkeypatch.setattr(REGISTRY["STRAT01"], "evaluate", fail)
    with pytest.raises(ReplayError) as selected_failure:
        replay(inputs(), stop_at=START)
    assert selected_failure.value.code is ReplayFailureCode.STRATEGY_CONFIG_INVALID


def test_v_d2a_29_news_strategy_does_not_evaluate_sibling(monkeypatch):
    values = candles()
    governed = manifest(
        strategy_id="STRAT05",
        profile_id="news",
        values=values,
        news_source="fixture_news",
        news_mode="FIXTURE",
        calendar_available=True,
    )
    replay_inputs = make_replay_inputs(
        manifest=governed,
        candles=values,
        news_source="fixture_news",
        news_mode="FIXTURE",
        calendar_available=True,
    )

    def fail(*_args, **_kwargs):
        raise ValueError("STRAT06 must not run")

    monkeypatch.setattr(REGISTRY["STRAT06"], "evaluate", fail)
    assert {item.strategy_id for item in replay(replay_inputs, stop_at=START).events} == {"STRAT05"}


def test_v_d2a_36_news_and_quote_sequences_are_bounded_by_iteration(monkeypatch):
    import app.services.backtesting.replay as replay_module

    values = candles()
    event_one = news_revision(version=1, available_at=START + dt.timedelta(minutes=5), actual="180")
    event_two = news_revision(version=2, available_at=START + dt.timedelta(minutes=6), actual="190")
    monkeypatch.setattr(replay_module, "_MAX_NEWS_EVENTS", 1)
    news_manifest = manifest(
        values=values,
        news_events=(event_one,),
        news_source="fixture_news",
        news_mode="FIXTURE",
        calendar_available=True,
    )
    assert make_replay_inputs(
        manifest=news_manifest,
        candles=values,
        news_events=DishonestSequence((event_one,), 99),
        news_source="fixture_news",
        news_mode="FIXTURE",
        calendar_available=True,
    )
    with pytest.raises(ReplayError) as news_limit:
        make_replay_inputs(
            manifest=news_manifest,
            candles=values,
            news_events=DishonestSequence((event_one, event_two), 1),
            news_source="fixture_news",
            news_mode="FIXTURE",
            calendar_available=True,
        )
    assert news_limit.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED

    quote_one = ObservedQuote(timestamp=START, observed_at=START, bid=D("2000"), ask=D("2000.2"), source="simulated")
    quote_two = quote_one.model_copy(
        update={"timestamp": START + dt.timedelta(seconds=1), "observed_at": START + dt.timedelta(seconds=1)}
    )
    monkeypatch.setattr(replay_module, "_MAX_QUOTES", 1)
    quote_manifest = manifest(values=values, quotes=(quote_one,))
    assert make_replay_inputs(
        manifest=quote_manifest,
        candles=values,
        quotes=DishonestSequence((quote_one,), 99),
    )
    with pytest.raises(ReplayError) as quote_limit:
        make_replay_inputs(
            manifest=quote_manifest,
            candles=values,
            quotes=DishonestSequence((quote_one, quote_two), 1),
        )
    assert quote_limit.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED


def test_candidate_output_bound_fails_without_complete_partial_result(monkeypatch):
    import app.services.backtesting.replay as replay_module

    monkeypatch.setattr(replay_module, "MAX_CANDIDATES_PER_RUN", 0)
    with pytest.raises(ReplayError) as error:
        replay(inputs(), stop_at=START)
    assert error.value.code is ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED


def scheduled_gap(timeframe: Timeframe, start: dt.datetime, buckets: int = 1) -> CoverageGap:
    return CoverageGap(
        timeframe=timeframe,
        gap_start=start,
        gap_end=start + dt.timedelta(seconds=SECONDS[timeframe] * buckets),
        code=CoverageGapCode.SCHEDULED_MARKET_CLOSURE,
        expectation=GapExpectation.EXPECTED_SCHEDULED_CLOSURE,
    )


@pytest.mark.parametrize(
    ("timeframe", "missing_open"),
    [
        (Timeframe.M5, dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC)),
        (Timeframe.H1, dt.datetime(2025, 1, 6, 10, 0, tzinfo=UTC)),
    ],
)
def test_new_d2a_rv_001_undeclared_interior_gap_rejects(timeframe, missing_open):
    values = candles()
    changed = {**values, timeframe: tuple(c for c in values[timeframe] if c.open_time != missing_open)}
    with pytest.raises(ReplayError) as error:
        make_replay_inputs(manifest=manifest(values=changed), candles=changed)
    assert error.value.code is ReplayFailureCode.INPUT_INVALID


def test_new_d2a_rv_001_scheduled_gap_reconciles_exact_missing_buckets():
    values = candles()
    first_missing = dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC)
    missing = {first_missing, first_missing + dt.timedelta(minutes=5)}
    changed = {**values, Timeframe.M5: tuple(c for c in values[Timeframe.M5] if c.open_time not in missing)}
    gap = scheduled_gap(Timeframe.M5, first_missing, buckets=2)
    assert make_replay_inputs(manifest=manifest(values=changed, gaps=(gap,)), candles=changed)


@pytest.mark.parametrize("case", ["wrong_timeframe", "wrong_interval", "orphan"])
def test_new_d2a_rv_001_incorrect_scheduled_gap_evidence_rejects(case):
    values = candles()
    missing_open = dt.datetime(2025, 1, 6, 10, 45, tzinfo=UTC)
    changed = values
    if case != "orphan":
        changed = {
            **values,
            Timeframe.M5: tuple(c for c in values[Timeframe.M5] if c.open_time != missing_open),
        }
    gap = (
        scheduled_gap(Timeframe.H1, dt.datetime(2025, 1, 6, 10, 0, tzinfo=UTC))
        if case == "wrong_timeframe"
        else scheduled_gap(Timeframe.M5, missing_open + dt.timedelta(minutes=5))
        if case == "wrong_interval"
        else scheduled_gap(Timeframe.M5, missing_open)
    )
    with pytest.raises(ReplayError) as error:
        make_replay_inputs(manifest=manifest(values=changed, gaps=(gap,)), candles=changed)
    assert error.value.code is ReplayFailureCode.INPUT_INVALID


def test_new_d2a_rv_001_gap_strictly_before_warmup_is_irrelevant():
    values = candles()
    early = candle(Timeframe.M1, WARMUP - dt.timedelta(minutes=5), "1999")
    changed = {**values, Timeframe.M1: (early,) + values[Timeframe.M1]}
    assert make_replay_inputs(manifest=manifest(values=changed), candles=changed)


def test_v_d2a_14_rv_01_replay_rejects_direct_and_post_factory_candle_tampering():
    values = candles()
    valid = inputs(values)
    changed = {
        **values,
        Timeframe.M5: values[Timeframe.M5][:2]
        + (values[Timeframe.M5][2].model_copy(update={"volume": D("999")}),)
        + values[Timeframe.M5][3:],
    }
    direct = ReplayInputs(**{**valid.model_dump(mode="python"), "candles": changed})
    with pytest.raises(ReplayError) as direct_error:
        replay(direct, stop_at=END)
    assert direct_error.value.code is ReplayFailureCode.INPUT_INVALID

    replaced = inputs(values)
    replaced.candles[Timeframe.M5] = changed[Timeframe.M5]
    with pytest.raises(ReplayError) as replaced_error:
        replay(replaced, stop_at=END)
    assert replaced_error.value.code is ReplayFailureCode.INPUT_INVALID

    mutated = inputs(values)
    mutated.candles[Timeframe.M5][2].volume = D("998")
    with pytest.raises(ReplayError) as mutated_error:
        replay(mutated, stop_at=END)
    assert mutated_error.value.code is ReplayFailureCode.INPUT_INVALID


def test_v_d2a_14_rv_01_replay_rejects_news_and_quote_tampering():
    values = candles()
    news = news_revision(version=1, available_at=START + dt.timedelta(minutes=5), actual="180")
    news_args = dict(news_source="fixture_news", news_mode="FIXTURE", calendar_available=True)
    valid_news = make_replay_inputs(
        manifest=manifest(values=values, news_events=(news,), **news_args),
        candles=values,
        news_events=(news,),
        **news_args,
    )
    changed_news = news.model_copy(update={"actual": D("999")})
    with pytest.raises(ReplayError) as news_error:
        replay(valid_news.model_copy(update={"news_events": (changed_news,)}), stop_at=END)
    assert news_error.value.code is ReplayFailureCode.INPUT_INVALID

    quote = ObservedQuote(timestamp=START, observed_at=START, bid=D("2000"), ask=D("2000.2"), source="simulated")
    valid_quote = make_replay_inputs(
        manifest=manifest(values=values, quotes=(quote,)), candles=values, quotes=(quote,)
    )
    changed_quote = quote.model_copy(update={"ask": D("2001")})
    with pytest.raises(ReplayError) as quote_error:
        replay(valid_quote.model_copy(update={"quotes": (changed_quote,)}), stop_at=END)
    assert quote_error.value.code is ReplayFailureCode.INPUT_INVALID


def test_v_d2a_14_rv_01_valid_refingerprinted_source_accepts_and_uses_private_snapshot(monkeypatch):
    import app.services.backtesting.replay as replay_module

    values = candles()
    changed = {
        **values,
        Timeframe.M5: values[Timeframe.M5][:2]
        + (values[Timeframe.M5][2].model_copy(update={"volume": D("999")}),)
        + values[Timeframe.M5][3:],
    }
    assert replay(inputs(changed), stop_at=END)

    caller_owned = inputs(values)
    expected = replay(inputs(values), stop_at=END)
    original_analyze = replay_module.analyze
    mutated = False

    def mutate_caller_after_preparation(*args, **kwargs):
        nonlocal mutated
        if not mutated:
            caller_owned.candles[Timeframe.M5][2].volume = D("777")
            mutated = True
        return original_analyze(*args, **kwargs)

    monkeypatch.setattr(replay_module, "analyze", mutate_caller_after_preparation)
    assert replay(caller_owned, stop_at=END) == expected


def test_v_d2a_14_rv_01_revalidates_nested_configuration_content():
    invalid_analysis = inputs()
    invalid_analysis.analysis_config.session_hours["ASIA"] = [20, 5]
    with pytest.raises(ReplayError) as analysis_error:
        replay(invalid_analysis, stop_at=START)
    assert analysis_error.value.code is ReplayFailureCode.INPUT_INVALID

    invalid_news = inputs()
    invalid_news.news_config.reaction_seconds[:] = [300, 60]
    with pytest.raises(ReplayError) as news_error:
        replay(invalid_news, stop_at=START)
    assert news_error.value.code is ReplayFailureCode.INPUT_INVALID


def test_new_d2a_rv_002_complete_replay_configuration_identity():
    values = candles()
    baseline = replay(inputs(values), stop_at=START)
    mutations = (
        ({"strategy_config": StrategyConfig(expiry_trigger_bars=13)}, True),
        ({"analysis_config": AnalysisConfig(internal_left=3)}, True),
        ({"news_config": NewsConfig(reaction_seconds=[60, 300])}, False),
        ({"tick_size": D("0.1")}, True),
    )
    for change, changes_output in mutations:
        changed = replay(inputs(values, **change), stop_at=START)
        assert changed.replay_input_fingerprint != baseline.replay_input_fingerprint
        if changes_output:
            assert changed.replay_fingerprint != baseline.replay_fingerprint
    assert replay(inputs(values), stop_at=START).replay_input_fingerprint == baseline.replay_input_fingerprint


def test_new_d2a_rv_002_configuration_identity_is_canonical():
    normal = AnalysisConfig()
    reverse_sessions = dict(reversed(tuple(normal.session_hours.items())))
    reordered = AnalysisConfig(**{**normal.model_dump(mode="python"), "session_hours": reverse_sessions})
    base = replay(inputs(analysis_config=normal, tick_size=D("0.01")), stop_at=START)
    equivalent = replay(inputs(analysis_config=reordered, tick_size=D("0.010")), stop_at=START)
    assert base.replay_input_fingerprint == equivalent.replay_input_fingerprint

    config_id = replay_configuration_fingerprint(
        strategy_config=StrategyConfig(),
        analysis_config=normal,
        news_config=NewsConfig(),
        tick_size=D("0.01"),
        replay_engine_version=REPLAY_ENGINE_VERSION,
    )
    equivalent_config_id = replay_configuration_fingerprint(
        strategy_config=StrategyConfig(),
        analysis_config=reordered,
        news_config=NewsConfig(),
        tick_size=D("0.010"),
        replay_engine_version=REPLAY_ENGINE_VERSION,
    )
    assert equivalent_config_id == config_id
    assert replay_input_fingerprint(manifest=manifest(), configuration_fingerprint=config_id) == (
        base.replay_input_fingerprint
    )


def test_new_d2a_rv_002_future_suffix_separates_input_and_causal_output_identity():
    values = candles()
    changed = {
        **values,
        Timeframe.M5: values[Timeframe.M5][:-1]
        + (values[Timeframe.M5][-1].model_copy(update={"volume": D("999")}),),
    }
    cutoff = dt.datetime(2025, 1, 6, 10, 50, tzinfo=UTC)
    left = replay(inputs(values), stop_at=cutoff)
    right = replay(inputs(changed), stop_at=cutoff)
    assert manifest(values=values).coverage.data_fingerprint != manifest(values=changed).coverage.data_fingerprint
    assert run_input_fingerprint(manifest(values=values)) != run_input_fingerprint(manifest(values=changed))
    assert left.replay_input_fingerprint != right.replay_input_fingerprint
    assert left.events == right.events
    assert left.replay_fingerprint == right.replay_fingerprint


@pytest.mark.parametrize("tick_size", [D("0"), D("-0.01"), D("NaN")])
def test_new_d2a_rv_002_invalid_tick_size_rejects(tick_size):
    with pytest.raises(ReplayError) as error:
        make_replay_inputs(manifest=manifest(), candles=candles(), tick_size=tick_size)
    assert error.value.code is ReplayFailureCode.INPUT_INVALID
