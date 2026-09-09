"""Independent golden cases and causal-prefix invariants for descriptive analysis."""

import datetime as dt
from decimal import Decimal

import pytest

from app.services.analysis.domain import AnalysisConfig
from app.services.analysis.engine import AnalysisEngine, AnalysisInputError, analyze
from app.services.analysis.service import AnalysisService
from app.services.market_data.domain import SECONDS, Candle, Timeframe

START = dt.datetime(2026, 8, 3, tzinfo=dt.UTC)
CONFIG = AnalysisConfig(
    internal_left=1,
    internal_right=1,
    external_left=1,
    external_right=1,
    atr_period=2,
    average_period=3,
    displacement_atr=Decimal(".8"),
)


def bar(index, close=100, *, opening=None, high=None, low=None, tf=Timeframe.M1, closed=True):
    close = Decimal(str(close))
    opening = close - Decimal(".2") if opening is None else Decimal(str(opening))
    return Candle(
        symbol="XAUUSD",
        timeframe=tf,
        source="simulated",
        open_time=START + dt.timedelta(seconds=index * SECONDS[tf]),
        open=opening,
        high=max(close, opening) + 1 if high is None else Decimal(str(high)),
        low=min(close, opening) - 1 if low is None else Decimal(str(low)),
        close=close,
        bid_close=close,
        ask_close=None,
        volume="10",
        is_closed=closed,
    )


def run(candles, config=CONFIG, requested=300):
    return analyze(candles, "XAUUSD", candles[0].timeframe if candles else Timeframe.M1, "simulated", requested, config)


def trend():
    bars = [
        bar(i, v, opening=Decimal(v) + Decimal(".2") if i % 2 == 0 else Decimal(v) - Decimal(".2"))
        for i, v in enumerate([100, 104, 101, 106, 103, 108, 105])
    ]
    bars += [
        bar(7, 113, opening=105, high=Decimal("113.2"), low=104),
        bar(8, 94, opening=113, high=114, low=Decimal("93.8")),
    ]
    return bars


def mirror(candles):
    return [
        c.model_copy(
            update={
                "open": 220 - c.open,
                "high": 220 - c.low,
                "low": 220 - c.high,
                "close": 220 - c.close,
                "bid_close": 220 - c.close,
            }
        )
        for c in candles
    ]


@pytest.mark.parametrize("mirrored", [False, True])
def test_golden_structure_bos_choch_mss_and_ob(mirrored):
    bars = mirror(trend()) if mirrored else trend()
    result = run(bars)
    direction = "BEARISH" if mirrored else "BULLISH"
    counter = "BULLISH" if mirrored else "BEARISH"
    events = [e for e in result.events if e.scope == "EXTERNAL"]
    assert [(e.kind, e.direction, e.occurred_at) for e in events] == [
        ("BOS", direction, bars[5].open_time),
        ("BOS", direction, bars[7].open_time),
        ("CHOCH", counter, bars[8].open_time),
        ("MSS", counter, bars[8].open_time),
    ]
    assert events[3].parent_event_id == events[2].id and events[3].displacement
    assert events[1].confirmed_at == bars[8].open_time
    labels = [s.label for s in result.swings if s.scope == "EXTERNAL"]
    assert {"LH", "LL"}.issubset(labels) if mirrored else {"HH", "HL"}.issubset(labels)
    blocks = [z for z in result.zones if z.kind == "OB"]
    assert len(blocks) >= 2
    assert any(z.direction == counter and z.occurred_at == bars[7].open_time for z in blocks)
    assert result.news_context == "UNKNOWN"


def test_choch_without_displacement_is_not_mss():
    bars = trend()[:8]
    bars.append(bar(8, 101, opening=Decimal("101.1"), high=102, low=100))
    result = run(bars)
    events = [e for e in result.events if e.occurred_at == bars[-1].open_time]
    assert events and all(e.kind == "CHOCH" and not e.displacement for e in events)
    assert result.external_state == "NEUTRAL"


