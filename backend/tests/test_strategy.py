"""Phase 4 causal context, independent geometry, immutable profile and lifecycle acceptance."""

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.analysis.domain import AnalysisConfig, IndicatorValue, SwingPoint
from app.services.analysis.engine import analyze
from app.services.market_data.domain import SECONDS, Candle, Timeframe
from app.services.news.domain import NewsConfig
from app.services.news.engine import build_context as news_context
from app.services.strategy.context import build_context, session_ranges
from app.services.strategy.domain import KeyLevel, StrategyConfig, fingerprint
from app.services.strategy.engine import evaluate, structural_plan
from app.services.strategy.indicators import calculate, ema
from app.services.strategy.patterns import detect

D = Decimal
AT = dt.datetime(2026, 9, 7, tzinfo=dt.UTC)
CONFIG = StrategyConfig()
ANALYSIS = AnalysisConfig()


def bars(tf=Timeframe.M1, count=100, at=AT, prices=None):
    values = prices if prices is not None else [D(100) + D(i % 8) / 2 for i in range(count)]
    return [
        Candle(
            symbol="XAUUSD",
            timeframe=tf,
            source="simulated",
            open_time=at - dt.timedelta(seconds=SECONDS[tf] * (len(values) - i)),
            open=D(value),
            close=D(value),
            high=D(value) + 1,
            low=D(value) - 1,
            volume=D(10),
            bid_close=D(value),
            ask_close=None,
            is_closed=True,
        )
        for i, value in enumerate(values)
    ]


def news(at=AT):
    return news_context(
        events=[],
        as_of=at,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )


def context(count=100, at=AT, inputs=None, config=CONFIG):
    return build_context(
        candles=inputs if inputs is not None else {tf: bars(tf, count, at) for tf in Timeframe},
        symbol="XAUUSD",
        source="simulated",
        at=at,
        news=news(at),
        tick_size=D(".01"),
        config=config,
        analysis_config=ANALYSIS,
        replay=True,
    )


def target_context():
    ctx = context(60)
    levels = tuple(
        KeyLevel(
            id=f"target-{i}",
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            kind="EXTERNAL_HIGH" if price > 100 else "EXTERNAL_LOW",
            price=D(price),
            origin=AT - dt.timedelta(hours=2),
            confirmed_at=AT - dt.timedelta(hours=1),
            valid_from=AT - dt.timedelta(hours=1),
            status="CONFIRMED",
            source_ids=(f"swing-{i}",),
            input_id="input",
        )
        for i, price in enumerate((120, 130, 140, 80, 70, 60))
    )
    return ctx.model_copy(update={"key_levels": levels})


def plan(ctx=None, direction="LONG", **changes):
    values = dict(
        context=ctx or target_context(),
        candidate_id="test-candidate",
        direction=direction,
        entry_lower=D(99),
        entry_upper=D(101),
        entry_id="entry-zone",
        stop_anchor=D(95) if direction == "LONG" else D(105),
        stop_id="stop-swing",
        atr=D(2),
        score=60,
        evidence=(),
        expires_at=AT + dt.timedelta(minutes=12),
        config=CONFIG,
    )
    values.update(changes)
    return structural_plan(**values)


def test_context_closed_cutoff_prefix_and_deep_immutability():
    past = bars(count=100)
    future = bars(count=50, at=AT + dt.timedelta(minutes=50))
    first = context(inputs={Timeframe.M1: past})
    second = context(inputs={Timeframe.M1: past + future})
    assert first == second
    snapshot = first.frames[0].analysis
    snapshot.events.clear()
    candles = first.frames[0].candles
    candles.clear()
    assert first.frames[0].bars == 100
    assert first.frames[0].analysis_json == second.frames[0].analysis_json
    with pytest.raises(ValidationError):
        first.as_of = AT
    with pytest.raises(ValidationError):
        first.frames[0].bars = 999


@pytest.mark.parametrize("count", [0, 34, 59, 60, 100, 150, 200, 231, 300])
def test_minimum_and_partial_history_is_explicit(count):
    result = evaluate(context(count), CONFIG)
    assert all(c.context_id == result.context.dependency_id(c.strategy_id) for c in result.candidates)
    assert all(c.plan is None for c in result.candidates)
    if count < 60:
        assert all(c.status == "BLOCKED_CONTEXT" for c in result.candidates)
    else:
        assert all(not any("INSUFFICIENT_CONTEXT" in m for m in c.missing_conditions) for c in result.candidates)
    assert len(result.profiles) == 7
    assert len({p.id for p in result.profiles}) == 7


