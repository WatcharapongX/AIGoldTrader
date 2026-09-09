"""Conservative pivot geometry, causal neckline close confirmation and explicit failure."""

import datetime as dt
from decimal import Decimal

from app.services.analysis.domain import AnalysisSnapshot, SwingPoint
from app.services.market_data.domain import SECONDS, Candle
from app.services.strategy.domain import Pattern, PatternPoint, StrategyConfig, fingerprint


def detect(candles: list[Candle], snapshot: AnalysisSnapshot, config: StrategyConfig) -> tuple[Pattern, ...]:
    if not candles or snapshot.as_of is None:
        return ()
    as_of = snapshot.as_of
    seconds = SECONDS[snapshot.timeframe]
    candles = [c for c in candles if c.is_closed and c.open_time + dt.timedelta(seconds=seconds) <= as_of]
    if not candles:
        return ()
    start = candles[max(0, len(candles) - config.pattern_lookback_bars)].open_time
    # Internal and external duplicate pivots are not independent pattern evidence.
    pivots: list[SwingPoint] = []
    for point in sorted(
        (
            s
            for s in snapshot.swings
            if s.scope == "INTERNAL" and s.swing_time >= start and s.confirmed_at <= snapshot.as_of
        ),
        key=lambda s: (s.swing_time, s.kind, s.id),
    ):
        if pivots and point.kind == pivots[-1].kind:
            if (point.price > pivots[-1].price) == (point.kind == "HIGH"):
                pivots[-1] = point
        else:
            pivots.append(point)
    atr_value = snapshot.indicators.get("ATR")
    atr = atr_value.value if atr_value else None
    if atr is None or atr <= 0:
        return ()
    tolerance = atr * config.tolerance_atr
    results: dict[str, Pattern] = {}

    def emit(kind: str, points: list[SwingPoint], direction: str, neckline: Decimal) -> None:
        if any(
            (b.swing_time - a.swing_time).total_seconds() < seconds * config.pattern_min_separation
            for a, b in zip(points, points[1:], strict=False)
        ):
            return
        high, low = max(s.price for s in points), min(s.price for s in points)
        if high - low <= tolerance * 4:
            return
        detected = max(s.confirmed_at for s in points)
        expiry = detected + dt.timedelta(seconds=config.pattern_lookback_bars * seconds)
        # Confirmation candle must occur after the final pivot has become observable.
        after = [c for c in candles if c.open_time >= detected]
        breakout = next(
            (
                c
                for c in after
                if (c.close > neckline + tolerance if direction == "LONG" else c.close < neckline - tolerance)
            ),
            None,
        )
        confirmed = breakout.open_time + dt.timedelta(seconds=seconds) if breakout else None
        failed = next(
            (
                c
                for c in after
                if (confirmed is None or c.open_time >= confirmed)
                and (c.close < low - tolerance if direction == "LONG" else c.close > high + tolerance)
            ),
            None,
        )
        status = "CONFIRMED" if confirmed else "CANDIDATE"
        if failed:
            status = "INVALIDATED" if confirmed else "FAILED"
        elif as_of >= expiry:
            status = "EXPIRED"
        identity = fingerprint([kind, [s.id for s in points], direction, config.model_dump(mode="json")])
        results[identity] = Pattern.model_validate(
            dict(
                id=identity,
                kind=kind,
                direction=direction,
                status=status,
                points=tuple(
                    PatternPoint(id=s.id, time=s.swing_time, confirmed_at=s.confirmed_at, price=s.price, kind=s.kind)
                    for s in points
                ),
                neckline=neckline,
                upper=high,
                lower=low,
                confirmed_at=confirmed,
                detected_at=detected,
                expires_at=expiry,
                source_ids=tuple(s.id for s in points),
                reason_th="ราคาปิดยืนยันการผ่านแนวคอ"
                if status == "CONFIRMED"
                else "รอราคาปิดยืนยัน ห้ามใช้รูปแบบที่ยังไม่ยืนยันเป็นสัญญาณ"
                if status == "CANDIDATE"
                else "รูปแบบหมดอายุหรือราคาปิดทำลายเงื่อนไข",
            )
        )

    # Sliding templates ensure a newer incomplete pattern never overwrites an earlier confirmed one.
    for end in range(3, len(pivots) + 1):
        three = pivots[end - 3 : end]
        a, b, c = three
        top = a.kind == "HIGH"
        if abs(a.price - c.price) <= tolerance:
            emit("DOUBLE_TOP" if top else "DOUBLE_BOTTOM", three, "SHORT" if top else "LONG", b.price)
        if end < 5:
            continue
        five = pivots[end - 5 : end]
        a, b, c, d, e = five
        top = a.kind == "HIGH"
        neck = min(b.price, d.price) if top else max(b.price, d.price)
        if max(a.price, c.price, e.price) - min(a.price, c.price, e.price) <= tolerance:
            emit("TRIPLE_TOP" if top else "TRIPLE_BOTTOM", five, "SHORT" if top else "LONG", neck)
        if abs(a.price - e.price) <= tolerance and (
            c.price > max(a.price, e.price) + tolerance * 2 if top else c.price < min(a.price, e.price) - tolerance * 2
        ):
            emit("HEAD_AND_SHOULDERS" if top else "INVERSE_HEAD_AND_SHOULDERS", five, "SHORT" if top else "LONG", neck)
        highs = [s for s in five if s.kind == "HIGH"]
        lows = [s for s in five if s.kind == "LOW"]
        dh = highs[-1].price - highs[0].price
        dl = lows[-1].price - lows[0].price
        sh = dh / Decimal(str((highs[-1].swing_time - highs[0].swing_time).total_seconds() / seconds))
        sl = dl / Decimal(str((lows[-1].swing_time - lows[0].swing_time).total_seconds() / seconds))
        if abs(dh) <= tolerance and dl > tolerance * 2:
            emit("ASCENDING_TRIANGLE", five, "LONG", max(s.price for s in highs))
        if abs(dl) <= tolerance and dh < -tolerance * 2:
            emit("DESCENDING_TRIANGLE", five, "SHORT", min(s.price for s in lows))
        if dh < -tolerance and dl > tolerance:
            emit("SYMMETRICAL_TRIANGLE", five, "LONG", highs[-1].price)
            emit("SYMMETRICAL_TRIANGLE", five, "SHORT", lows[-1].price)
        if dh > tolerance and dl > tolerance and sl > sh:
            emit("RISING_WEDGE", five, "SHORT", lows[-1].price)
        if dh < -tolerance and dl < -tolerance and sh < sl:
            emit("FALLING_WEDGE", five, "LONG", highs[-1].price)
        # A flag needs an observable impulse before the channel; a generic diagonal range is not a flag.
        prior = [bar for bar in candles if bar.open_time < a.swing_time][-8:]
        pole = prior[-1].close - prior[0].open if len(prior) == 8 else Decimal(0)
        parallel = abs(sh - sl) <= tolerance / 2
        if parallel and dh < -tolerance and dl < -tolerance and pole > atr * 3:
            emit("BULLISH_FLAG", five, "LONG", highs[-1].price)
        if parallel and dh > tolerance and dl > tolerance and pole < -atr * 3:
            emit("BEARISH_FLAG", five, "SHORT", lows[-1].price)
    return tuple(sorted(results.values(), key=lambda p: (p.detected_at, p.id))[-64:])