def test_pivot_confirmation_delay_and_forming_bar_ignored():
    bars = [bar(i, v) for i, v in enumerate([100, 101, 105, 102, 101])]
    before = run(bars[:4], AnalysisConfig())
    after = run(bars, AnalysisConfig())
    assert not before.swings
    internal = [s for s in after.swings if s.scope == "INTERNAL"]
    assert len(internal) == 1 and internal[0].swing_time == bars[2].open_time
    assert internal[0].confirmed_at == bars[4].open_time + dt.timedelta(minutes=1)
    forming = bars[-1].model_copy(update={"is_closed": False})
    assert run(bars[:-1] + [forming], AnalysisConfig()).swings == before.swings
    assert run(bars[:-1] + [forming], AnalysisConfig()).history.closed == 4


def test_equal_tolerance_plateaus_and_flat():
    values = [100, 105, 101, Decimal("105.01"), 102]
    labels = [s.label for s in run([bar(i, v) for i, v in enumerate(values)]).swings]
    assert "EQH" in labels
    assert any(level.kind == "EQH" for level in run([bar(i, v) for i, v in enumerate(values)]).liquidity)
    assert not run([bar(i, 100, opening=100, high=100, low=100) for i in range(30)]).swings
    tied = [bar(i, v) for i, v in enumerate([100, 105, 105, 100])]
    assert not run(tied).swings


@pytest.mark.parametrize("mirrored", [False, True])
def test_sweep_distinct_from_close_break(mirrored):
    bars = [bar(i, v) for i, v in enumerate([100, 105, 101])]
    probe = bar(3, 105, opening=104, high=108, low=103)
    candles = mirror(bars + [probe]) if mirrored else bars + [probe]
    result = run(candles)
    swept = [level for level in result.liquidity if level.status == "SWEPT"]
    assert len(swept) == 1
    assert swept[0].swept_at == candles[-1].open_time + dt.timedelta(minutes=1)
    assert not result.events
    broken = bar(3, 108, opening=104, high=109, low=103)
    result = run(mirror(bars + [broken]) if mirrored else bars + [broken])
    assert any(level.status == "INVALIDATED" for level in result.liquidity)
    assert not any(level.status == "SWEPT" for level in result.liquidity)


@pytest.mark.parametrize("mirrored", [False, True])
def test_fvg_lifecycle_and_inversion(mirrored):
    bars = [
        bar(0, 100, opening=100, high=101, low=99),
        bar(1, 103, opening=100, high=104, low=99),
        bar(2, 105, opening=104, high=106, low=103),
    ]
    if mirrored:
        bars = mirror(bars)
    first = next(z for z in run(bars).zones if z.kind == "FVG")
    assert first.confirmed_at == bars[2].open_time + dt.timedelta(minutes=1)
    assert (first.lower_bound, first.upper_bound) == (
        (Decimal(117), Decimal(119)) if mirrored else (Decimal(101), Decimal(103))
    )
    partial = bar(3, 104, opening=104, high=105, low=102)
    partial = mirror([partial])[0] if mirrored else partial
    zone = next(z for z in run(bars + [partial]).zones if z.id == first.id)
    assert zone.status == "PARTIALLY_FILLED" and zone.fill_fraction == Decimal(".5")
    filled = bar(4, 103, opening=103, high=104, low=101)
    filled = mirror([filled])[0] if mirrored else filled
    assert next(z for z in run(bars + [partial, filled]).zones if z.id == first.id).status == "FILLED"
    invalid = bar(3, 98, opening=105, high=106, low=97)
    invalid = mirror([invalid])[0] if mirrored else invalid
    result = run(bars + [invalid])
    assert next(z for z in result.zones if z.id == first.id).status == "INVALIDATED"
    assert any(z.kind == "IFVG" and z.source_event_id == first.id for z in result.zones)
    gap = bars[2].model_copy(update={"open_time": bars[2].open_time + dt.timedelta(minutes=1)})
    assert not run(bars[:2] + [gap]).zones