def test_live_fixture_news_blocks_only_news_strategies():
    result = evaluate(context().model_copy(update={"mode": "ACTUAL"}), CONFIG)
    news_candidates = [c for c in result.candidates if c.strategy_id in ("STRAT05", "STRAT06")]
    non_news_candidates = [c for c in result.candidates if c.strategy_id not in ("STRAT05", "STRAT06")]
    assert all(c.status == "BLOCKED_CONTEXT" and c.plan is None for c in news_candidates)
    assert all(any("ข่าวจริง" in reason for reason in c.conflicts) for c in news_candidates)
    assert all(
        not any("ข่าวจริง" in reason or "บริบทข่าว" in reason for reason in candidate.conflicts)
        for candidate in non_news_candidates
    )


def test_context_rejects_duplicates_source_and_future_news():
    values = bars(count=2)
    with pytest.raises(ValueError):
        context(inputs={Timeframe.M1: [values[0], values[0]]})
    with pytest.raises(ValueError):
        context(inputs={Timeframe.M5: values})
    with pytest.raises(ValueError):
        build_context(
            candles={},
            symbol="XAUUSD",
            source="simulated",
            at=AT,
            news=news(AT + dt.timedelta(seconds=1)),
            tick_size=D(".01"),
            config=CONFIG,
            analysis_config=ANALYSIS,
        )


def test_rolling_window_revisions_and_fingerprints_are_deterministic():
    values = bars(count=350, at=AT + dt.timedelta(minutes=50))
    contexts = []
    for start, end in ((0, 300), (1, 301), (50, 350)):
        at = values[end - 1].open_time + dt.timedelta(minutes=1)
        contexts.append(context(at=at, inputs={Timeframe.M1: values[start:end]}))
    assert len({c.id for c in contexts}) == 3
    assert all(c.absence_means == "NOT_INCLUDED_UNKNOWN" for c in contexts)
    for c in contexts:
        assert evaluate(c, CONFIG) == evaluate(c, CONFIG)
    changed = context(config=CONFIG.model_copy(update={"minimum_rr": D(2)}))
    assert changed.config_id != context().config_id


def test_known_indicator_values_and_warmup():
    assert ema([D(1), D(2), D(3), D(4)], 3) == [None, None, D(2), D(3)]
    ascending = bars(prices=[D(i) for i in range(101, 151)])
    result = {v.name: v for v in calculate(ascending, CONFIG)}
    assert result["MACD"].value == D(7)
    assert result["MACD_SIGNAL"].value == D(7)
    assert result["MACD_HISTOGRAM"].value == D(0)
    assert result["STOCHASTIC_K"].value == D(100) * 14 / 15
    assert all(v.value is None and v.status == "WARMUP" for v in calculate([], CONFIG))
    flat = [c.model_copy(update={"high": D(100), "low": D(100), "close": D(100)}) for c in bars(count=50)]
    assert {v.name: v for v in calculate(flat, CONFIG)}["STOCHASTIC_K"].status == "UNAVAILABLE"
    with pytest.raises(ValidationError):
        bars(prices=[D("NaN")])


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_plan_geometry_has_structural_targets_tick_rounding_and_no_size(direction):
    result = plan(direction=direction)
    assert result and len(result.targets) == 3
    assert all(t.rr >= CONFIG.minimum_rr for t in result.targets)
    assert result.stop_loss < result.entry_lower if direction == "LONG" else result.stop_loss > result.entry_upper
    assert "volume" not in result.model_dump() and "lot" not in result.model_dump()


@pytest.mark.parametrize(
    "changes",
    [
        {"stop_anchor": D(110)},
        {"entry_lower": D(102)},
        {"atr": D(0)},
        {"entry_id": ""},
        {"stop_id": ""},
        {"entry_lower": D(-1)},
    ],
)
def test_plan_rejects_invalid_geometry(changes):
    assert plan(**changes) is None


