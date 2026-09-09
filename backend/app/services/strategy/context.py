"""One deterministic context from canonical closed bars and point-in-time news."""

import datetime as dt
import json
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.analysis.domain import AnalysisConfig
from app.services.analysis.engine import analyze
from app.services.market_data.domain import SECONDS, Candle, Timeframe
from app.services.news.domain import NewsMarketContext, NewsStrategyContext, ObservedQuote
from app.services.strategy.domain import (
    Frame,
    Indicator,
    KeyLevel,
    MarketSafetyContext,
    SessionRange,
    StrategyConfig,
    StrategyMarketContext,
    fingerprint,
)
from app.services.strategy.indicators import calculate
from app.services.strategy.patterns import detect


def session_ranges(candles: list[Candle], at: dt.datetime, config: StrategyConfig) -> tuple[SessionRange, ...]:
    if not candles:
        return ()
    step = SECONDS[candles[0].timeframe]
    result: list[SessionRange] = []
    for definition in config.sessions:
        zone = ZoneInfo(definition.timezone)
        local = at.astimezone(zone).date()
        for days in range(3):
            day = local - dt.timedelta(days=days)
            start = dt.datetime.combine(day, dt.time(definition.start_hour), zone).astimezone(dt.UTC)
            end = (dt.datetime.combine(day, dt.time(), zone) + dt.timedelta(hours=definition.end_hour)).astimezone(
                dt.UTC
            )
            if start > at:
                continue
            bars = [
                c
                for c in candles
                if c.is_closed and start <= c.open_time and c.open_time + dt.timedelta(seconds=step) <= min(at, end)
            ]
            if not bars:
                continue
            expected = int((end - start).total_seconds()) // step
            complete = (
                at >= end
                and len(bars) == expected
                and bars[0].open_time == start
                and bars[-1].open_time + dt.timedelta(seconds=step) == end
                and all(
                    (b.open_time - a.open_time).total_seconds() == step for a, b in zip(bars, bars[1:], strict=False)
                )
            )
            result.append(
                SessionRange(
                    id=fingerprint([definition.model_dump(mode="json"), start]),
                    name=definition.name,
                    timezone=definition.timezone,
                    start=start,
                    end=end,
                    high=max(c.high for c in bars),
                    low=min(c.low for c in bars),
                    status="CONFIRMED" if complete else "PROVISIONAL",
                    complete_coverage=complete,
                )
            )
    return tuple(sorted(result, key=lambda r: (r.start, r.name)))


