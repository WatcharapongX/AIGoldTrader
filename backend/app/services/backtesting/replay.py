"""Single-threaded causal prefix replay through existing Analysis/News/Strategy engines."""

import datetime as dt
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.services.analysis.domain import AnalysisConfig
from app.services.analysis.engine import analyze
from app.services.backtesting.domain import (
    REPLAY_ENGINE_VERSION,
    BacktestRunManifest,
    CoverageGapCode,
    GapExpectation,
)
from app.services.backtesting.fingerprint import (
    historical_data_fingerprint,
    replay_configuration_fingerprint,
    replay_input_fingerprint,
    semantic_fingerprint,
)
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
from app.services.market_data.domain import SECONDS, Candle, Timeframe, bucket
from app.services.news.domain import EconomicEvent, NewsConfig, ObservedQuote
from app.services.news.engine import build_context as build_news_context
from app.services.strategy.context import build_context as build_strategy_context
from app.services.strategy.domain import StrategyConfig
from app.services.strategy.engine import REGISTRY, profiles

_MAX_FRAME_WINDOW = 1000
_MAX_ANALYSIS_WINDOW = 300
_MAX_NEWS_EVENTS = 2000
_MAX_QUOTES = 3600


@dataclass(frozen=True)
class _ReplayCandleFrame:
    timeframe: Timeframe
    candles: tuple[Candle, ...]


@dataclass(frozen=True)
class _ReplayExecution:
    manifest: BacktestRunManifest
    candle_frames: tuple[_ReplayCandleFrame, ...]
    news_events: tuple[EconomicEvent, ...]
    quotes: tuple[ObservedQuote, ...]
    strategy_config: StrategyConfig
    analysis_config: AnalysisConfig
    news_config: NewsConfig
    tick_size: Decimal | None
    news_source: str
    news_mode: str
    calendar_available: bool
    historical_fingerprint: str
    configuration_fingerprint: str
    input_fingerprint: str


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


def _model_copy(model_type, value):
    payload = value.model_dump(mode="python") if hasattr(value, "model_dump") else value
    return model_type.model_validate(payload)


def _reconcile_candle_continuity(
    manifest: BacktestRunManifest,
    candles: dict[Timeframe, tuple[Candle, ...]],
) -> None:
    """Match every governed missing bucket to scheduled-closure evidence exactly."""
    coverage_by_frame = {item.timeframe: item for item in manifest.coverage.timeframe_coverage}
    gaps_by_frame = {
        timeframe: tuple(gap for gap in manifest.coverage.gaps if gap.timeframe == timeframe)
        for timeframe in manifest.coverage.required_timeframes
    }
    for timeframe, values in candles.items():
        step = dt.timedelta(seconds=SECONDS[timeframe])
        frame_coverage = coverage_by_frame[timeframe]
        governed_start = max(manifest.coverage.warmup_start, frame_coverage.available_start)
        governed_end = min(manifest.coverage.usable_end, frame_coverage.available_end)
        missing: set[dt.datetime] = set()
        for previous, current in zip(values, values[1:], strict=False):
            expected = previous.open_time + step
            while expected < current.open_time:
                if governed_start <= expected and expected + step <= governed_end:
                    missing.add(expected)
                expected += step

        declared: set[dt.datetime] = set()
        for gap in gaps_by_frame[timeframe]:
            if (
                gap.expectation != GapExpectation.EXPECTED_SCHEDULED_CLOSURE
                or gap.code != CoverageGapCode.SCHEDULED_MARKET_CLOSURE
                or gap.gap_start != bucket(gap.gap_start, timeframe)
                or gap.gap_end != bucket(gap.gap_end, timeframe)
            ):
                _fail(ReplayFailureCode.INPUT_INVALID)
            expected = gap.gap_start
            while expected < gap.gap_end:
                if governed_start <= expected and expected + step <= governed_end:
                    declared.add(expected)
                expected += step
        if missing != declared:
            _fail(ReplayFailureCode.INPUT_INVALID)


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
        raw_values = _bounded_tuple(candles[timeframe], frame_limit)
        try:
            values = tuple(_model_copy(Candle, candle) for candle in raw_values)
        except (TypeError, ValueError) as error:
            _fail(ReplayFailureCode.INPUT_INVALID, error)
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
    _reconcile_candle_continuity(manifest, result)
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