def test_plan_never_skips_nearest_obstruction_to_force_rr():
    ctx = target_context()
    close = ctx.key_levels[0].model_copy(update={"id": "near", "price": D(102)})
    assert plan(ctx.model_copy(update={"key_levels": (close,) + ctx.key_levels})) is None
    assert plan(ctx.model_copy(update={"tick_size": None})) is None
    assert plan(ctx.model_copy(update={"key_levels": ctx.key_levels[:1]})) is None


@pytest.mark.parametrize(
    "day,start_utc",
    [(dt.date(2026, 3, 6), 13), (dt.date(2026, 3, 9), 12), (dt.date(2026, 10, 30), 12), (dt.date(2026, 11, 2), 13)],
)
def test_session_dst_and_provisional_extrema(day, start_utc):
    at = dt.datetime.combine(day, dt.time(23), dt.UTC)
    values = bars(Timeframe.M5, 288, at)
    ranges = session_ranges(values, at, CONFIG)
    ny = next(s for s in ranges if s.name == "NEW_YORK" and s.start.date() == day)
    assert ny.start.hour == start_utc and ny.status == "CONFIRMED"
    cutoff = ny.start + dt.timedelta(hours=1)
    running = next(s for s in session_ranges(values, cutoff, CONFIG) if s.id == ny.id)
    assert running.status == "PROVISIONAL" and not running.complete_coverage
    assert running.high == max(c.high for c in values if ny.start <= c.open_time < cutoff)


def test_session_missing_candle_never_claims_complete():
    at = AT.replace(hour=23)
    values = bars(Timeframe.M5, 288, at)
    values = [c for c in values if c.open_time != at.replace(hour=13, minute=5)]
    assert (
        next(
            s for s in session_ranges(values, at, CONFIG) if s.name == "NEW_YORK" and s.start.date() == at.date()
        ).status
        == "PROVISIONAL"
    )


@pytest.mark.parametrize(
    "kind,prices,direction",
    [
        ("DOUBLE_TOP", [110, 100, 110], "SHORT"),
        ("DOUBLE_BOTTOM", [90, 100, 90], "LONG"),
        ("TRIPLE_TOP", [110, 100, 110, 100, 110], "SHORT"),
        ("TRIPLE_BOTTOM", [90, 100, 90, 100, 90], "LONG"),
        ("HEAD_AND_SHOULDERS", [110, 100, 115, 100, 110], "SHORT"),
        ("INVERSE_HEAD_AND_SHOULDERS", [90, 100, 85, 100, 90], "LONG"),
        ("ASCENDING_TRIANGLE", [110, 95, 110, 100, 110], "LONG"),
        ("DESCENDING_TRIANGLE", [90, 105, 90, 100, 90], "SHORT"),
        ("SYMMETRICAL_TRIANGLE", [115, 90, 110, 95, 105], "LONG"),
        ("RISING_WEDGE", [105, 90, 108, 97, 111], "SHORT"),
        ("FALLING_WEDGE", [115, 100, 108, 97, 101], "LONG"),
    ],
)
def test_pattern_goldens_confirm_only_after_observable_pivots(kind, prices, direction):
    values = bars(count=100)
    start = values[70].open_time
    first_high = kind not in ("DOUBLE_BOTTOM", "TRIPLE_BOTTOM", "INVERSE_HEAD_AND_SHOULDERS", "DESCENDING_TRIANGLE")
    pivots = tuple(
        SwingPoint(
            id=f"pivot-{i}",
            scope="INTERNAL",
            kind="HIGH" if (i % 2 == 0) == first_high else "LOW",
            label="SH" if (i % 2 == 0) == first_high else "SL",
            price=D(price),
            swing_time=start + dt.timedelta(minutes=i * 4),
            confirmed_at=start + dt.timedelta(minutes=i * 4 + 2),
        )
        for i, price in enumerate(prices)
    )
    snapshot = analyze(values, "XAUUSD", Timeframe.M1, "simulated")
    snapshot = snapshot.model_copy(
        update={
            "swings": list(pivots),
            "indicators": {"ATR": IndicatorValue(value=D(4), minimum_bars_required=14, status="READY")},
        }
    )
    detected = max(p.confirmed_at for p in pivots)
    # Before final pivot knowledge no matching full pattern can be confirmed.
    early = snapshot.model_copy(update={"as_of": detected - dt.timedelta(minutes=1)})
    assert not any(
        p.kind == kind and p.source_ids == tuple(s.id for s in pivots) for p in detect(values, early, CONFIG)
    )
    value = D(max(prices) + 2 if direction == "LONG" else min(prices) - 2)
    revised = [
        c.model_copy(update={"open": value, "close": value, "high": value + 1, "low": value - 1})
        if c.open_time >= detected
        else c
        for c in values
    ]
    results = [p for p in detect(revised, snapshot, CONFIG) if p.kind == kind and p.direction == direction]
    assert any(p.status == "CONFIRMED" and p.confirmed_at >= detected + dt.timedelta(minutes=1) for p in results)


