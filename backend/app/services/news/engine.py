"""Point-in-time structured news context; no clock reads, provider I/O or execution."""

import datetime as dt
import hashlib
import json
from decimal import Decimal

from app.services.analysis.domain import (
    AnalysisConfig,
    AnalysisSnapshot,
    LiquidityLevel,
    StructureEvent,
    SwingPoint,
    Zone,
)
from app.services.analysis.indicators import Indicators, rounded
from app.services.market_data.domain import SECONDS, Candle, Timeframe
from app.services.news.domain import (
    NEWS_VERSION,
    EconomicEvent,
    NewsConfig,
    NewsStrategyContext,
    ObservedQuote,
    ReactionWindow,
    ReleaseGroup,
    StructureContext,
    Surprise,
)


def relevance_score(event: EconomicEvent, config: NewsConfig) -> int:
    return min(config.relevance.get(event.currency, 0), config.impact_relevance.get(event.impact, 0))


def latest_known(events: list[EconomicEvent], as_of: dt.datetime) -> list[EconomicEvent]:
    if as_of.tzinfo is None:
        raise ValueError("UTC-aware cutoff required")
    selected: dict[str, EconomicEvent] = {}
    for raw in events:
        event = EconomicEvent.model_validate(raw.model_dump())
        if event.available_at > as_of:
            continue
        if event.id not in selected or event.revision_version > selected[event.id].revision_version:
            selected[event.id] = event
        elif event.revision_version == selected[event.id].revision_version and event != selected[event.id]:
            raise ValueError("Conflicting event revision")
    return sorted(selected.values(), key=lambda event: (event.scheduled_at, event.id))


def surprise(event: EconomicEvent, config: NewsConfig) -> Surprise:
    actual, forecast = event.actual, event.forecast
    revision = (
        None
        if event.revised_previous is None or event.previous is None
        else event.revised_previous
        - (event.previous_before_revision if event.previous_before_revision is not None else event.previous)
    )
    missing = actual is None or forecast is None or event.unit == "NON_NUMERIC"
    raw = None if actual is None or forecast is None or event.unit == "NON_NUMERIC" else actual - forecast
    relative = None if raw is None or forecast is None or forecast == 0 else raw / abs(forecast)
    direction = "UNAVAILABLE" if raw is None else "ABOVE" if raw > 0 else "BELOW" if raw < 0 else "INLINE"
    rule = config.direction_overrides.get(event.event_code, event.direction_rule)
    positive = raw is not None and (raw > 0 if rule == "HIGHER_IS_POSITIVE" else raw < 0)
    usd = (
        "UNKNOWN"
        if raw is None or rule == "CONTEXT_DEPENDENT"
        else "NEUTRAL"
        if raw == 0
        else "POSITIVE"
        if positive
        else "NEGATIVE"
    )
    magnitude = (
        "UNAVAILABLE"
        if raw is None or relative is None and raw != 0
        else "ZERO"
        if raw == 0
        else "LARGE"
        if relative is not None and abs(relative) >= config.relative_large
        else "SMALL"
    )
    return Surprise.model_validate(
        {
            "event_id": event.id,
            "raw": rounded(raw),
            "relative": rounded(relative),
            "direction": direction,
            "magnitude": magnitude,
            "usd_direction": usd,
            "revision_delta": rounded(revision),
            "reason_code": "NON_NUMERIC_EVENT"
            if event.unit == "NON_NUMERIC"
            else "MISSING_RESULT"
            if missing
            else "CONTEXT_DEPENDENT"
            if rule == "CONTEXT_DEPENDENT"
            else "FORECAST_ZERO"
            if forecast == 0
            else "NUMERIC_SURPRISE",
        }
    )