def _canonical_replay_inputs(
    *,
    manifest,
    candles,
    news_events,
    quotes,
    strategy_config,
    analysis_config,
    news_config,
    tick_size,
    news_source,
    news_mode,
    calendar_available,
) -> tuple[ReplayInputs, str, str, str]:
    """Prepare the exact canonical snapshot and identities used for execution."""
    try:
        canonical_manifest = _model_copy(BacktestRunManifest, manifest)
        canonical_candles = _validate_candles(canonical_manifest, candles)
        canonical_news = tuple(
            _model_copy(EconomicEvent, event) for event in _bounded_tuple(news_events, _MAX_NEWS_EVENTS)
        )
        canonical_quotes = tuple(
            _model_copy(ObservedQuote, quote) for quote in _bounded_tuple(quotes, _MAX_QUOTES)
        )
        canonical_strategy = _model_copy(StrategyConfig, strategy_config or StrategyConfig())
        canonical_analysis = _model_copy(AnalysisConfig, analysis_config or AnalysisConfig())
        canonical_news_config = _model_copy(NewsConfig, news_config or NewsConfig())
        result = ReplayInputs.model_validate(
            {
                "manifest": canonical_manifest,
                "candles": canonical_candles,
                "news_events": canonical_news,
                "quotes": canonical_quotes,
                "strategy_config": canonical_strategy,
                "analysis_config": canonical_analysis,
                "news_config": canonical_news_config,
                "tick_size": tick_size,
                "news_source": news_source,
                "news_mode": news_mode,
                "calendar_available": calendar_available,
            }
        )
    except ReplayError:
        raise
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        _fail(ReplayFailureCode.INPUT_INVALID, error)
    _validate_news(result)
    _validate_quotes(result)
    _validate_strategy_scope(result)
    historical_fingerprint = historical_data_fingerprint(
        symbol=canonical_manifest.config.symbol,
        source=canonical_manifest.coverage.source,
        candles=canonical_candles,
        news_events=canonical_news,
        quotes=canonical_quotes,
        news_source=result.news_source,
        news_mode=result.news_mode,
        calendar_available=result.calendar_available,
    )
    if historical_fingerprint != canonical_manifest.coverage.data_fingerprint:
        _fail(ReplayFailureCode.INPUT_INVALID)
    configuration_fingerprint = replay_configuration_fingerprint(
        strategy_config=canonical_strategy,
        analysis_config=canonical_analysis,
        news_config=canonical_news_config,
        tick_size=result.tick_size,
        replay_engine_version=REPLAY_ENGINE_VERSION,
    )
    input_fingerprint = replay_input_fingerprint(
        manifest=canonical_manifest,
        configuration_fingerprint=configuration_fingerprint,
    )
    return result, historical_fingerprint, configuration_fingerprint, input_fingerprint


def _prepare_replay_execution(inputs: ReplayInputs) -> _ReplayExecution:
    canonical, historical_fingerprint, configuration_fingerprint, input_fingerprint = _canonical_replay_inputs(
        manifest=inputs.manifest,
        candles=inputs.candles,
        news_events=inputs.news_events,
        quotes=inputs.quotes,
        strategy_config=inputs.strategy_config,
        analysis_config=inputs.analysis_config,
        news_config=inputs.news_config,
        tick_size=inputs.tick_size,
        news_source=inputs.news_source,
        news_mode=inputs.news_mode,
        calendar_available=inputs.calendar_available,
    )
    frames = tuple(
        _ReplayCandleFrame(timeframe=timeframe, candles=canonical.candles[timeframe])
        for timeframe in sorted(canonical.candles, key=lambda item: SECONDS[item])
    )
    return _ReplayExecution(
        manifest=canonical.manifest,
        candle_frames=frames,
        news_events=canonical.news_events,
        quotes=canonical.quotes,
        strategy_config=canonical.strategy_config,
        analysis_config=canonical.analysis_config,
        news_config=canonical.news_config,
        tick_size=canonical.tick_size,
        news_source=canonical.news_source,
        news_mode=canonical.news_mode,
        calendar_available=canonical.calendar_available,
        historical_fingerprint=historical_fingerprint,
        configuration_fingerprint=configuration_fingerprint,
        input_fingerprint=input_fingerprint,
    )


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
    result, _, _, _ = _canonical_replay_inputs(
        manifest=manifest,
        candles=candles,
        news_events=news_events,
        quotes=quotes,
        strategy_config=strategy_config,
        analysis_config=analysis_config,
        news_config=news_config,
        tick_size=tick_size,
        news_source=news_source,
        news_mode=news_mode,
        calendar_available=calendar_available,
    )
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
    execution = _prepare_replay_execution(inputs)
    manifest = execution.manifest
    candles = {frame.timeframe: frame.candles for frame in execution.candle_frames}
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
            config=execution.analysis_config,
        )
        try:
            news = build_news_context(
                list(execution.news_events),
                at,
                source=execution.news_source,
                mode=execution.news_mode,
                config=execution.news_config,
                candles=m1,
                quotes=list(execution.quotes),
                structure=structure,
                calendar_available=execution.calendar_available,
                market_source=manifest.coverage.source,
            )
            context = build_strategy_context(
                candles=visible,
                symbol=manifest.config.symbol,
                source=manifest.coverage.source,
                at=at,
                news=news,
                tick_size=execution.tick_size,
                config=execution.strategy_config,
                analysis_config=execution.analysis_config,
                replay=True,
                quotes=execution.quotes,
            )
        except (TypeError, ValueError) as error:
            _fail(ReplayFailureCode.CAUSALITY_VIOLATION, error)
        selected = _selected_profile(
            execution.strategy_config,
            context.config_id,
            manifest.config.profile_id,
            manifest.config.strategy_id,
        )
        try:
            candidate = REGISTRY[manifest.config.strategy_id].evaluate(
                context, selected, execution.strategy_config
            )
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
        replay_input_fingerprint=execution.input_fingerprint,
        cutoff=cutoff,
        primary_events_processed=len(primary_events),
        events=tuple(events),
        replay_fingerprint=semantic_fingerprint(result_payload),
    )