def test_flat_range_not_pattern_and_operational_clocks_not_in_identity():
    ctx = context()
    assert not detect([], ctx.frames[0].analysis, CONFIG)
    assert "generated_at" not in ctx.model_dump() and "served_at" not in ctx.model_dump()
    assert len(fingerprint(ctx)) == 64


def qualified_context(strategy_id="STRAT01", short=False):
    """Explicit upstream-contract fixture; never served as an actual-market example."""
    from app.services.analysis.domain import DealingRange, LiquidityLevel, StructureEvent, Zone
    from app.services.news.provider import fixture_release
    from app.services.strategy.domain import Pattern, PatternPoint

    ctx = target_context()
    direction = "BEARISH" if short else "BULLISH"

    def conv(v):
        return D(200) - D(v) if short else D(v)

    event_at = AT - dt.timedelta(minutes=8)
    sweep_at = AT - dt.timedelta(minutes=10)
    zone_at = AT - dt.timedelta(minutes=5)
    frames = []
    for frame in ctx.frames:
        a = frame.analysis
        event = StructureEvent(
            id="confirmation",
            scope="INTERNAL",
            kind="MSS",
            direction=direction,
            price=conv(99),
            swing_id="swing-confirmation",
            swing_time=AT - dt.timedelta(minutes=20),
            occurred_at=event_at,
            confirmed_at=event_at,
            displacement=True,
        )
        bos = event.model_copy(update={"id": "bos", "kind": "BOS"})
        sweep = LiquidityLevel(
            id="sweep",
            kind="BSL" if short else "SSL",
            side="HIGH" if short else "LOW",
            price=conv(98),
            created_at=AT - dt.timedelta(hours=2),
            confirmed_at=AT - dt.timedelta(hours=1),
            source_ids=["liquidity-swing"],
            status="SWEPT",
            swept_at=sweep_at,
            sweep_price=conv(96),
            ended_at=sweep_at,
        )
        bounds = sorted((conv(99), conv(100)))
        zone = Zone(
            id="entry-zone",
            kind="FVG",
            direction=direction,
            lower_bound=bounds[0],
            upper_bound=bounds[1],
            occurred_at=zone_at,
            confirmed_at=zone_at,
            status="OPEN",
            source_event_id=event.id,
            fill_fraction=D(0),
            ended_at=None,
        )
        dr = DealingRange(
            lower_bound=D(98),
            upper_bound=D(102),
            equilibrium=D(100),
            origin_time=AT - dt.timedelta(hours=1),
            confirmed_at=AT - dt.timedelta(minutes=30),
            direction=direction,
            swing_ids=["range-low", "range-high"],
            location="PREMIUM" if short else "DISCOUNT",
            retracement_62=D(99),
            retracement_79=D(98.5),
        )
        a = a.model_copy(
            update={
                "external_state": direction,
                "internal_state": direction,
                "events": [bos, event],
                "liquidity": [sweep],
                "zones": [zone],
                "dealing_range": dr,
                "regime": "RANGING" if strategy_id == "STRAT04" else "TRENDING_DOWN" if short else "TRENDING_UP",
                "indicators": {
                    "ATR": IndicatorValue(value=D(2), minimum_bars_required=14, status="READY"),
                    "ADX": IndicatorValue(value=D(18), minimum_bars_required=28, status="READY"),
                    "RSI": IndicatorValue(value=D(40 if short else 60), minimum_bars_required=14, status="READY"),
                },
            }
        )
        candles = frame.candles
        newest = candles[-1]
        low = conv(103) if short else D(97)
        high = conv(97) if short else D(103)
        candles[-1] = newest.model_copy(
            update={"open": conv(100), "close": conv(102), "low": low, "high": high, "bid_close": conv(102)}
        )
        # A closed reclaim exists before the structural confirmation.
        candles = [
            c.model_copy(
                update={
                    "close": conv(100),
                    "open": conv(100),
                    "high": conv(99) if short else D(101),
                    "low": conv(101) if short else D(99),
                    "bid_close": conv(100),
                }
            )
            if sweep_at <= c.open_time < event_at
            else c
            for c in candles
        ]
        point = PatternPoint(
            id="p",
            time=AT - dt.timedelta(minutes=30),
            confirmed_at=AT - dt.timedelta(minutes=28),
            price=conv(100),
            kind="HIGH" if short else "LOW",
        )
        pattern = Pattern(
            id="breakout",
            kind="DOUBLE_BOTTOM" if not short else "DOUBLE_TOP",
            direction="SHORT" if short else "LONG",
            status="CONFIRMED",
            points=(point,),
            neckline=conv(100),
            upper=D(104),
            lower=D(96),
            confirmed_at=AT - dt.timedelta(minutes=10),
            detected_at=AT - dt.timedelta(minutes=20),
            expires_at=AT + dt.timedelta(minutes=30),
            source_ids=("p",),
            reason_th="ข้อมูลทดสอบ",
        )
        import json

        frames.append(
            frame.model_copy(
                update={
                    "analysis_json": a.model_dump_json(),
                    "candles_json": json.dumps([c.model_dump(mode="json") for c in candles]),
                    "patterns": (pattern,),
                }
            )
        )
    released = fixture_release(AT - dt.timedelta(minutes=20), "negative" if not short else "positive")
    n = news_context(
        events=released,
        as_of=AT,
        source="fixture_economic_v1",
        mode="FIXTURE",
        config=NewsConfig(),
        candles=[],
        quotes=[],
        structure=None,
        market_source="simulated",
    )
    n = n.model_copy(
        update={
            "macro_bias": "USD_POSITIVE" if short else "USD_NEGATIVE",
            "spread_state": "SPREAD_NORMAL",
            "volatility_state": "NORMAL",
            "trade_policy_state": "INFORMATIONAL",
            "reaction_state": "LIQUIDITY_SWEEP_REVERSAL" if strategy_id == "STRAT06" else "STRONG_DIRECTIONAL",
            "strategy_eligibility": {k: "ELIGIBLE" for k in n.strategy_eligibility},
            "structure_confirmation": n.structure_confirmation.model_copy(update={"status": "ALIGNED"}),
        }
    )
    from app.services.strategy.domain import MarketSafetyContext

    safety = MarketSafetyContext(
        spread_state="SPREAD_NORMAL",
        volatility_state="NORMAL",
        current_spread=D(".02"),
        baseline_spread=D(".02"),
        quote_as_of=AT,
        source_ids=("explicit-test-quote",),
    )
    result = ctx.model_copy(
        update={
            "frames": tuple(frames),
            "news_json": n.model_dump_json(),
            "news_fingerprint": n.fingerprint,
            "market_safety": safety,
        }
    )
    market_id = fingerprint(result.model_dump(exclude={"id", "market_context_id", "news_json", "news_fingerprint"}))
    return result.model_copy(update={"market_context_id": market_id, "id": fingerprint([market_id, n.fingerprint])})