def build_context(
    *,
    candles: dict[Timeframe, list[Candle]],
    symbol: str,
    source: str,
    at: dt.datetime,
    news: NewsMarketContext,
    tick_size: Decimal | None,
    config: StrategyConfig,
    analysis_config: AnalysisConfig,
    replay: bool = False,
    quotes: tuple[ObservedQuote, ...] = (),
) -> StrategyMarketContext:
    if at.tzinfo is None:
        raise ValueError("Aware cutoff required")
    at = at.astimezone(dt.UTC)
    news = NewsStrategyContext.model_validate(news.model_dump(include=set(NewsStrategyContext.model_fields)))
    if news.as_of > at or news.market_source not in (None, source) or news.symbol != symbol:
        raise ValueError("News provenance/cutoff mismatch")
    config_id = fingerprint([config.model_dump(mode="json"), analysis_config.model_dump(mode="json")])
    frames: list[Frame] = []
    levels: list[KeyLevel] = []
    canonical: dict[Timeframe, list[Candle]] = {}
    for tf in sorted(candles, key=lambda t: SECONDS[t]):
        values = candles[tf]
        if len(values) > 1000 or any(c.symbol != symbol or c.source != source or c.timeframe != tf for c in values):
            raise ValueError("Invalid bounded canonical input")
        if any(a.open_time >= b.open_time for a, b in zip(values, values[1:], strict=False)):
            raise ValueError("Canonical input must be unique and ascending")
        bars = [c for c in values if c.is_closed and c.open_time + dt.timedelta(seconds=SECONDS[tf]) <= at]
        canonical[tf] = bars
        snapshot = analyze(bars[-300:], symbol, tf, source, requested=300, config=analysis_config)
        extras = calculate(bars[-300:], config)
        reused = tuple(
            Indicator(
                name=name,
                value=item.value,
                minimum_bars=item.minimum_bars_required,
                status="READY" if item.value is not None else "WARMUP",
            )
            for name, item in snapshot.indicators.items()
        )
        frame = Frame(
            timeframe=tf,
            input_id=snapshot.input_id,
            config_id=snapshot.config_id,
            algorithm_version=snapshot.algorithm_version,
            window_start=snapshot.window_start,
            as_of=snapshot.as_of,
            bars=len(bars[-300:]),
            requested=300,
            candles_json=json.dumps([c.model_dump(mode="json") for c in bars[-300:]], sort_keys=True),
            analysis_json=snapshot.model_dump_json(),
            indicators=reused + extras,
            patterns=detect(bars[-300:], snapshot, config),
        )
        frames.append(frame)

        def add(kind, price, origin, confirmed, ids, status="CONFIRMED", upper=None, tf=tf, snapshot=snapshot):
            levels.append(
                KeyLevel(
                    id=fingerprint([symbol, source, tf, kind, ids, origin]),
                    symbol=symbol,
                    timeframe=tf,
                    kind=kind,
                    price=price,
                    upper=upper,
                    origin=origin,
                    confirmed_at=confirmed,
                    valid_from=confirmed or origin,
                    status=status,
                    source_ids=tuple(ids),
                    input_id=snapshot.input_id,
                )
            )

        for swing in snapshot.swings:
            add(swing.scope + "_" + swing.kind, swing.price, swing.swing_time, swing.confirmed_at, [swing.id])
        for level in snapshot.liquidity:
            add(
                level.kind,
                level.price,
                level.created_at,
                level.confirmed_at,
                [level.id],
                level.status if level.status != "ACTIVE" else "CONFIRMED",
            )
        for zone in snapshot.zones:
            add(
                zone.kind,
                zone.lower_bound,
                zone.occurred_at,
                zone.confirmed_at,
                [zone.id],
                "INVALIDATED" if zone.status == "INVALIDATED" else "CONFIRMED",
                zone.upper_bound,
            )
        if snapshot.dealing_range:
            dr = snapshot.dealing_range
            add("EQUILIBRIUM", dr.equilibrium, dr.origin_time, dr.confirmed_at, list(dr.swing_ids))
        if tf in (Timeframe.D1, Timeframe.W1) and bars:
            last = bars[-1]
            prefix = "PD" if tf == Timeframe.D1 else "PW"
            close_at = last.open_time + dt.timedelta(seconds=SECONDS[tf])
            identity = fingerprint(last.model_dump(mode="json"))
            add(prefix + "H", last.high, last.open_time, close_at, [identity])
            add(prefix + "L", last.low, last.open_time, close_at, [identity])
    sessions = session_ranges(canonical.get(Timeframe.M5, []), at, config)
    for session in sessions:
        for side, price in (("HIGH", session.high), ("LOW", session.low)):
            levels.append(
                KeyLevel(
                    id=fingerprint([session.id, side]),
                    symbol=symbol,
                    timeframe=Timeframe.M5,
                    kind=session.name + "_" + side,
                    price=price,
                    origin=session.start,
                    confirmed_at=session.end if session.status == "CONFIRMED" else None,
                    valid_from=session.end if session.status == "CONFIRMED" else at,
                    status=session.status,
                    source_ids=(session.id,),
                    input_id=fingerprint([session.model_dump(mode="json"), at]),
                )
            )
    intraday = canonical.get(Timeframe.M5, [])
    day_start = at.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - dt.timedelta(days=day_start.weekday())
    for name, boundary in (("DAILY_OPEN", day_start), ("WEEKLY_OPEN", week_start)):
        bar = next((c for c in intraday if c.open_time == boundary), None)
        if bar:
            close_at = bar.open_time + dt.timedelta(minutes=5)
            levels.append(
                KeyLevel(
                    id=fingerprint([source, name, boundary]),
                    symbol=symbol,
                    timeframe=Timeframe.M5,
                    kind=name,
                    price=bar.open,
                    origin=boundary,
                    confirmed_at=close_at,
                    valid_from=close_at,
                    status="CONFIRMED",
                    source_ids=(fingerprint(bar.model_dump(mode="json")),),
                    input_id=fingerprint(bar.model_dump(mode="json")),
                )
            )
    active = [s.name for s in sessions if s.start <= at < s.end]
    current = "OVERLAP" if len(active) > 1 else active[0] if active else "OFF_HOURS"
    # Quote baseline is the preceding market minute, independent of calendar.
    observed = sorted(
        (q for q in quotes if q.source == source and q.timestamp <= at and q.observed_at <= at),
        key=lambda q: q.timestamp,
    )
    recent = [q for q in observed if at - dt.timedelta(seconds=70) <= q.timestamp < at - dt.timedelta(seconds=10)]
    fresh = [q for q in observed if at - dt.timedelta(seconds=10) <= q.timestamp]
    baseline = sum((q.ask - q.bid for q in recent), Decimal(0)) / len(recent) if len(recent) >= 3 else None
    current_spread = fresh[-1].ask - fresh[-1].bid if fresh else None
    ratio = current_spread / baseline if baseline and current_spread is not None else None
    m1 = canonical.get(Timeframe.M1, [])
    # Compare latest closed range with preceding 14 closed ranges (not future ATR).
    ranges = [c.high - c.low for c in m1[-15:-1]]
    average = sum(ranges, Decimal(0)) / len(ranges) if len(ranges) == 14 else None
    extent = (m1[-1].high - m1[-1].low) / average if average else None
    safety = MarketSafetyContext.model_validate(
        dict(
            spread_state="UNAVAILABLE"
            if ratio is None
            else "SPREAD_EXTREME"
            if ratio >= 4
            else "SPREAD_ELEVATED"
            if ratio >= 2
            else "SPREAD_NORMAL",
            volatility_state="UNAVAILABLE"
            if extent is None
            else "EXTREME"
            if extent >= 4
            else "ELEVATED"
            if extent >= 2
            else "NORMAL",
            baseline_spread=baseline,
            current_spread=current_spread,
            quote_as_of=fresh[-1].timestamp if fresh else None,
            source_ids=tuple(fingerprint(q.model_dump(mode="json")) for q in recent + fresh),
        )
    )
    # Both full frozen inputs and derived context participate in identity; clocks never do.
    payload = dict(
        symbol=symbol,
        source=source,
        mode="REPLAY" if replay else "ACTUAL",
        as_of=at,
        config_id=config_id,
        strategy_config_json=config.model_dump_json(),
        analysis_config_json=analysis_config.model_dump_json(),
        tick_size=tick_size,
        frames=tuple(frames),
        key_levels=tuple(sorted({level.id: level for level in levels}.values(), key=lambda v: v.id)),
        sessions=sessions,
        current_session=current,
        market_safety=safety,
        news_json=news.model_dump_json(),
        news_fingerprint=news.fingerprint,
    )
    payload["market_context_id"] = fingerprint(
        {k: v for k, v in payload.items() if k not in ("news_json", "news_fingerprint")}
    )
    return StrategyMarketContext.model_validate(dict(id=fingerprint(payload), **payload))