def test_range_indicator_oracles_and_session_boundaries():
    result = run(trend()[:7])
    r = result.dealing_range
    assert r is not None and r.lower_bound < r.equilibrium < r.upper_bound
    assert r.equilibrium == (r.lower_bound + r.upper_bound) / 2
    assert r.confirmed_at <= result.as_of
    flat = run([bar(i, 100, opening=100, high=100, low=100) for i in range(30)])
    assert flat.indicators["RSI"].value == 50
    assert flat.indicators["ATR"].value == flat.indicators["ADX"].value == 0
    assert flat.indicators["SMA"].value == flat.indicators["EMA"].value == 100
    assert flat.indicators["BOLLINGER_UPPER"].value == flat.indicators["BOLLINGER_LOWER"].value == 100
    rising = run([bar(i, 100 + i, opening=100 + i, high=100 + i, low=100 + i) for i in range(30)])
    assert rising.indicators["ATR"].value == 1 and rising.indicators["RSI"].value == 100
    assert rising.indicators["ADX"].value == 100
    assert rising.indicators["SMA"].value == 128
    hours = [bar(i, 100 + i % 7, tf=Timeframe.H1) for i in range(170)]
    session = run(hours, AnalysisConfig())
    assert any(s.name == "ASIA" for s in session.sessions)
    assert {"PDH", "PDL", "PWH", "PWL"}.issubset({level.kind for level in session.liquidity})
    # The first partial day in a truncated input must never masquerade as a complete day.
    assert not any(level.kind == "PDH" for level in run(hours[5:24]).liquidity)


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4, 5, 10, 11, 12, 14, 15, 16, 27, 28, 29, 50, 100, 231, 300])
def test_minimum_counts_partial_history(count):
    result = run([bar(i, 100 + i % 5) for i in range(count)], AnalysisConfig())
    assert result.history.closed == count and result.history.returned == count
    assert result.history.status == ("EMPTY" if count == 0 else "COMPLETE" if count == 300 else "PARTIAL")
    for module in result.modules.values():
        assert (module.status == "INSUFFICIENT_DATA") == (count < module.minimum_bars_required)


def test_batch_streaming_prefix_invariance_and_bounded_state():
    bars = [bar(i, 100 + (i % 10 if i % 20 < 10 else 20 - i % 20)) for i in range(100)]
    engine = AnalysisEngine("XAUUSD", Timeframe.M1, "simulated", CONFIG)
    past = {}
    for i, candle in enumerate(bars):
        engine.feed(candle)
        snapshot = engine.snapshot()
        assert snapshot == run(bars[: i + 1])
        immutable = {v.id: v.model_dump_json() for v in snapshot.swings + snapshot.events}
        assert all(immutable.get(key) == value for key, value in past.items())
        past = immutable
    for i in range(100, 2000):
        engine.feed(bar(i, 100 + i % 13))
    assert len(engine.bars) <= 150
    assert all(
        len(items) <= CONFIG.max_objects for items in (engine.swings, engine.events, engine.levels, engine.zones)
    )
    assert len(engine.groups) <= 40 and len(engine.sessions) <= 32


@pytest.mark.parametrize(
    "mutation",
    [
        {"high": Decimal(1)},
        {"close": Decimal("NaN")},
        {"volume": Decimal("Infinity")},
        {"source": "mt5_demo_iux"},
        {"symbol": "EURUSD"},
        {"timeframe": Timeframe.M5},
        {"open_time": START.replace(tzinfo=None)},
    ],
)
def test_malformed_input_is_controlled(mutation):
    with pytest.raises(AnalysisInputError):
        analyze([bar(0).model_copy(update=mutation)], "XAUUSD", Timeframe.M1, "simulated")


def test_duplicate_order_forming_and_config_identity():
    for values in ([bar(0), bar(0)], [bar(1), bar(0)], [bar(0, closed=False), bar(1)]):
        with pytest.raises(AnalysisInputError):
            run(values)
    a = run(trend())
    b = run(trend(), CONFIG.model_copy(update={"equal_ticks": 0}))
    assert a.config_id != b.config_id and set(s.id for s in a.swings).isdisjoint(s.id for s in b.swings)
    with pytest.raises(AnalysisInputError):
        run([bar(i) for i in range(1001)])


async def test_cache_forming_updates_corrections_source_and_bound():
    service = AnalysisService()
    values = trend() + [bar(9, closed=False)]
    first = await service.snapshot(values, "XAUUSD", Timeframe.M1, "simulated", config=CONFIG)
    second = await service.snapshot(
        values[:-1] + [bar(9, 101, closed=False)], "XAUUSD", Timeframe.M1, "simulated", config=CONFIG
    )
    assert first == second and service.calculations == 1 and service.hits == 1
    await service.snapshot(values[:-1] + [bar(9, 101)], "XAUUSD", Timeframe.M1, "simulated", config=CONFIG)
    assert service.calculations == 2
    for count in range(1, 36):
        await service.snapshot(values[:1], "XAUUSD", Timeframe.M1, "simulated", requested=count, config=CONFIG)
    assert len(service.cache) == 32