def release_group(events: list[EconomicEvent], config: NewsConfig) -> ReleaseGroup:
    values = [surprise(event, config) for event in events]
    positive = negative = Decimal(0)
    neutral = unknown = 0
    for event, value in zip(events, values, strict=True):
        weight = Decimal(
            config.weights.get(
                event.event_code,
                Decimal(".25")
                if event.event_code in ("CPI_MOM", "CPI_YOY", "CORE_CPI_MOM", "CORE_CPI_YOY")
                else Decimal(1),
            )
        )
        if value.usd_direction == "POSITIVE":
            positive += weight
        elif value.usd_direction == "NEGATIVE":
            negative += weight
        elif value.usd_direction == "NEUTRAL":
            neutral += 1
        else:
            unknown += 1
        rule = config.direction_overrides.get(event.event_code, event.direction_rule)
        if value.revision_delta and rule != "CONTEXT_DEPENDENT":
            revision_positive = value.revision_delta > 0 if rule == "HIGHER_IS_POSITIVE" else value.revision_delta < 0
            if revision_positive:
                positive += weight * config.revision_weight
            else:
                negative += weight * config.revision_weight
    codes = {event.event_code for event in events}
    complete = all(
        event.actual is not None and event.forecast is not None or event.unit == "NON_NUMERIC" for event in events
    ) and ("NFP" not in codes or {"NFP", "UNEMPLOYMENT", "WAGES"} <= codes)
    if codes & {"CPI_MOM", "CPI_YOY", "CORE_CPI_MOM", "CORE_CPI_YOY"}:
        complete = complete and {"CPI_MOM", "CPI_YOY", "CORE_CPI_MOM", "CORE_CPI_YOY"} <= codes
    if any(e.source == "forex_factory" for e in events) and "NFP" in codes:
        complete = complete and all(e.revised_previous is not None for e in events if e.event_code == "NFP")
    complete = complete and not any(e.field_conflicts for e in events)
    if positive and negative:
        alignment, bias = "CONFLICTING", "CONFLICTING"
    elif positive or negative:
        alignment = "ALL_ALIGNED" if complete and not unknown and not neutral else "MOSTLY_ALIGNED"
        strong = alignment == "ALL_ALIGNED" and len(events) >= 2
        bias = (
            ("USD_STRONG_POSITIVE" if strong else "USD_POSITIVE")
            if positive
            else ("USD_STRONG_NEGATIVE" if strong else "USD_NEGATIVE")
        )
    else:
        alignment, bias = ("MIXED", "USD_NEUTRAL") if neutral else ("UNAVAILABLE", "UNKNOWN")
    return ReleaseGroup.model_validate(
        {
            "group_id": events[0].group_id,
            "event_ids": [event.id for event in events],
            "alignment": alignment,
            "bias": bias,
            "score": positive - negative,
            "completeness": "COMPLETE" if complete else "PARTIAL",
            "surprises": values,
        }
    )


def event_regime(event: EconomicEvent, as_of: dt.datetime, config: NewsConfig) -> str:
    if event.status == "CANCELLED" or event.impact not in ("HIGH", "MEDIUM"):
        return "NORMAL"
    seconds = (as_of - event.scheduled_at).total_seconds()
    if seconds >= config.normalized_seconds and event.status != "DELAYED":
        return "NORMAL"
    if seconds < -config.pre_seconds[event.impact]:
        return "NORMAL"
    if seconds < -config.lock_seconds[event.impact]:
        return "PRE_NEWS"
    if seconds < 0 or event.status == "DELAYED":
        return "NEWS_LOCK"
    if seconds < config.release_seconds:
        return "RELEASE"
    if event.status not in ("RELEASED", "REVISED"):
        return "NEWS_LOCK"
    if seconds < config.observation_seconds:
        return "POST_NEWS_VOLATILITY"
    if seconds < config.confirmation_seconds:
        return "POST_NEWS_CONFIRMATION"
    if seconds < config.normalized_seconds:
        return "NORMALIZED"
    return "NORMAL"