@pytest.mark.parametrize("strategy_id", ["STRAT01", "STRAT02", "STRAT03", "STRAT04", "STRAT05", "STRAT06"])
@pytest.mark.parametrize("short", [False, True])
def test_six_playbook_long_short_goldens(strategy_id, short):
    from app.services.strategy.engine import REGISTRY, profiles

    ctx = qualified_context(strategy_id, short)
    profile = next(p for p in profiles(CONFIG, ctx.config_id) if p.id == "smc").model_copy(
        update={"allowed_strategies": (strategy_id,)}
    )
    candidate = REGISTRY[strategy_id].evaluate(ctx, profile, CONFIG)
    assert candidate.status == "READY", (candidate.missing_conditions, candidate.conflicts, candidate.evidence)
    assert candidate.direction == ("SHORT" if short else "LONG")
    assert candidate.plan and len(candidate.plan.targets) >= 2
    assert candidate.plan.context_id == ctx.dependency_id(strategy_id)


def test_advisory_news_does_not_block_non_news_strategy_and_profiles_are_isolated():
    from app.services.strategy.engine import REGISTRY, profiles

    ctx = qualified_context()
    traders = tuple(p for p in profiles(CONFIG, ctx.config_id) if p.id == "smc")
    first = REGISTRY["STRAT01"].evaluate(ctx, traders[0], CONFIG)
    assert first.status == "READY"
    n = ctx.news.model_copy(
        update={
            "calendar_state": "CALENDAR_UNAVAILABLE",
            "trade_policy_state": "RESTRICTED",
            "strategy_eligibility": {"MEAN_REVERSION": "BLOCKED"},
            "macro_bias": "CONFLICTING",
        }
    )
    advisory = ctx.model_copy(update={"news_json": n.model_dump_json()})
    other = REGISTRY["STRAT01"].evaluate(advisory, traders[0], CONFIG)
    assert other.status == "READY" and other.plan is not None
    assert all(item.code != "NEWS" for item in other.evidence)
    assert not any("ข่าว" in reason for reason in other.conflicts)
    assert REGISTRY["STRAT01"].evaluate(ctx, traders[0], CONFIG) == first
    assert all(c.context_id == ctx.dependency_id(c.strategy_id) for c in evaluate(ctx, CONFIG).candidates)