def test_analysis_api_auth_invalid_requests(client, auth_headers):
    for path in ("/api/analysis/structure", "/api/analysis/context"):
        assert client.get(path).status_code == 401
        assert client.get(path + "?limit=1001", headers=auth_headers).status_code == 422
    assert client.get("/api/analysis/structure?timeframe=M2", headers=auth_headers).status_code == 422
    assert client.get("/api/analysis/structure?symbol=UNKNOWN", headers=auth_headers).status_code == 404


@pytest.mark.parametrize("tf", list(Timeframe))
def test_all_timeframe_prefix_confirmation_and_source_identity(tf):
    candles = [bar(i, 100 + i % 7, tf=tf) for i in range(50)]
    short = run(candles[:25])
    long = run(candles)
    assert all(s.confirmed_at <= short.as_of for s in short.swings)
    by_id = {s.id: s for s in long.swings}
    assert all(by_id[s.id] == s for s in short.swings)
    assert long.input_id != short.input_id and long.window_start == short.window_start
    other = analyze(
        [c.model_copy(update={"source": "mt5_demo_iux"}) for c in candles], "XAUUSD", tf, "mt5_demo_iux", config=CONFIG
    )
    assert set(s.id for s in long.swings).isdisjoint(s.id for s in other.swings)


def test_configuration_is_validated_and_no_execution_dependencies():
    import ast
    from pathlib import Path

    from pydantic import ValidationError

    from app.core.config import Settings

    for config in (
        {"internal_right": 0},
        {"max_objects": 999},
        {"session_hours": {"ASIA": [20, 5]}},
        {"low_volatility_ratio": ".1", "high_volatility_ratio": ".01"},
    ):
        with pytest.raises(ValidationError):
            AnalysisConfig.model_validate(config)
    assert Settings(_env_file=None, analysis_config={"internal_right": 3}).analysis_config.internal_right == 3
    root = Path(__file__).parents[1] / "app/services/analysis"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(part in (node.module or "") for part in ("broker", "MetaTrader5", "trading", "ai."))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"order_send", "order_check", "login"}


def test_zero_and_small_decimal_serialization_matches_generated_pattern():
    import re

    from app.services.analysis.domain import IndicatorValue

    schema = IndicatorValue.model_json_schema(mode="serialization")["properties"]["value"]["anyOf"][0]
    for value in (Decimal("0E-8"), Decimal("1E-8"), Decimal("1E+8")):
        payload = IndicatorValue(value=value, minimum_bars_required=1, status="READY").model_dump(mode="json")
        assert re.fullmatch(schema["pattern"], payload["value"])
        assert "E" not in payload["value"]
        assert Decimal(payload["value"]) == value


@pytest.mark.parametrize("mirrored", [False, True])
def test_order_block_mitigation_invalidation_and_breaker(mirrored):
    values = trend()[:8]
    original = mirror(values) if mirrored else values
    first = next(z for z in run(original).zones if z.kind == "OB" and z.occurred_at == values[6].open_time)
    touch = bar(8, 112, opening=111, high=114, low=Decimal("105.2"))
    broken = bar(9, 102, opening=111, high=112, low=101)
    touch, broken = mirror([touch, broken]) if mirrored else [touch, broken]
    assert next(z for z in run(original + [touch]).zones if z.id == first.id).status == "MITIGATED"
    result = run(original + [touch, broken])
    assert next(z for z in result.zones if z.id == first.id).status == "INVALIDATED"
    assert any(z.kind == "BREAKER" and z.source_event_id == first.id for z in result.zones)


def test_session_minimum_and_coarse_candle_coverage_are_honest():
    m1 = run([bar(i) for i in range(300)], AnalysisConfig())
    assert m1.modules["sessions"].minimum_bars_required == 480
    assert m1.modules["sessions"].status == "INSUFFICIENT_DATA"
    h4 = run([bar(i, 100 + i % 5, tf=Timeframe.H4) for i in range(30)], AnalysisConfig())
    assert h4.sessions and all(s.name == "ASIA" for s in h4.sessions)
    assert h4.modules["sessions"].minimum_bars_required == 2
    d1 = run([bar(i, 100 + i % 5, tf=Timeframe.D1) for i in range(30)], AnalysisConfig())
    assert not d1.sessions and d1.modules["sessions"].status == "NO_STRUCTURE"