def structure_context(
    snapshot: AnalysisSnapshot | None, at: dt.datetime | None, as_of: dt.datetime, bias: str
) -> StructureContext:
    if snapshot is None or snapshot.as_of is None or snapshot.as_of > as_of:
        return StructureContext.model_validate(
            {
                "status": "STRUCTURE_UNAVAILABLE",
                "upstream_input_id": None,
                "upstream_config_id": None,
                "upstream_algorithm_version": None,
                "upstream_as_of": None,
                "upstream_window_start": None,
                "references": {},
            }
        )
    references: dict[str, str] = {}
    if at:
        for event in snapshot.events:
            if at <= event.confirmed_at <= as_of:
                references[event.id] = "CONFIRMED_" + event.kind
        for level in snapshot.liquidity:
            if level.swept_at and at <= level.swept_at <= as_of:
                references[level.id] = level.status
        for zone in snapshot.zones:
            if at <= zone.confirmed_at <= as_of:
                references[zone.id] = zone.status
    events = [event for event in snapshot.events if at and at <= event.confirmed_at <= as_of]
    state = "WAITING"
    if events and bias not in ("UNKNOWN", "USD_NEUTRAL", "CONFLICTING"):
        expected = "BEARISH" if "POSITIVE" in bias else "BULLISH"
        state = "ALIGNED" if events[-1].direction == expected else "CONFLICTING"
    elif events and bias == "CONFLICTING":
        state = "CONFLICTING"
    return StructureContext.model_validate(
        {
            "status": state,
            "upstream_input_id": snapshot.input_id,
            "upstream_config_id": snapshot.config_id,
            "upstream_algorithm_version": snapshot.algorithm_version,
            "upstream_as_of": snapshot.as_of,
            "upstream_window_start": snapshot.window_start,
            "references": references,
        }
    )


def reaction(
    at: dt.datetime, as_of: dt.datetime, candles: list[Candle], config: NewsConfig, structure: AnalysisSnapshot | None
) -> list[ReactionWindow]:
    closed = [c for c in candles if c.is_closed and c.open_time + dt.timedelta(seconds=SECONDS[c.timeframe]) <= as_of]
    before = [c for c in closed if c.open_time + dt.timedelta(seconds=SECONDS[c.timeframe]) <= at]
    indicators = Indicators(AnalysisConfig())
    for candle in before:
        indicators.feed(candle)
    atr = indicators.atr
    result = []
    for seconds in config.reaction_seconds:
        cutoff = at + dt.timedelta(seconds=seconds)
        item = ReactionWindow(
            seconds=seconds, cutoff=cutoff, status="WAITING" if cutoff > as_of else "REACTION_UNAVAILABLE"
        )
        bars = [
            c
            for c in closed
            if c.open_time >= at and c.open_time + dt.timedelta(seconds=SECONDS[c.timeframe]) <= cutoff
        ]
        # Exact whole M1 coverage; sub-minute or missing/straddling bars are never interpolated.
        ready = (
            cutoff <= as_of
            and before
            and bars
            and seconds % 60 == 0
            and before[-1].open_time + dt.timedelta(minutes=1) == at
            and bars[0].open_time == at
            and len(bars) == seconds // 60
            and all(b.open_time - a.open_time == dt.timedelta(minutes=1) for a, b in zip(bars, bars[1:], strict=False))
        )
        if ready:
            base, after = before[-1].close, bars[-1].close
            high, low = max(c.high for c in bars), min(c.low for c in bars)
            move = None if not atr else (after - base) / atr
            expansion = None if not atr else (high - low) / atr
            classification = "UNCONFIRMED"
            observed_events = (
                [] if structure is None else [e for e in structure.events if at <= e.confirmed_at <= cutoff]
            )
            sweeps = (
                []
                if structure is None
                else [level for level in structure.liquidity if level.swept_at and at <= level.swept_at <= cutoff]
            )
            if atr and move is not None:
                if high - base >= atr * config.whipsaw_atr and base - low >= atr * config.whipsaw_atr:
                    classification = "WHIPSAW"
                elif any(
                    level.side == "HIGH" and after < base or level.side == "LOW" and after > base for level in sweeps
                ):
                    classification = "LIQUIDITY_SWEEP_REVERSAL"
                elif any(
                    e.kind == "BOS"
                    and (e.direction == "BULLISH" and after < base or e.direction == "BEARISH" and after > base)
                    for e in observed_events
                ):
                    classification = "FAILED_BREAKOUT"
                elif observed_events and any(e.kind == "BOS" for e in observed_events):
                    classification = "BREAKOUT"
                elif abs(move) >= config.directional_atr:
                    classification = "STRONG_DIRECTIONAL"
                elif abs(move) <= config.muted_atr:
                    classification = "MUTED"
            average = sum((c.volume for c in before[-20:]), Decimal(0)) / min(20, len(before))
            item = item.model_copy(
                update={
                    "status": "READY",
                    "price_before": base,
                    "price_after": after,
                    "return_percent": rounded((after - base) / base * 100),
                    "move_atr": rounded(move),
                    "range_atr": rounded(expansion),
                    "tick_activity_ratio": None
                    if not average
                    else rounded(sum((c.volume for c in bars), Decimal(0)) / len(bars) / average),
                    "classification": classification,
                }
            )
        result.append(item)
    return result


