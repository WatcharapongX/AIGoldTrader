"""D2B2 adapters between stateful live Risk orchestration and the pure policy core."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.services.market_data.domain import Quote
from app.services.news.domain import NewsStrategyContext
from app.services.risk.domain import AccountSnapshot, RiskPolicy, SymbolSpecification
from app.services.risk.policy_domain import (
    DataHealthInputState,
    KillSwitchInputState,
    MarketSafetyState,
    NewsAvailability,
    PortfolioExposureSnapshot,
    PureDataHealthInput,
    PureKillSwitchInput,
    PureNewsEvent,
    PureNewsState,
    PureQuoteState,
    PureRiskCode,
    PureRiskEvaluationInput,
    PureRiskResult,
    QuoteAvailability,
    ReservationIntegrityState,
)
from app.services.strategy.domain import SetupCandidate, TradePlanSuggestion


def pure_quote_from_live(quote: Quote | None) -> PureQuoteState:
    if quote is None:
        return PureQuoteState(availability=QuoteAvailability.UNAVAILABLE)
    return PureQuoteState(
        availability=QuoteAvailability.AVAILABLE,
        timestamp=quote.timestamp,
        bid=quote.bid,
        ask=quote.ask,
        spread=quote.spread,
        source=quote.source,
        mode=quote.mode,
        status=quote.status,
    )


def pure_news_from_live(news_context: NewsStrategyContext | None) -> PureNewsState:
    if news_context is None or news_context.calendar_state != "AVAILABLE":
        return PureNewsState(availability=NewsAvailability.UNAVAILABLE)

    events = tuple(
        PureNewsEvent(
            event_id=event.id,
            event_name=event.event_name,
            currency=event.currency,
            impact=event.impact,
            scheduled_at=event.scheduled_at,
            available_at=event.available_at,
            provider=event.source,
            source=event.source,
            revision_id=(
                str(event.revision_version)
                if event.revision_version is not None
                else str(getattr(event, "revision_id", ""))
            ),
            revision_version=event.revision_version,
        )
        for event in news_context.events
    )
    provider = getattr(news_context, "source", "") or getattr(news_context, "provider", "")
    revision_version = getattr(news_context, "revision_version", None)
    revision_id = (
        str(revision_version)
        if revision_version is not None
        else str(getattr(news_context, "revision_id", ""))
    )
    return PureNewsState(
        availability=NewsAvailability.AVAILABLE,
        events=events,
        provider=provider,
        source=provider,
        revision_id=revision_id,
        revision_version=revision_version,
    )


def baseline_portfolio_snapshot(
    account: AccountSnapshot,
    candidate: SetupCandidate,
    plan: TradePlanSuggestion,
) -> PortfolioExposureSnapshot:
    """Return validation-safe preflight evidence without reading reservation state."""
    return PortfolioExposureSnapshot(
        symbol=candidate.symbol,
        direction=plan.direction,
        open_risk_pct=account.open_risk_pct,
        reserved_risk_pct=Decimal("0"),
        symbol_risk_pct=Decimal("0"),
        directional_risk_pct=Decimal("0"),
        active_reservation_count=0,
        open_position_count=account.open_positions_count,
        reservation_integrity=ReservationIntegrityState.OK,
    )


def portfolio_snapshot_from_live(
    account: AccountSnapshot,
    candidate: SetupCandidate,
    plan: TradePlanSuggestion,
    active_reservations: Sequence[Any],
) -> tuple[PortfolioExposureSnapshot, Decimal, str | None]:
    """Build locked DB-authoritative pure exposure and legacy fingerprint evidence.

    Exactly one reservation for the evaluated candidate is the canonical retry row and is
    excluded. Multiple rows for that candidate remain visible as an integrity anomaly.
    """
    candidate_rows = [
        row for row in active_reservations if getattr(row, "candidate_id", None) == candidate.id
    ]
    excluded_id = candidate_rows[0].id if len(candidate_rows) == 1 else None
    effective_rows = [row for row in active_reservations if row.id != excluded_id]

    candidate_counts: dict[str, int] = {}
    duplicate_candidate_id: str | None = None
    for row in effective_rows:
        candidate_id = getattr(row, "candidate_id", None)
        if not candidate_id:
            continue
        candidate_counts[candidate_id] = candidate_counts.get(candidate_id, 0) + 1
        if candidate_counts[candidate_id] > 1 and duplicate_candidate_id is None:
            duplicate_candidate_id = candidate_id

    def risk_sum(rows: Sequence[Any]) -> Decimal:
        return sum((Decimal(str(row.risk_pct)) for row in rows), Decimal("0"))

    reserved_risk = risk_sum(effective_rows)
    symbol_risk = risk_sum([row for row in effective_rows if row.symbol == candidate.symbol])
    directional_risk = risk_sum([row for row in effective_rows if row.direction == plan.direction])
    legacy_fingerprint_reserved = risk_sum(
        [row for row in active_reservations if getattr(row, "candidate_id", None) != candidate.id]
    )

    return (
        PortfolioExposureSnapshot(
            symbol=candidate.symbol,
            direction=plan.direction,
            open_risk_pct=account.open_risk_pct,
            reserved_risk_pct=reserved_risk,
            symbol_risk_pct=symbol_risk,
            directional_risk_pct=directional_risk,
            active_reservation_count=len(effective_rows),
            open_position_count=account.open_positions_count,
            reservation_integrity=(
                ReservationIntegrityState.DUPLICATE_ACTIVE_RESERVATION
                if duplicate_candidate_id is not None
                else ReservationIntegrityState.OK
            ),
            duplicate_candidate_id=duplicate_candidate_id,
        ),
        account.open_risk_pct + legacy_fingerprint_reserved,
        excluded_id,
    )


def pure_kill_switch_from_live(state: Any) -> PureKillSwitchInput:
    return PureKillSwitchInput(
        state=KillSwitchInputState(state.state),
        reason_th=state.reason_th if state.state == "ACTIVE" else "",
        source=state.activated_by,
        state_id=state.id,
    )


def build_live_pure_input(
    *,
    as_of,
    candidate: SetupCandidate,
    plan: TradePlanSuggestion,
    account: AccountSnapshot,
    policy: RiskPolicy,
    spec: SymbolSpecification,
    quote: PureQuoteState,
    news: PureNewsState,
    kill_switch: PureKillSwitchInput,
    data_health_state: DataHealthInputState,
    data_health_provider: str,
    data_health_source: str,
    data_health_failures: int,
    caller_requested_risk_pct: Decimal | None,
    portfolio: PortfolioExposureSnapshot,
    candidate_lifecycle_status: str | None,
    candidate_transition_count: int,
) -> PureRiskEvaluationInput:
    return PureRiskEvaluationInput(
        as_of=as_of,
        candidate=candidate,
        trade_plan=plan,
        account=account,
        policy=policy,
        symbol_specification=spec,
        quote=quote,
        news=news,
        kill_switch=kill_switch,
        data_health=PureDataHealthInput(
            state=data_health_state,
            provider=data_health_provider,
            source=data_health_source,
            consecutive_failures=max(0, data_health_failures),
            threshold=policy.data_health_consecutive_failures,
        ),
        candidate_lifecycle_status=candidate_lifecycle_status or candidate.status,
        candidate_transition_count=candidate_transition_count,
        caller_requested_risk_pct=caller_requested_risk_pct,
        portfolio=portfolio,
    )


def quote_stale_evidence(result: PureRiskResult) -> tuple[bool, str]:
    stale_states = {
        MarketSafetyState.UNAVAILABLE,
        MarketSafetyState.STALE,
        MarketSafetyState.SPREAD_BLOCKED,
    }
    is_stale = result.safety_trigger_facts.quote_safety_state in stale_states
    if not is_stale:
        return False, ""
    quote_codes = {
        PureRiskCode.QUOTE_UNAVAILABLE,
        PureRiskCode.QUOTE_STALE,
        PureRiskCode.SPREAD_EXCESSIVE,
    }
    for code, reason in zip(result.blocked_codes, result.blocked_reasons_th, strict=False):
        if code in quote_codes:
            return True, reason
    return True, "ข้อมูลราคาตลาดไม่ผ่านเกณฑ์ความปลอดภัย"
