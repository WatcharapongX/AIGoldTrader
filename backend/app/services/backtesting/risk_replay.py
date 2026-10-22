"""D2C causal replay followed by independent stateless pure Risk evaluations."""

import datetime as dt
from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext

from app.services.backtesting.fingerprint import semantic_fingerprint
from app.services.backtesting.policy import MAX_CANDIDATES_PER_RUN, MAX_ESTIMATED_OUTPUT_BYTES
from app.services.backtesting.replay import make_replay_inputs, replay
from app.services.backtesting.replay_domain import ReplayError, ReplayFailureCode, ReplayInputs, ReplayStrategyEvent
from app.services.backtesting.risk_replay_domain import (
    RISK_REPLAY_INTEGRATION_VERSION,
    BacktestSymbolSpecAssumption,
    ReplayRiskEvent,
    RiskEvaluationStatus,
    RiskReplayConfig,
    RiskReplayError,
    RiskReplayFailureCode,
    RiskReplayResult,
)
from app.services.backtesting.risk_replay_fingerprint import (
    baseline_account_id,
    risk_configuration_fingerprint,
    risk_event_fingerprint,
    risk_output_fingerprint,
    risk_replay_input_fingerprint,
)
from app.services.news.domain import ObservedQuote
from app.services.news.engine import latest_known
from app.services.risk.domain import AccountSnapshot, RiskPolicy, SymbolSpecification
from app.services.risk.policy_core import evaluate_pure_risk
from app.services.risk.policy_domain import (
    DataHealthInputState,
    KillSwitchInputState,
    NewsAvailability,
    PortfolioExposureSnapshot,
    PureDataHealthInput,
    PureKillSwitchInput,
    PureNewsEvent,
    PureNewsState,
    PureQuoteState,
    PureRiskEvaluationInput,
    QuoteAvailability,
    ReservationIntegrityState,
)

MAX_RISK_CONFIGURATION_BYTES = 64 * 1024


def _guard_policy_size(policy: RiskPolicy) -> None:
    """Bound canonical Decimal expansion before fingerprinting the offline policy."""
    estimated_bytes = 1024  # Fixed keys and separators for this versioned contract.
    for value in policy.model_dump(mode="python").values():
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise RiskReplayError(RiskReplayFailureCode.CONFIGURATION_INVALID)
            sign, digits, exponent = value.as_tuple()
            estimated_bytes += sign + len(digits) + abs(exponent) + 3
        elif isinstance(value, str):
            # UTF-8 uses at most four bytes per code point; avoid rendering arbitrary-length versions.
            estimated_bytes += 4 * len(value)
        if estimated_bytes > MAX_RISK_CONFIGURATION_BYTES:
            raise RiskReplayError(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)


def _translate_replay_error(error: ReplayError) -> RiskReplayError:
    mapped = {
        ReplayFailureCode.RESOURCE_LIMIT_EXCEEDED: RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED,
        ReplayFailureCode.CAUSALITY_VIOLATION: RiskReplayFailureCode.CAUSALITY_VIOLATION,
        ReplayFailureCode.NEWS_UNAVAILABLE: RiskReplayFailureCode.NEWS_UNAVAILABLE,
        ReplayFailureCode.STRATEGY_CONFIG_INVALID: RiskReplayFailureCode.CONFIGURATION_INVALID,
    }
    return RiskReplayError(mapped.get(error.code, RiskReplayFailureCode.INPUT_INVALID))


