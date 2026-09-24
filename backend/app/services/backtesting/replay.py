"""Single-threaded causal prefix replay through existing Analysis/News/Strategy engines."""

import datetime as dt
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from app.services.analysis.engine import analyze
from app.services.backtesting.domain import REPLAY_ENGINE_VERSION, BacktestRunManifest
from app.services.backtesting.fingerprint import historical_data_fingerprint, semantic_fingerprint
from app.services.backtesting.policy import (
    MAX_CANDIDATES_PER_RUN,
    MAX_PRIMARY_REPLAY_EVENTS,
    MAX_TOTAL_CANDLE_INPUTS,
)
from app.services.backtesting.replay_domain import (
    ReplayClock,
    ReplayError,
    ReplayFailureCode,
    ReplayInputs,
    ReplayResult,
    ReplayStrategyEvent,
)
from app.services.market_data.domain import SECONDS, Candle, Timeframe
from app.services.news.domain import EconomicEvent, ObservedQuote
from app.services.news.engine import build_context as build_news_context
from app.services.strategy.context import build_context as build_strategy_context
from app.services.strategy.domain import StrategyConfig
from app.services.strategy.engine import REGISTRY, profiles

_MAX_FRAME_WINDOW = 1000
_MAX_ANALYSIS_WINDOW = 300
_MAX_NEWS_EVENTS = 2000
_MAX_QUOTES = 3600


def _fail(code: ReplayFailureCode, error: Exception | None = None) -> None:
    if error is None:
        raise ReplayError(code)
    raise ReplayError(code) from error


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        _fail(ReplayFailureCode.INPUT_INVALID)
    return value.astimezone(dt.UTC)


def _bounded_tuple(values: Iterable, limit: int) -> tuple:
    result = []
    for item in values:
        if len(result) == limit:
            _fail(ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)
        result.append(item)
    return tuple(result)


def _validate_candles(
    manifest: BacktestRunManifest, candles: Mapping[Timeframe, Sequence[Candle]]
) -> dict[Timeframe, tuple[Candle, ...]]:
    required = set(manifest.coverage.required_timeframes)
    if set(candles) != required or manifest.config.timeframe not in candles:
        _fail(ReplayFailureCode.INPUT_INVALID)
    result: dict[Timeframe, tuple[Candle, ...]] = {}
    remaining = MAX_TOTAL_CANDLE_INPUTS
    for timeframe in sorted(candles, key=lambda item: SECONDS[item]):
        frame_limit = remaining
        if timeframe == manifest.config.timeframe:
            frame_limit = min(frame_limit, MAX_PRIMARY_REPLAY_EVENTS)
        values = _bounded_tuple(candles[timeframe], frame_limit)
        remaining -= len(values)
        previous: dt.datetime | None = None
        forming = False
        for index, candle in enumerate(values):
            invalid_closed_state = (
                timeframe == manifest.config.timeframe
                and not candle.is_closed
                or forming
                or not candle.is_closed
                and index != len(values) - 1
            )
            if (
                candle.symbol != manifest.config.symbol
                or candle.source != manifest.coverage.source
                or candle.timeframe != timeframe
                or invalid_closed_state
                or previous is not None
                and candle.open_time <= previous
            ):
                code = (
                    ReplayFailureCode.NON_MONOTONIC
                    if previous and candle.open_time <= previous
                    else ReplayFailureCode.INPUT_INVALID
                )
                _fail(code)
            previous = candle.open_time
            forming = not candle.is_closed
        result[timeframe] = values
    coverage_by_frame = {item.timeframe: item for item in manifest.coverage.timeframe_coverage}
    primary_count = len(result[manifest.config.timeframe])
    total = sum(len(values) for values in result.values())
    if primary_count != manifest.coverage.available_primary_events or total != manifest.coverage.total_candle_inputs:
        _fail(ReplayFailureCode.INPUT_INVALID)
    for timeframe, values in result.items():
        frame_coverage = coverage_by_frame[timeframe]
        if len(values) != frame_coverage.available_events or not values:
            _fail(ReplayFailureCode.INPUT_INVALID)
        supplied_start = values[0].open_time
        supplied_end = values[-1].open_time + dt.timedelta(seconds=SECONDS[timeframe])
        if supplied_start > frame_coverage.available_start or supplied_end < frame_coverage.available_end:
            _fail(ReplayFailureCode.INPUT_INVALID)
    return result


def _validate_news(inputs: ReplayInputs) -> None:
    seen: dict[tuple[str, int], EconomicEvent] = {}
    for event in inputs.news_events:
        key = (event.id, event.revision_version)
        if key in seen and seen[key] != event:
            _fail(ReplayFailureCode.INPUT_INVALID)
        seen[key] = event
        if event.source != inputs.news_source or event.source_mode != inputs.news_mode:
            _fail(ReplayFailureCode.INPUT_INVALID)
    if inputs.manifest.config.strategy_id in ("STRAT05", "STRAT06"):
        coverage = inputs.manifest.coverage.news_vintages
        if not coverage.available or coverage.source != inputs.news_source or not inputs.calendar_available:
            _fail(ReplayFailureCode.NEWS_UNAVAILABLE)