@pytest.mark.parametrize("strategy_id", ["STRAT05", "STRAT06"])
def test_unavailable_calendar_remains_a_hard_block_for_news_strategies(strategy_id):
    from app.services.strategy.engine import REGISTRY, profiles

    ctx = qualified_context(strategy_id)
    n = ctx.news.model_copy(
        update={
            "calendar_state": "CALENDAR_UNAVAILABLE",
            "trade_policy_state": "RESTRICTED",
            "strategy_eligibility": {"NEWS_MOMENTUM": "WAITING", "NEWS_REVERSAL": "WAITING"},
        }
    )
    unavailable = ctx.model_copy(update={"news_json": n.model_dump_json()})
    profile = next(p for p in profiles(CONFIG, ctx.config_id) if p.id == "news").model_copy(
        update={"allowed_strategies": (strategy_id,)}
    )
    candidate = REGISTRY[strategy_id].evaluate(unavailable, profile, CONFIG)
    assert candidate.status == "BLOCKED_CONTEXT" and candidate.plan is None
    assert any("ข่าวจริง" in reason for reason in candidate.conflicts)


def test_lifecycle_absence_expiry_and_explicit_invalidation():
    from app.services.strategy.engine import REGISTRY, profiles
    from app.services.strategy.lifecycle import transition

    ctx = qualified_context()
    candidate = REGISTRY["STRAT01"].evaluate(
        ctx, next(p for p in profiles(CONFIG, ctx.config_id) if p.id == "smc"), CONFIG
    )
    empty = context(inputs={}).model_copy(update={"id": "next", "as_of": AT + dt.timedelta(minutes=1)})
    assert transition(candidate, empty) is None
    expired = empty.model_copy(update={"as_of": candidate.expires_at})
    assert transition(candidate, expired).to_status == "EXPIRED"
    assert transition(candidate, expired, current_status="EXPIRED") is None
    assert transition(candidate, empty.model_copy(update={"as_of": AT - dt.timedelta(minutes=1)})) is None
    replacement = candidate.model_copy(update={"id": "new", "context_id": "next"})
    assert transition(candidate, empty, replacement).to_status == "SUPERSEDED"
    snapshot = ctx.frames[0].analysis
    z = snapshot.zones[0].model_copy(update={"status": "INVALIDATED", "ended_at": AT + dt.timedelta(minutes=1)})
    snapshot = snapshot.model_copy(update={"zones": [z]})
    frame = ctx.frames[0].model_copy(update={"analysis_json": snapshot.model_dump_json()})
    changed = empty.model_copy(update={"frames": (frame,)})
    assert transition(candidate, changed).to_status == "INVALIDATED"


