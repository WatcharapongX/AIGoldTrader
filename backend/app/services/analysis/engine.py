"""Causal, deterministic closed-candle state machine. No provider, clock or execution I/O."""

import datetime as dt
import hashlib
from collections import deque
from decimal import Decimal

from app.services.analysis.domain import (
    ALGORITHM_VERSION,
    AnalysisConfig,
    AnalysisSnapshot,
    DealingRange,
    History,
    LiquidityLevel,
    ModuleStatus,
    SessionRange,
    StructureEvent,
    SwingPoint,
    Zone,
)
from app.services.analysis.indicators import Indicators, rounded
from app.services.market_data.domain import SECONDS, Candle, Timeframe, bucket


class AnalysisInputError(ValueError):
    pass


class AnalysisEngine:
    def __init__(self, symbol, timeframe, source, config=None):
        self.symbol, self.timeframe, self.source = symbol, Timeframe(timeframe), source
        self.config = config or AnalysisConfig()
        self.config_id = hashlib.sha256(self.config.model_dump_json().encode()).hexdigest()[:16]
        self.tolerance = self.config.tick_size * self.config.equal_ticks
        self.bars: deque[Candle] = deque(maxlen=max(150, self.config.ob_lookback + 1))
        self.count = 0
        self.window_start = None
        self.input_digest = hashlib.sha256()
        self.swings: list[SwingPoint] = []
        self.events: list[StructureEvent] = []
        self.levels: list[LiquidityLevel] = []
        self.zones: list[Zone] = []
        self.sessions: list[SessionRange] = []
        self.groups: dict = {}
        self.latest: dict = {scope: {"HIGH": None, "LOW": None} for scope in ("INTERNAL", "EXTERNAL")}
        self.state = {"INTERNAL": "UNKNOWN", "EXTERNAL": "UNKNOWN"}
        self.broken: dict = {}
        self.indicators = Indicators(self.config)

    def identity(self, kind, *parts):
        text = "|".join(
            map(str, (ALGORITHM_VERSION, self.config_id, self.symbol, self.timeframe.value, self.source, kind, *parts))
        )
        return kind + "-" + hashlib.sha256(text.encode()).hexdigest()[:20]

    def end(self, candle):
        return candle.open_time + dt.timedelta(seconds=SECONDS[self.timeframe])

    def displacement(self, candle, direction):
        atr = self.indicators.atr  # Previous closed bar's ATR, never includes the candidate's range.
        extent = candle.high - candle.low
        if atr is None or atr <= 0 or extent <= 0:
            return False
        body = candle.close - candle.open
        location = (
            (candle.close - candle.low) / extent if direction == "BULLISH" else (candle.high - candle.close) / extent
        )
        return (body > 0 if direction == "BULLISH" else body < 0) and (
            abs(body) >= atr * self.config.displacement_atr and location >= self.config.displacement_close_fraction
        )

    def _event(self, kind, scope, direction, swing, candle, displaced, parent=None):
        event = StructureEvent(
            id=self.identity(kind, scope, candle.open_time, swing.id),
            scope=scope,
            kind=kind,
            direction=direction,
            price=swing.price,
            swing_id=swing.id,
            swing_time=swing.swing_time,
            occurred_at=candle.open_time,
            confirmed_at=self.end(candle),
            displacement=displaced,
            parent_event_id=parent,
        )
        self.events.append(event)
        if displaced and kind in ("BOS", "MSS"):
            for origin in reversed(list(self.bars)[-self.config.ob_lookback :]):
                opposing = origin.close < origin.open if direction == "BULLISH" else origin.close > origin.open
                if opposing and origin.high > origin.low:
                    zone_id = self.identity("OB", direction, origin.open_time)
                    if not any(z.id == zone_id for z in self.zones):
                        self.zones.append(
                            Zone(
                                id=zone_id,
                                kind="OB",
                                direction=direction,
                                lower_bound=origin.low,
                                upper_bound=origin.high,
                                occurred_at=origin.open_time,
                                confirmed_at=self.end(candle),
                                status="ACTIVE",
                                source_event_id=event.id,
                            )
                        )
                    break
        return event

    def _breaks(self, candle):
        for scope in self.latest:
            for kind, direction in (("HIGH", "BULLISH"), ("LOW", "BEARISH")):
                swing = self.latest[scope][kind]
                if swing is None or self.broken.get((scope, kind)) == swing.id:
                    continue
                crossed = (
                    candle.close > swing.price + self.tolerance
                    if kind == "HIGH"
                    else candle.close < swing.price - self.tolerance
                )
                if not crossed:
                    continue
                self.broken[(scope, kind)] = swing.id
                old = self.state[scope]
                displaced = self.displacement(candle, direction)
                if old == direction:
                    self._event("BOS", scope, direction, swing, candle, displaced)
                elif old in ("BULLISH", "BEARISH"):
                    warning = self._event("CHOCH", scope, direction, swing, candle, displaced)
                    self.state[scope] = "NEUTRAL"
                    if displaced:
                        self._event("MSS", scope, direction, swing, candle, True, warning.id)
                        self.state[scope] = direction
                # UNKNOWN/NEUTRAL breaks establish context without inventing continuation evidence.
                else:
                    self.state[scope] = direction

    def _swing(self, scope, kind, pivot, confirmed_at):
        price = pivot.high if kind == "HIGH" else pivot.low
        previous = self.latest[scope][kind]
        if previous is None:
            label = "SH" if kind == "HIGH" else "SL"
        elif abs(price - previous.price) <= self.tolerance:
            label = "EQH" if kind == "HIGH" else "EQL"
        elif kind == "HIGH":
            label = "HH" if price > previous.price else "LH"
        else:
            label = "HL" if price > previous.price else "LL"
        swing = SwingPoint(
            id=self.identity("SWING", scope, kind, pivot.open_time),
            scope=scope,
            kind=kind,
            label=label,
            price=price,
            swing_time=pivot.open_time,
            confirmed_at=confirmed_at,
        )
        self.swings.append(swing)
        self.latest[scope][kind] = swing
        if scope == "EXTERNAL":
            self.levels.append(
                LiquidityLevel(
                    id=self.identity("LIQUIDITY", swing.id),
                    kind="BSL" if kind == "HIGH" else "SSL",
                    side=kind,
                    price=price,
                    created_at=pivot.open_time,
                    confirmed_at=confirmed_at,
                    source_ids=[swing.id],
                )
            )
            if previous and label in ("EQH", "EQL"):
                self.levels.append(
                    LiquidityLevel(
                        id=self.identity(label, previous.id, swing.id),
                        kind=label,
                        side=kind,
                        price=rounded((price + previous.price) / 2),
                        created_at=previous.swing_time,
                        confirmed_at=confirmed_at,
                        source_ids=[previous.id, swing.id],
                    )
                )
        high, low = self.latest[scope]["HIGH"], self.latest[scope]["LOW"]
        if high and low and self.broken.get((scope, "HIGH")) != high.id and self.broken.get((scope, "LOW")) != low.id:
            if high.label == "HH" and low.label == "HL":
                self.state[scope] = "BULLISH"
            elif high.label == "LH" and low.label == "LL":
                self.state[scope] = "BEARISH"
            elif high.label in ("EQH", "LH", "HH") and low.label in ("EQL", "HL", "LL"):
                # Keep an established break state until another structural event; initial mixed pairs are neutral.
                if self.state[scope] == "UNKNOWN":
                    self.state[scope] = "NEUTRAL"

    def _pivots(self, candle):
        values = list(self.bars)
        for scope, left, right in (
            ("INTERNAL", self.config.internal_left, self.config.internal_right),
            ("EXTERNAL", self.config.external_left, self.config.external_right),
        ):
            width = left + right + 1
            if len(values) < width:
                continue
            window = values[-width:]
            pivot = window[left]
            peers = window[:left] + window[left + 1 :]
            # Strict extrema: tied plateaus yield no pivot, preventing arbitrary tie selection.
            if all(pivot.high > v.high for v in peers):
                self._swing(scope, "HIGH", pivot, self.end(candle))
            if all(pivot.low < v.low for v in peers):
                self._swing(scope, "LOW", pivot, self.end(candle))

    def _liquidity(self, candle):
        for index, level in enumerate(self.levels):
            if level.status != "ACTIVE" or level.confirmed_at > candle.open_time:
                continue
            high = level.side == "HIGH"
            crossed = candle.high > level.price + self.tolerance if high else candle.low < level.price - self.tolerance
            inside = candle.close <= level.price if high else candle.close >= level.price
            broken = (
                candle.close > level.price + self.tolerance if high else candle.close < level.price - self.tolerance
            )
            if crossed and inside:
                self.levels[index] = level.model_copy(
                    update={
                        "status": "SWEPT",
                        "swept_at": self.end(candle),
                        "sweep_price": candle.high if high else candle.low,
                        "ended_at": self.end(candle),
                    }
                )
            elif broken:
                self.levels[index] = level.model_copy(update={"status": "INVALIDATED", "ended_at": self.end(candle)})

    def _zones(self, candle):
        new = []
        for index, zone in enumerate(self.zones):
            if zone.status in ("FILLED", "INVALIDATED") or zone.confirmed_at > candle.open_time:
                continue
            bullish = zone.direction == "BULLISH"
            invalid = (
                candle.close < zone.lower_bound - self.tolerance
                if bullish
                else candle.close > zone.upper_bound + self.tolerance
            )
            touched = candle.low <= zone.upper_bound and candle.high >= zone.lower_bound
            if invalid:
                self.zones[index] = zone.model_copy(update={"status": "INVALIDATED", "ended_at": self.end(candle)})
                if zone.kind in ("FVG", "OB"):
                    kind = "IFVG" if zone.kind == "FVG" else "BREAKER"
                    new.append(
                        Zone(
                            id=self.identity(kind, zone.id, candle.open_time),
                            kind=kind,
                            direction="BEARISH" if bullish else "BULLISH",
                            lower_bound=zone.lower_bound,
                            upper_bound=zone.upper_bound,
                            occurred_at=candle.open_time,
                            confirmed_at=self.end(candle),
                            status="OPEN" if kind == "IFVG" else "ACTIVE",
                            source_event_id=zone.id,
                        )
                    )
            elif touched:
                if zone.kind in ("FVG", "IFVG"):
                    fraction = (zone.upper_bound - candle.low) if bullish else (candle.high - zone.lower_bound)
                    fraction = min(
                        Decimal(1), max(zone.fill_fraction, fraction / (zone.upper_bound - zone.lower_bound))
                    )
                    self.zones[index] = zone.model_copy(
                        update={
                            "status": "FILLED" if fraction >= 1 else "PARTIALLY_FILLED",
                            "fill_fraction": rounded(fraction),
                            "ended_at": self.end(candle) if fraction >= 1 else None,
                        }
                    )
                else:
                    self.zones[index] = zone.model_copy(update={"status": "MITIGATED"})
        self.zones.extend(new)

    def _fvg(self, candle):
        if len(self.bars) < 3:
            return
        first = self.bars[-3]
        # Three adjacent canonical bars; never interpret weekend/data gaps as imbalances.
        if self.end(first) != self.bars[-2].open_time or self.end(self.bars[-2]) != candle.open_time:
            return
        gap = self.config.tick_size * self.config.minimum_gap_ticks
        direction = None
        if candle.low - first.high >= gap:
            direction, low, high = "BULLISH", first.high, candle.low
        elif first.low - candle.high >= gap:
            direction, low, high = "BEARISH", candle.high, first.low
        if direction:
            self.zones.append(
                Zone(
                    id=self.identity("FVG", candle.open_time),
                    kind="FVG",
                    direction=direction,
                    lower_bound=low,
                    upper_bound=high,
                    occurred_at=first.open_time,
                    confirmed_at=self.end(candle),
                    status="OPEN",
                )
            )

    def _periods(self, candle):
        day = bucket(candle.open_time, Timeframe.D1)
        week = bucket(candle.open_time, Timeframe.W1)
        windows = [("PD", day, day + dt.timedelta(days=1)), ("PW", week, week + dt.timedelta(days=7))]
        windows.extend(
            (name, day + dt.timedelta(hours=hours[0]), day + dt.timedelta(hours=hours[1]))
            for name, hours in self.config.session_hours.items()
        )
        # A coarse candle cannot supply a partial session's extrema. Omit incompatible windows.
        windows = [
            (name, start, stop)
            for name, start, stop in windows
            if bucket(start, self.timeframe) == start
            and int((stop - start).total_seconds()) % SECONDS[self.timeframe] == 0
        ]
        end = self.end(candle)
        # Complete observed periods when their boundary has passed, including scheduled market gaps.
        for key, group in list(self.groups.items()):
            name, start, stop = key
            if end < stop:
                continue
            # Include this bar before finalization if it belongs wholly inside the period.
            if start <= candle.open_time and end <= stop:
                group = (group[0], max(group[1], candle.high), min(group[2], candle.low))
            if group[0] == start:
                session = name not in ("PD", "PW")
                if session:
                    self.sessions.append(
                        SessionRange(name=name, start=start, end=stop, high=group[1], low=group[2], confirmed_at=end)
                    )
                for side, price in (("HIGH", group[1]), ("LOW", group[2])):
                    kind = "SESSION_" + side if session else name + ("H" if side == "HIGH" else "L")
                    self.levels.append(
                        LiquidityLevel(
                            id=self.identity(kind, name, start),
                            kind=kind,
                            side=side,
                            price=price,
                            created_at=start,
                            confirmed_at=end,
                            source_ids=[name + ":" + start.isoformat()],
                        )
                    )
            del self.groups[key]
        for name, start, stop in windows:
            if candle.open_time < start or end > stop:
                continue
            key = (name, start, stop)
            # A one-bar period (D1/W1) is confirmed directly on its own close.
            if candle.open_time == start and end == stop:
                for side, price in (("HIGH", candle.high), ("LOW", candle.low)):
                    kind = name + ("H" if side == "HIGH" else "L")
                    if name in ("PD", "PW"):
                        self.levels.append(
                            LiquidityLevel(
                                id=self.identity(kind, name, start),
                                kind=kind,
                                side=side,
                                price=price,
                                created_at=start,
                                confirmed_at=end,
                                source_ids=[name],
                            )
                        )
                continue
            if end == stop:
                continue
            group = self.groups.get(key, (candle.open_time, candle.high, candle.low))
            self.groups[key] = (group[0], max(group[1], candle.high), min(group[2], candle.low))
        self.sessions = self.sessions[-32:]

    def feed(self, value: Candle):
        try:
            candle = Candle.model_validate(value.model_dump() if isinstance(value, Candle) else value)
        except (ValueError, TypeError):
            raise AnalysisInputError("Invalid canonical candle") from None
        if (candle.symbol, candle.timeframe, candle.source) != (self.symbol, self.timeframe, self.source):
            raise AnalysisInputError("Mixed symbol, timeframe or source")
        if not candle.is_closed:
            raise AnalysisInputError("Confirmed engine accepts closed candles only")
        if self.bars and candle.open_time <= self.bars[-1].open_time:
            raise AnalysisInputError("Duplicate or reversed closed candles")
        if self.window_start is None:
            self.window_start = candle.open_time
        self.input_digest.update(candle.model_dump_json().encode())
        self._liquidity(candle)
        self._zones(candle)
        self._breaks(candle)
        self.bars.append(candle)
        self.count += 1
        self._pivots(candle)
        self._fvg(candle)
        self._periods(candle)
        self.indicators.feed(candle)
        cap = self.config.max_objects
        self.swings, self.events = self.swings[-cap:], self.events[-cap:]
        self.levels, self.zones = self.levels[-cap:], self.zones[-cap:]

    def _range(self):
        for scope in ("EXTERNAL", "INTERNAL"):
            pivots = [s for s in self.swings if s.scope == scope]
            if len(pivots) < 2:
                continue
            last = pivots[-1]
            previous = next((s for s in reversed(pivots[:-1]) if s.kind != last.kind), None)
            if previous is None or previous.swing_time >= last.swing_time:
                continue
            low = last.price if last.kind == "LOW" else previous.price
            high = last.price if last.kind == "HIGH" else previous.price
            if high - low <= self.tolerance:
                continue
            eq = rounded((high + low) / 2)
            close = self.bars[-1].close
            direction = "BULLISH" if last.kind == "HIGH" else "BEARISH"
            r62, r79 = (
                (high - (high - low) * v for v in (Decimal(".62"), Decimal(".79")))
                if direction == "BULLISH"
                else (low + (high - low) * v for v in (Decimal(".62"), Decimal(".79")))
            )
            return DealingRange(
                lower_bound=low,
                upper_bound=high,
                equilibrium=eq,
                origin_time=previous.swing_time,
                confirmed_at=last.confirmed_at,
                direction=direction,
                swing_ids=[previous.id, last.id],
                location="EQUILIBRIUM"
                if abs(close - eq) <= self.tolerance
                else "PREMIUM"
                if close > eq
                else "DISCOUNT",
                retracement_62=rounded(r62),
                retracement_79=rounded(r79),
            )
        return None

    def snapshot(self, requested=300, returned=None):
        returned = self.count if returned is None else returned
        history = History(
            requested=requested,
            returned=returned,
            closed=self.count,
            status="EMPTY" if returned == 0 else "PARTIAL" if returned < requested else "COMPLETE",
        )
        c = self.config
        minimums = {
            "internal_structure": c.internal_left + c.internal_right + 1,
            "external_structure": c.external_left + c.external_right + 1,
            "liquidity": c.external_left + c.external_right + 1,
            "fvg": 3,
            "order_blocks": max(c.atr_period + 2, c.internal_left + c.internal_right + 2),
            "indicators": max(c.atr_period * 2, c.average_period),
            "sessions": min(
                (
                    int((stop - start) * 3600 / SECONDS[self.timeframe])
                    for start, stop in c.session_hours.values()
                    if (stop - start) * 3600 % SECONDS[self.timeframe] == 0
                    and start * 3600 % SECONDS[self.timeframe] == 0
                ),
                default=1,
            ),
            "regime": max(c.atr_period * 2, c.average_period),
        }
        available = {
            "internal_structure": any(s.scope == "INTERNAL" for s in self.swings),
            "external_structure": any(s.scope == "EXTERNAL" for s in self.swings),
            "liquidity": bool(self.levels),
            "fvg": any(z.kind in ("FVG", "IFVG") for z in self.zones),
            "order_blocks": any(z.kind in ("OB", "BREAKER") for z in self.zones),
            "sessions": bool(self.sessions),
            "indicators": True,
            "regime": True,
        }
        modules = {}
        for name, minimum in minimums.items():
            status = (
                "INSUFFICIENT_DATA"
                if self.count < minimum
                else "NO_STRUCTURE"
                if not available[name]
                else "PARTIAL_HISTORY"
                if history.status == "PARTIAL"
                else "READY"
            )
            modules[name] = ModuleStatus(
                status=status,
                minimum_bars_required=minimum,
                available_bars=self.count,
                reason="Closed bars below warm-up"
                if status == "INSUFFICIENT_DATA"
                else "No confirmed feature under these rules"
                if status == "NO_STRUCTURE"
                else "Available closed history analyzed; no fabricated backfill",
            )
        indicators = self.indicators.values()
        state = self.state["EXTERNAL"] if self.state["EXTERNAL"] != "UNKNOWN" else self.state["INTERNAL"]
        regime = "UNKNOWN"
        if self.bars and modules["regime"].status != "INSUFFICIENT_DATA":
            ratio = self.indicators.atr / self.bars[-1].close
            if ratio >= c.high_volatility_ratio:
                regime = "HIGH_VOLATILITY"
            elif ratio <= c.low_volatility_ratio:
                regime = "LOW_VOLATILITY"
            elif (
                self.events
                and self.events[-1].kind == "BOS"
                and self.events[-1].confirmed_at == self.end(self.bars[-1])
            ):
                regime = "BREAKOUT"
            elif state in ("BULLISH", "BEARISH") and self.indicators.adx >= c.adx_trend_threshold:
                against = (
                    self.bars[-1].close < self.indicators.ema
                    if state == "BULLISH"
                    else self.bars[-1].close > self.indicators.ema
                )
                regime = "PULLBACK" if against else "TRENDING_UP" if state == "BULLISH" else "TRENDING_DOWN"
            elif state != "UNKNOWN":
                regime = "RANGING"
        as_of = self.end(self.bars[-1]) if self.bars else None
        return AnalysisSnapshot(
            symbol=self.symbol,
            timeframe=self.timeframe,
            source=self.source,
            algorithm_version=ALGORITHM_VERSION,
            config_id=self.config_id,
            input_id=self.input_digest.hexdigest()[:24],
            window_start=self.window_start,
            history=history,
            as_of=as_of,
            modules=modules,
            internal_state=self.state["INTERNAL"],
            external_state=self.state["EXTERNAL"],
            swings=self.swings,
            events=self.events,
            liquidity=self.levels,
            zones=self.zones,
            dealing_range=self._range(),
            indicators=indicators,
            sessions=self.sessions,
            current_sessions=[]
            if as_of is None
            else [name for name, (start, stop) in c.session_hours.items() if start <= as_of.hour < stop],
            regime=regime,
            confluence_counts={
                direction: sum(z.direction == direction and z.status in ("ACTIVE", "OPEN") for z in self.zones)
                for direction in ("BULLISH", "BEARISH")
            },
        )


def analyze(candles, symbol, timeframe, source, requested=300, config=None):
    if len(candles) > 1000 or len(candles) > requested or not 1 <= requested <= 1000:
        raise AnalysisInputError("Analysis input exceeds bounded window")
    engine = AnalysisEngine(symbol, timeframe, source, config)
    previous = None
    forming = False
    for value in candles:
        try:
            candle = Candle.model_validate(value.model_dump() if isinstance(value, Candle) else value)
        except (ValueError, TypeError):
            raise AnalysisInputError("Invalid canonical candle") from None
        if (candle.symbol, candle.timeframe, candle.source) != (symbol, Timeframe(timeframe), source):
            raise AnalysisInputError("Mixed symbol, timeframe or source")
        if previous is not None and candle.open_time <= previous:
            raise AnalysisInputError("Duplicate or reversed timestamps")
        if forming:
            raise AnalysisInputError("Only the final candle may be forming")
        previous = candle.open_time
        forming = not candle.is_closed
        if candle.is_closed:
            engine.feed(candle)
    return engine.snapshot(requested=requested, returned=len(candles))