def build_context(
    events: list[EconomicEvent],
    as_of: dt.datetime,
    *,
    source: str,
    mode: str,
    config: NewsConfig,
    candles: list[Candle],
    quotes: list[ObservedQuote],
    structure: AnalysisSnapshot | None,
    calendar_available: bool = True,
    view: str = "current",
    market_source: str | None = None,
) -> NewsStrategyContext:
    as_of = as_of.astimezone(dt.UTC) if as_of.tzinfo else as_of
    if as_of.tzinfo is None or len(events) > 2000 or len(candles) > 1000 or len(quotes) > 3600:
        raise ValueError("Invalid or unbounded context inputs")
    if structure is not None:
        if structure.as_of is None or structure.as_of > as_of:
            structure = None
        else:
            structure = AnalysisSnapshot.model_validate(
                {k: v for k, v in structure.model_dump().items() if k in AnalysisSnapshot.model_fields}
            )
    if structure is not None:
        objects: list[SwingPoint | StructureEvent | Zone | LiquidityLevel] = [
            *structure.swings,
            *structure.events,
            *structure.zones,
            *structure.liquidity,
        ]
        if any(
            obj.confirmed_at > as_of or (ended_at := getattr(obj, "ended_at", None)) is not None and ended_at > as_of
            for obj in objects
        ):
            raise ValueError("Future lifecycle in point-in-time structure input")
    selected = latest_known(events, as_of)
    selected = [event for event in selected if event.source == source]
    if any(event.source_mode != mode for event in selected):
        raise ValueError("Mixed news provider modes")
    if view == "none":
        selected = []
    if len(selected) > 200:
        raise ValueError("Calendar context exceeds event bound")
    canonical = [Candle.model_validate(c.model_dump()) for c in candles]
    canonical = [c for c in canonical if c.is_closed and c.open_time + dt.timedelta(minutes=1) <= as_of]
    if any(c.symbol != "XAUUSD" or c.timeframe != Timeframe.M1 or c.source != market_source for c in canonical):
        raise ValueError("Mixed reaction input identity")
    if any(a.open_time >= b.open_time for a, b in zip(canonical, canonical[1:], strict=False)):
        raise ValueError("Reaction input must be ordered")
    quotes = [ObservedQuote.model_validate(q.model_dump()) for q in quotes]
    if any(a.timestamp >= b.timestamp for a, b in zip(quotes, quotes[1:], strict=False)):
        raise ValueError("Quotes must have unique ordered timestamps")
    observed = [q for q in quotes if q.timestamp <= as_of and q.observed_at <= as_of and q.source == market_source]
    relevant = [
        event
        for event in selected
        if relevance_score(event, config) >= 2
        and event.status != "CANCELLED"
        and (event.impact == "HIGH" or event.source != "forex_factory" or event.event_code in config.medium_event_codes)
    ]
    priorities = {
        "NORMAL": 0,
        "NORMALIZED": 1,
        "POST_NEWS_CONFIRMATION": 2,
        "PRE_NEWS": 3,
        "POST_NEWS_VOLATILITY": 4,
        "RELEASE": 5,
        "NEWS_LOCK": 6,
    }
    risks = [(event_regime(event, as_of, config), event) for event in relevant]
    risks = [pair for pair in risks if pair[0] != "NORMAL"]
    active = (
        max(risks, key=lambda pair: (priorities[pair[0]], -abs((pair[1].scheduled_at - as_of).total_seconds())))
        if risks
        else None
    )
    state = active[0] if active else "NORMAL"
    active_event = active[1] if active else None
    group = (
        release_group([e for e in relevant if e.group_id == active_event.group_id], config) if active_event else None
    )
    bias = group.bias if group else "UNKNOWN"
    at = active_event.scheduled_at if active_event else None
    structure_value = structure_context(structure, at, as_of, bias)
    windows = reaction(at, as_of, canonical, config, structure) if at and at <= as_of else []
    # Non-numeric releases have no invented macro direction. Match observed price
    # reaction to post-release structure instead, never infer sentiment from title.
    if active_event and active_event.unit == "NON_NUMERIC" and active_event.released_at and structure and windows:
        known = [w for w in windows if w.status == "READY" and w.move_atr is not None]
        if known and known[-1].move_atr:
            price_bias = "USD_NEGATIVE" if known[-1].move_atr > 0 else "USD_POSITIVE"
            structure_value = structure_context(structure, at, as_of, price_bias)
    ready = [window for window in windows if window.status == "READY"]
    reaction_state = ready[-1].classification if ready else "REACTION_UNAVAILABLE"
    baseline = current = ratio = None
    if at:
        previous = [
            q.ask - q.bid
            for q in observed
            if at - dt.timedelta(seconds=config.spread_baseline_seconds) <= q.timestamp < at
        ]
        fresh = [q for q in observed if (as_of - q.timestamp).total_seconds() <= config.quote_max_age_seconds]
        if len(previous) >= config.minimum_spread_samples:
            baseline = sum(previous, Decimal(0)) / len(previous)
        if fresh:
            current = fresh[-1].ask - fresh[-1].bid
        if baseline and current is not None:
            ratio = current / baseline
    spread = (
        "UNAVAILABLE"
        if ratio is None
        else "SPREAD_EXTREME"
        if ratio >= config.spread_extreme
        else "SPREAD_ELEVATED"
        if ratio >= config.spread_elevated
        else "SPREAD_NORMAL"
    )
    extent = ready[-1].range_atr if ready else None
    volatility = (
        "UNAVAILABLE"
        if extent is None
        else "EXTREME"
        if extent >= config.volatility_extreme
        else "ELEVATED"
        if extent >= config.volatility_elevated
        else "NORMAL"
    )
    reasons = []
    if mode == "FIXTURE":
        reasons.append("DEMO_NEWS_NOT_REAL_RELEASE")
    if not calendar_available:
        state = "UNKNOWN"
        reasons.append("CALENDAR_UNAVAILABLE")
    if not canonical:
        reasons.append("REACTION_UNAVAILABLE")
    if structure_value.status == "STRUCTURE_UNAVAILABLE":
        reasons.append("STRUCTURE_UNAVAILABLE")
    if group and group.alignment == "CONFLICTING":
        reasons.append("CONFLICTING_RELEASE")
    if active_event and active_event.actual is None:
        reasons.append("RESULT_NOT_AVAILABLE")
    release_status = (
        "NO_EVENT"
        if active_event is None
        else "PRE_NEWS"
        if active_event.scheduled_at > as_of
        else "WAITING_FOR_ACTUAL"
        if active_event.unit != "NON_NUMERIC" and active_event.actual is None
        else "WAITING_FOR_RELEASE"
        if active_event.released_at is None
        else "RELEASED"
    )
    quality = (
        "UNAVAILABLE"
        if not calendar_available
        else "CONFLICT"
        if any(e.field_conflicts for e in relevant)
        else "COMPLETE"
        if group and group.completeness == "COMPLETE"
        else "PARTIAL"
    )
    if release_status == "WAITING_FOR_ACTUAL":
        reasons.append("WAITING_FOR_ACTUAL")
    restricted = (
        not calendar_available
        or state in ("NEWS_LOCK", "RELEASE", "POST_NEWS_VOLATILITY")
        or reaction_state == "WHIPSAW"
        or spread == "SPREAD_EXTREME"
    )
    policy = "RESTRICTED" if restricted else "CAUTION" if state not in ("NORMAL", "NORMALIZED") else "INFORMATIONAL"
    advisory = "CAUTION" if policy != "INFORMATIONAL" else "ALLOWED"
    eligibility = {
        "TREND_CONTINUATION": advisory,
        "MEAN_REVERSION": advisory,
        "BREAKOUT": advisory,
        "NEWS_MOMENTUM": "WAITING",
        "NEWS_REVERSAL": "WAITING",
    }
    if (
        not restricted
        and release_status == "RELEASED"
        and quality == "COMPLETE"
        and state in ("POST_NEWS_CONFIRMATION", "NORMALIZED")
        and spread == "SPREAD_NORMAL"
        and volatility != "EXTREME"
        and structure_value.status == "ALIGNED"
    ):
        if reaction_state in ("STRONG_DIRECTIONAL", "BREAKOUT"):
            eligibility["NEWS_MOMENTUM"] = "ELIGIBLE"
        if reaction_state == "LIQUIDITY_SWEEP_REVERSAL":
            eligibility["NEWS_REVERSAL"] = "ELIGIBLE"
    config_id = hashlib.sha256(config.model_dump_json().encode()).hexdigest()[:16]
    inputs = {
        "version": NEWS_VERSION,
        "as_of": as_of.isoformat(),
        "config": config_id,
        "source": source,
        "mode": mode,
        "available": calendar_available,
        "view": view,
        "events": [e.model_dump(mode="json") for e in selected],
        "candles": [c.model_dump(mode="json") for c in canonical],
        "quotes": [q.model_dump(mode="json") for q in observed],
        "structure": None if structure is None else structure.model_dump(mode="json"),
    }
    fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return NewsStrategyContext.model_validate(
        {
            "release_status": release_status,
            "data_quality": quality,
            "as_of": as_of,
            "market_as_of": canonical[-1].open_time + dt.timedelta(minutes=1) if canonical else None,
            "config_id": config_id,
            "fingerprint": fingerprint,
            "source": source,
            "source_mode": mode,
            "calendar_state": "AVAILABLE" if calendar_available else "CALENDAR_UNAVAILABLE",
            "view": view,
            "events": selected,
            "xauusd_relevance": {
                e.id: {
                    "affected_currency": e.currency,
                    "score": relevance_score(e, config),
                    "channels": config.macro_channels.get(e.currency, []),
                }
                for e in selected
            },
            "upcoming_events": [e for e in relevant if e.scheduled_at > as_of],
            "active_group": group,
            "active_event_id": active_event.id if active_event else None,
            "news_regime": state,
            "macro_bias": bias,
            "macro_strength": "STRONG"
            if "STRONG" in bias
            else "MIXED"
            if bias == "CONFLICTING"
            else "UNKNOWN"
            if bias == "UNKNOWN"
            else "MODERATE",
            "multiple_event_risk": len({e.group_id for regime, e in risks}) > 1,
            "reaction_windows": windows,
            "reaction_state": reaction_state,
            "spread_state": spread,
            "baseline_spread": rounded(baseline),
            "current_spread": rounded(current),
            "spread_ratio": rounded(ratio),
            "volatility_state": volatility,
            "structure_confirmation": structure_value,
            "trade_policy_state": policy,
            "strategy_eligibility": eligibility,
            "reason_codes": reasons,
            "market_source": market_source,
        }
    )