async def test_repository_idempotence_and_conflict_rejects_overwrite(db_session):
    from sqlalchemy import func, select

    from app.models.strategy import StrategyEvaluationRecord, TradeCandidateRecord
    from app.services.strategy.repository import persist

    session, _ = db_session
    result = evaluate(context(), CONFIG)
    first = await persist(session, result)
    await session.commit()
    second = await persist(session, result)
    assert first == second
    assert await session.scalar(select(func.count()).select_from(StrategyEvaluationRecord)) == len(result.candidates)
    assert await session.scalar(select(func.count()).select_from(TradeCandidateRecord)) == len(result.candidates)
    bad = result.model_copy(update={"candidates": ()})
    with pytest.raises(ValueError, match="identity conflict"):
        await persist(session, bad)
    from app.services.strategy.identity import projections

    for value in projections(result):
        assert (await session.get(StrategyEvaluationRecord, value.id)).payload == value.model_dump(mode="json")


@pytest.mark.parametrize(
    "path",
    [
        "/api/strategy/context",
        "/api/strategies",
        "/api/trader-profiles",
        "/api/strategy/evaluations",
        "/api/trade-candidates",
        "/api/trade-plan/current",
    ],
)
def test_strategy_routes_require_authentication(client, path):
    assert client.get(path).status_code == 401


def test_candle_by_candle_replay_has_no_future_visibility():
    values = bars(count=80)
    for count in range(1, 81):
        at = values[count - 1].open_time + dt.timedelta(minutes=1)
        accumulated = context(at=at, inputs={Timeframe.M1: values[:count]})
        full = context(at=at, inputs={Timeframe.M1: values})
        assert accumulated == full
        assert evaluate(accumulated, CONFIG) == evaluate(full, CONFIG)


@pytest.mark.parametrize("short", [False, True])
def test_flag_requires_pole_and_failed_pattern_records_failure(short):
    values = bars(count=100)
    start = values[70].open_time

    def mirror(v):
        return D(220) - D(v) if short else D(v)

    prices = [110, 100, 108, 98, 106]
    pivots = [
        SwingPoint(
            id=f"flag-{i}",
            scope="INTERNAL",
            kind="LOW" if (i % 2 == 0) == short else "HIGH",
            label="SL" if (i % 2 == 0) == short else "SH",
            price=mirror(v),
            swing_time=start + dt.timedelta(minutes=i * 4),
            confirmed_at=start + dt.timedelta(minutes=i * 4 + 2),
        )
        for i, v in enumerate(prices)
    ]
    snapshot = analyze(values, "XAUUSD", Timeframe.M1, "simulated").model_copy(
        update={
            "swings": pivots,
            "indicators": {"ATR": IndicatorValue(value=D(4), minimum_bars_required=14, status="READY")},
        }
    )
    detected = max(p.confirmed_at for p in pivots)
    for i in range(62, 70):
        value = mirror(90 + (i - 62) * 3)
        values[i] = values[i].model_copy(update={"open": value, "close": value, "high": value + 1, "low": value - 1})
    for i, c in enumerate(values):
        if c.open_time >= detected:
            value = mirror(114)
            values[i] = c.model_copy(update={"open": value, "close": value, "high": value + 1, "low": value - 1})
    kind = "BEARISH_FLAG" if short else "BULLISH_FLAG"
    assert any(p.kind == kind and p.status == "CONFIRMED" for p in detect(values, snapshot, CONFIG))
    value = mirror(80)
    values[-1] = values[-1].model_copy(update={"open": value, "close": value, "high": value + 1, "low": value - 1})
    assert any(p.kind == kind and p.status == "INVALIDATED" for p in detect(values, snapshot, CONFIG))


def test_operational_clock_normalizes_postgres_session_offset():
    from app.services.strategy.domain import StrategyResponse

    offset = AT.astimezone(dt.timezone(dt.timedelta(hours=7)))
    response = StrategyResponse(
        evaluation=evaluate(context(0), CONFIG), generated_at=offset, served_at=offset, stale=True
    )
    assert response.model_dump(mode="json")["generated_at"].endswith("Z")
    assert response.evaluation.context.as_of == AT


def test_unknown_spread_and_volatility_are_not_described_as_extreme():
    result = evaluate(context(), CONFIG)
    reasons = {reason for candidate in result.candidates for reason in candidate.conflicts}
    assert "ยังไม่มีข้อมูลส่วนต่างราคาที่ตรวจสอบได้" in reasons
    assert "ยังไม่มีข้อมูลความผันผวนที่ตรวจสอบได้" in reasons
    assert "ความผันผวนสูงเกินเงื่อนไข" not in reasons