def _validate_strategy_scope(inputs: ReplayInputs) -> None:
    manifest = inputs.manifest
    if inputs.strategy_config.version != manifest.provenance.strategy_version:
        _fail(ReplayFailureCode.STRATEGY_CONFIG_INVALID)
    selected = next(
        (
            profile
            for profile in profiles(inputs.strategy_config, "scope-validation")
            if profile.id == manifest.config.profile_id
        ),
        None,
    )
    if selected is None or manifest.config.strategy_id not in selected.allowed_strategies:
        _fail(ReplayFailureCode.STRATEGY_CONFIG_INVALID)
    mapped = {
        selected.timeframe_map.context,
        selected.timeframe_map.bias,
        selected.timeframe_map.setup,
        selected.timeframe_map.trigger,
    }
    required = set(manifest.coverage.required_timeframes)
    if not mapped <= required or manifest.config.strategy_id in ("STRAT05", "STRAT06") and Timeframe.M1 not in required:
        _fail(ReplayFailureCode.STRATEGY_CONFIG_INVALID)


def _validate_quotes(inputs: ReplayInputs) -> None:
    previous: dt.datetime | None = None
    for quote in inputs.quotes:
        if quote.source != inputs.manifest.coverage.source or previous is not None and quote.timestamp <= previous:
            code = (
                ReplayFailureCode.NON_MONOTONIC
                if previous and quote.timestamp <= previous
                else ReplayFailureCode.INPUT_INVALID
            )
            _fail(code)
        previous = quote.timestamp


def make_replay_inputs(
    *,
    manifest: BacktestRunManifest,
    candles: Mapping[Timeframe, Sequence[Candle]],
    news_events: Sequence[EconomicEvent] = (),
    quotes: Sequence[ObservedQuote] = (),
    strategy_config=None,
    analysis_config=None,
    news_config=None,
    tick_size: Decimal | None = None,
    news_source: str = "historical_unavailable",
    news_mode: str = "UNAVAILABLE",
    calendar_available: bool = False,
) -> ReplayInputs:
    """Validate cheap collection counts before immutable Pydantic materialization."""
    canonical = _validate_candles(manifest, candles)
    canonical_news = _bounded_tuple(news_events, _MAX_NEWS_EVENTS)
    canonical_quotes = _bounded_tuple(quotes, _MAX_QUOTES)
    values = {
        "manifest": manifest,
        "candles": canonical,
        "news_events": canonical_news,
        "quotes": canonical_quotes,
        "tick_size": tick_size,
        "news_source": news_source,
        "news_mode": news_mode,
        "calendar_available": calendar_available,
    }
    if strategy_config is not None:
        values["strategy_config"] = strategy_config
    if analysis_config is not None:
        values["analysis_config"] = analysis_config
    if news_config is not None:
        values["news_config"] = news_config
    try:
        result = ReplayInputs.model_validate(values)
    except (TypeError, ValueError) as error:
        _fail(ReplayFailureCode.INPUT_INVALID, error)
    _validate_news(result)
    _validate_quotes(result)
    _validate_strategy_scope(result)
    actual_fingerprint = historical_data_fingerprint(
        symbol=manifest.config.symbol,
        source=manifest.coverage.source,
        candles=canonical,
        news_events=result.news_events,
        quotes=result.quotes,
        news_source=result.news_source,
        news_mode=result.news_mode,
        calendar_available=result.calendar_available,
    )
    if actual_fingerprint != manifest.coverage.data_fingerprint:
        _fail(ReplayFailureCode.INPUT_INVALID)
    return result


def _visible_prefix(
    candles: tuple[Candle, ...], timeframe: Timeframe, at: dt.datetime, warmup_start: dt.datetime
) -> tuple[Candle, ...]:
    latest_open = at - dt.timedelta(seconds=SECONDS[timeframe])
    stop = bisect_right(candles, latest_open, key=lambda candle: candle.open_time)
    visible = tuple(
        candle
        for candle in candles[:stop]
        if candle.is_closed and candle.open_time + dt.timedelta(seconds=SECONDS[timeframe]) >= warmup_start
    )
    return visible[-_MAX_FRAME_WINDOW:]


def _selected_profile(config: StrategyConfig, config_id: str, profile_id: str, strategy_id: str):
    selected = next((profile for profile in profiles(config, config_id) if profile.id == profile_id), None)
    if selected is None or strategy_id not in selected.allowed_strategies:
        _fail(ReplayFailureCode.STRATEGY_CONFIG_INVALID)
    return selected