def _prepare(inputs: ReplayInputs, config: RiskReplayConfig) -> tuple[ReplayInputs, RiskReplayConfig]:
    try:
        # Revalidate nested payloads even if caller bypassed validation or mutated frozen models.
        payload = config.model_dump(mode="python", round_trip=True)
        try:
            BacktestSymbolSpecAssumption.model_validate(payload["symbol_specification"])
        except (TypeError, ValueError) as error:
            raise RiskReplayError(RiskReplayFailureCode.SYMBOL_SPEC_INVALID) from error
        canonical_config = RiskReplayConfig.model_validate(payload)
        _guard_policy_size(canonical_config.policy)
        risk_configuration_fingerprint(canonical_config)  # Also reject non-finite semantic policy content.
    except RiskReplayError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise RiskReplayError(RiskReplayFailureCode.CONFIGURATION_INVALID) from error
    try:
        canonical = make_replay_inputs(
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
    except ReplayError as error:
        raise _translate_replay_error(error) from error
    except (AttributeError, TypeError, ValueError, ArithmeticError) as error:
        raise RiskReplayError(RiskReplayFailureCode.INPUT_INVALID) from error
    if canonical_config.policy.version != canonical.manifest.provenance.risk_policy_version:
        raise RiskReplayError(RiskReplayFailureCode.CONFIGURATION_INVALID)
    if canonical_config.policy.news_risk_enabled:
        vintage = canonical.manifest.coverage.news_vintages
        if (
            not vintage.available
            or vintage.source != canonical.news_source
            or not canonical.calendar_available
            or canonical.news_mode != "LIVE"
            or vintage.vintage_start is None
            or vintage.vintage_end is None
            or vintage.vintage_start > canonical.manifest.config.start
            or vintage.vintage_end < canonical.manifest.config.end
        ):
            raise RiskReplayError(RiskReplayFailureCode.NEWS_UNAVAILABLE)
    return canonical, canonical_config


def _news_at(inputs: ReplayInputs, config: RiskReplayConfig, at: dt.datetime) -> PureNewsState:
    if not config.policy.news_risk_enabled:
        return PureNewsState(availability=NewsAvailability.UNAVAILABLE, source="BACKTEST_NEWS_RISK_DISABLED")
    known = latest_known(list(inputs.news_events), at)
    known = [event for event in known if event.source == inputs.news_source]
    if len(known) > 200:
        raise RiskReplayError(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)
    return PureNewsState(
        availability=NewsAvailability.AVAILABLE,
        provider=inputs.news_source,
        source=inputs.news_source,
        events=tuple(
            PureNewsEvent(
                event_id=e.id,
                event_name=e.event_name,
                currency=e.currency,
                impact=e.impact,
                scheduled_at=e.scheduled_at,
                available_at=e.available_at,
                provider=e.source,
                source=e.source,
                revision_id=str(e.revision_version),
                revision_version=e.revision_version,
            )
            for e in known
        ),
    )


def _quote_at(inputs: ReplayInputs, at: dt.datetime) -> ObservedQuote | None:
    # D2A has already validated unique increasing market timestamps.
    return next(
        (
            q
            for q in reversed(inputs.quotes)
            if q.timestamp <= at and q.observed_at <= at and q.source == inputs.manifest.coverage.source
        ),
        None,
    )


def _build_input(
    inputs: ReplayInputs,
    config: RiskReplayConfig,
    event: ReplayStrategyEvent,
    account_id: str,
    quote: ObservedQuote | None,
) -> PureRiskEvaluationInput:
    at = event.as_of
    plan = event.trade_plan
    if (
        plan is None
        or event.context.as_of != at
        or event.candidate.detected_at != at
        or plan.as_of != at
        or plan.context_id != event.context_id
    ):
        raise RiskReplayError(RiskReplayFailureCode.CAUSALITY_VIOLATION)
    balance = inputs.manifest.config.initial_balance
    account = AccountSnapshot(
        id="bt_snap_"
        + semantic_fingerprint({"account_id": account_id, "source_event": event.event_fingerprint, "as_of": at}),
        account_id=account_id,
        balance=balance,
        equity=balance,
        peak_equity=balance,
        free_margin=balance,
        floating_pnl=0,
        daily_realized_pnl=0,
        weekly_realized_pnl=0,
        open_risk_pct=0,
        reserved_risk_pct=0,
        consecutive_losses=0,
        last_loss_at=None,
        cooldown_until=None,
        open_positions_count=0,
        state_version=1,
        state_updated_at=at,
        observed_at=at,
        as_of=at,
        trading_mode="BACKTEST",
        source="CONFIGURED_TEST",
    )
    assumption = config.symbol_specification
    specification = SymbolSpecification(
        **assumption.model_dump(mode="python"),
        id="bt_spec_" + semantic_fingerprint({"assumption": assumption, "effective_at": at}),
        observed_at=at,
        broker_server=None,
    )
    pure_quote = (
        PureQuoteState(availability=QuoteAvailability.UNAVAILABLE, mode="BACKTEST_HISTORICAL")
        if quote is None
        else PureQuoteState(
            availability=QuoteAvailability.AVAILABLE,
            timestamp=quote.timestamp,
            bid=quote.bid,
            ask=quote.ask,
            spread=quote.ask - quote.bid,
            source=quote.source,
            mode="BACKTEST_HISTORICAL",
            status="AVAILABLE",
        )
    )
    return PureRiskEvaluationInput(
        as_of=at,
        candidate=event.candidate,
        trade_plan=plan,
        account=account,
        policy=config.policy,
        symbol_specification=specification,
        quote=pure_quote,
        news=_news_at(inputs, config, at),
        kill_switch=PureKillSwitchInput(state=KillSwitchInputState.INACTIVE, source="BACKTEST_NO_EXTERNAL_KILL_SWITCH"),
        data_health=PureDataHealthInput(
            state=DataHealthInputState.HEALTHY,
            source="BACKTEST_CAUSAL_DATA_ADMISSION",
            provider="backtest",
            consecutive_failures=0,
            threshold=config.policy.data_health_consecutive_failures,
        ),
        candidate_lifecycle_status=event.candidate_status,
        candidate_transition_count=0,
        caller_requested_risk_pct=config.caller_requested_risk_pct,
        portfolio=PortfolioExposureSnapshot(
            symbol=event.candidate.symbol,
            direction=plan.direction,
            open_risk_pct=0,
            reserved_risk_pct=0,
            symbol_risk_pct=0,
            directional_risk_pct=0,
            active_reservation_count=0,
            open_position_count=0,
            reservation_integrity=ReservationIntegrityState.OK,
        ),
    )


def replay_risk(
    inputs: ReplayInputs, config: RiskReplayConfig, *, stop_at: dt.datetime | None = None
) -> RiskReplayResult:
    """Evaluate each D2A plan independently; approvals never evolve simulation state."""
    context = Context(
        prec=28,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )
    with localcontext(context):
        return _replay_risk(inputs, config, stop_at)


def _validate_source_events(source) -> None:
    """Reject a perturbed D2A stream (reordered/duplicated/future) with a stable code.

    ``ReplayResult`` normally validates canonical order, but a caller/monkeypatch can
    bypass that via ``model_copy``; D2C must never let the raw ``ValidationError``
    from final result construction escape (D2C-IV-P2-001).
    """
    keys = [(e.as_of, e.profile_id, e.strategy_id, e.candidate_id) for e in source.events]
    if keys != sorted(keys) or len(keys) != len(set(keys)) or any(e.as_of > source.cutoff for e in source.events):
        raise RiskReplayError(RiskReplayFailureCode.CAUSALITY_VIOLATION)


def _replay_risk(inputs: ReplayInputs, config: RiskReplayConfig, stop_at: dt.datetime | None) -> RiskReplayResult:
    canonical, config = _prepare(inputs, config)
    try:
        source = replay(canonical, stop_at=stop_at)
    except ReplayError as error:
        raise _translate_replay_error(error) from error
    except (TypeError, ValueError, ArithmeticError) as error:
        raise RiskReplayError(RiskReplayFailureCode.CAUSALITY_VIOLATION) from error
    _validate_source_events(source)
    configuration = risk_configuration_fingerprint(config)
    account_id = baseline_account_id(
        canonical.manifest.config.symbol, canonical.manifest.config.initial_balance, configuration
    )
    events: list[ReplayRiskEvent] = []
    output_bytes = 0
    for event in source.events:
        if len(events) >= MAX_CANDIDATES_PER_RUN:
            raise RiskReplayError(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)
        payload = {
            "as_of": event.as_of,
            "profile_id": event.profile_id,
            "strategy_id": event.strategy_id,
            "candidate_id": event.candidate_id,
            "plan_id": None,
            "replay_strategy_event_fingerprint": event.event_fingerprint,
            "risk_evaluation_status": RiskEvaluationStatus.NOT_EVALUATED_NO_PLAN,
            "risk_input_fingerprint": None,
            "pure_risk_result": None,
            "pure_risk_fingerprint": None,
            "quote_timestamp": None,
            "quote_observed_at": None,
        }
        if event.trade_plan is not None:
            quote = _quote_at(canonical, event.as_of)
            try:
                pure_input = _build_input(canonical, config, event, account_id, quote)
            except RiskReplayError:
                raise
            except (TypeError, ValueError, ArithmeticError) as error:
                raise RiskReplayError(RiskReplayFailureCode.CAUSALITY_VIOLATION) from error
            try:
                pure_result = evaluate_pure_risk(pure_input)
            except Exception as error:
                raise RiskReplayError(RiskReplayFailureCode.POLICY_EVALUATION_FAILED) from error
            payload.update(
                plan_id=event.trade_plan.id,
                risk_evaluation_status=RiskEvaluationStatus.EVALUATED,
                risk_input_fingerprint=semantic_fingerprint(
                    {
                        "kind": "risk-event-input",
                        "integration_version": RISK_REPLAY_INTEGRATION_VERSION,
                        "input": pure_input,
                        "source_event": event.event_fingerprint,
                        "quote_observed_at": quote.observed_at if quote else None,
                    }
                ),
                pure_risk_result=pure_result,
                pure_risk_fingerprint=pure_result.semantic_fingerprint,
                quote_timestamp=quote.timestamp if quote else None,
                quote_observed_at=quote.observed_at if quote else None,
            )
        try:
            risk_event = ReplayRiskEvent(**payload, risk_event_fingerprint=risk_event_fingerprint(payload))
        except (TypeError, ValueError, ArithmeticError) as error:
            raise RiskReplayError(RiskReplayFailureCode.CAUSALITY_VIOLATION) from error
        output_bytes += len(risk_event.model_dump_json().encode("utf-8"))
        if output_bytes > MAX_ESTIMATED_OUTPUT_BYTES:
            raise RiskReplayError(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)
        events.append(risk_event)
    evaluated = sum(e.risk_evaluation_status == RiskEvaluationStatus.EVALUATED for e in events)
    output = {
        "cutoff": source.cutoff,
        "source_replay_fingerprint": source.replay_fingerprint,
        "strategy_events_seen": len(events),
        "risk_events_evaluated": evaluated,
        "no_plan_events": len(events) - evaluated,
        "events": tuple(events),
    }
    try:
        result = RiskReplayResult(
            **output,
            source_replay_input_fingerprint=source.replay_input_fingerprint,
            risk_configuration_fingerprint=configuration,
            risk_replay_input_fingerprint=risk_replay_input_fingerprint(source.replay_input_fingerprint, configuration),
            risk_replay_fingerprint=risk_output_fingerprint(output),
        )
    except (TypeError, ValueError, ArithmeticError) as error:
        raise RiskReplayError(RiskReplayFailureCode.CAUSALITY_VIOLATION) from error
    # Include the envelope, separators, and all metadata in the actual wire bound.
    if len(result.model_dump_json().encode("utf-8")) > MAX_ESTIMATED_OUTPUT_BYTES:
        raise RiskReplayError(RiskReplayFailureCode.RESOURCE_LIMIT_EXCEEDED)
    return result