def replay(inputs: ReplayInputs, *, stop_at: dt.datetime | None = None) -> ReplayResult:
    """Recompute every reportable decision from the causal prefix visible at its UTC close."""
    manifest = inputs.manifest
    candles = _validate_candles(manifest, inputs.candles)
    _validate_news(inputs)
    _validate_quotes(inputs)
    _validate_strategy_scope(inputs)
    cutoff = min(_utc(stop_at) if stop_at is not None else manifest.config.end, manifest.config.end)
    if cutoff < manifest.coverage.warmup_start:
        _fail(ReplayFailureCode.INPUT_INVALID)
    primary = candles[manifest.config.timeframe]
    primary_events = [
        candle.open_time + dt.timedelta(seconds=SECONDS[manifest.config.timeframe])
        for candle in primary
        if manifest.coverage.warmup_start
        <= candle.open_time + dt.timedelta(seconds=SECONDS[manifest.config.timeframe])
        <= cutoff
    ]
    if len(primary_events) > MAX_PRIMARY_REPLAY_EVENTS:
        _fail(ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)
    clock = ReplayClock()
    events: list[ReplayStrategyEvent] = []
    identities: dict[tuple[dt.datetime, str, str, str], str] = {}
    for event_time in primary_events:
        at = clock.advance(event_time)
        visible = {
            timeframe: list(_visible_prefix(values, timeframe, at, manifest.coverage.warmup_start))
            for timeframe, values in candles.items()
        }
        m1 = visible.get(Timeframe.M1, [])
        structure = analyze(
            m1[-_MAX_ANALYSIS_WINDOW:],
            manifest.config.symbol,
            Timeframe.M1,
            manifest.coverage.source,
            requested=_MAX_ANALYSIS_WINDOW,
            config=inputs.analysis_config,
        )
        try:
            news = build_news_context(
                list(inputs.news_events),
                at,
                source=inputs.news_source,
                mode=inputs.news_mode,
                config=inputs.news_config,
                candles=m1,
                quotes=list(inputs.quotes),
                structure=structure,
                calendar_available=inputs.calendar_available,
                market_source=manifest.coverage.source,
            )
            context = build_strategy_context(
                candles=visible,
                symbol=manifest.config.symbol,
                source=manifest.coverage.source,
                at=at,
                news=news,
                tick_size=inputs.tick_size,
                config=inputs.strategy_config,
                analysis_config=inputs.analysis_config,
                replay=True,
                quotes=inputs.quotes,
            )
        except (TypeError, ValueError) as error:
            _fail(ReplayFailureCode.CAUSALITY_VIOLATION, error)
        selected = _selected_profile(
            inputs.strategy_config,
            context.config_id,
            manifest.config.profile_id,
            manifest.config.strategy_id,
        )
        try:
            candidate = REGISTRY[manifest.config.strategy_id].evaluate(context, selected, inputs.strategy_config)
        except (KeyError, TypeError, ValueError) as error:
            _fail(ReplayFailureCode.STRATEGY_CONFIG_INVALID, error)
        if at < manifest.config.start:
            continue
        projected = context.dependency_projection(manifest.config.strategy_id)
        payload = {
            "replay_engine_version": REPLAY_ENGINE_VERSION,
            "as_of": at,
            "profile_id": selected.id,
            "strategy_id": manifest.config.strategy_id,
            "context": projected,
            "candidate": candidate,
            "trade_plan": candidate.plan,
        }
        event_fingerprint = semantic_fingerprint(payload)
        key = (at, selected.id, manifest.config.strategy_id, candidate.id)
        if key in identities:
            if identities[key] != event_fingerprint:
                _fail(ReplayFailureCode.CAUSALITY_VIOLATION)
            continue
        identities[key] = event_fingerprint
        events.append(
            ReplayStrategyEvent(
                as_of=at,
                profile_id=selected.id,
                strategy_id=manifest.config.strategy_id,
                context_id=candidate.context_id,
                candidate_id=candidate.id,
                candidate_status=candidate.status,
                context=projected,
                candidate=candidate,
                trade_plan=candidate.plan,
                event_fingerprint=event_fingerprint,
            )
        )
        if len(events) > MAX_CANDIDATES_PER_RUN:
            _fail(ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)
    events.sort(key=lambda item: (item.as_of, item.profile_id, item.strategy_id, item.candidate_id))
    result_payload = {
        "replay_engine_version": REPLAY_ENGINE_VERSION,
        "cutoff": cutoff,
        "primary_events_processed": len(primary_events),
        "primary_candles": tuple(
            candle
            for candle in primary
            if candle.is_closed
            and manifest.coverage.warmup_start
            <= candle.open_time + dt.timedelta(seconds=SECONDS[manifest.config.timeframe])
            <= cutoff
        ),
        "events": events,
    }
    return ReplayResult(
        replay_engine_version=REPLAY_ENGINE_VERSION,
        cutoff=cutoff,
        primary_events_processed=len(primary_events),
        events=tuple(events),
        replay_fingerprint=semantic_fingerprint(result_payload),
    )
