"""Side-effect-free deterministic Risk policy evaluation."""

import datetime as dt
from decimal import Decimal
from typing import NamedTuple

from app.services.risk.domain import MarketProvenance, NewsEventAudit, NewsRiskProvenance
from app.services.risk.policy_domain import (
    DataHealthInputState,
    KillSwitchInputState,
    MarketSafetyState,
    NewsAvailability,
    PortfolioExposureSnapshot,
    PureRiskCode,
    PureRiskEvaluationInput,
    PureRiskResult,
    QuoteAvailability,
    ReservationIntegrityState,
    SafetyTriggerFacts,
)
from app.services.risk.policy_fingerprint import compute_pure_risk_fingerprint
from app.services.risk.sizing import SizingResult, calculate_position_size

ZERO = Decimal("0")


class CapacityResult(NamedTuple):
    allowed: bool
    approved_risk_pct: Decimal
    approved_risk_amount: Decimal
    exposure_before: Decimal
    exposure_after: Decimal
    code: PureRiskCode | None
    reason_th: str | None
    is_reduced: bool


def is_pure_cooldown_active(
    account,
    policy,
    as_of: dt.datetime,
) -> tuple[bool, dt.datetime | None]:
    """Infrastructure-free equivalent of the live cooldown calculation."""
    effective_now = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=dt.UTC)
    cooldown_until = account.cooldown_until
    last_loss = account.last_loss_at

    if cooldown_until is not None and effective_now < cooldown_until:
        return True, cooldown_until

    if account.consecutive_losses >= policy.cooldown_consecutive_losses and last_loss is not None:
        calculated_until = last_loss + dt.timedelta(minutes=policy.cooldown_period_minutes)
        if cooldown_until is None or last_loss > cooldown_until or effective_now < calculated_until:
            if effective_now < calculated_until:
                return True, calculated_until

    return False, None


def _risk_amount(risk_pct: Decimal, equity: Decimal) -> Decimal:
    return (risk_pct / Decimal("100") * equity).quantize(Decimal("0.01"))


def _portfolio_capacity(
    exposure: PortfolioExposureSnapshot,
    policy,
    account,
    requested_risk_pct: Decimal,
    as_of: dt.datetime,
) -> CapacityResult:
    current_total = exposure.open_risk_pct + exposure.reserved_risk_pct

    in_cooldown, _ = is_pure_cooldown_active(account, policy, as_of)
    if in_cooldown:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.COOLDOWN_ACTIVE,
            "พอร์ตโฟลิโออยู่ในช่วงพักการเทรด (Cooldown Period) เนื่องจากขาดทุนต่อเนื่อง",
            False,
        )

    if exposure.reservation_integrity == ReservationIntegrityState.DUPLICATE_ACTIVE_RESERVATION:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.RESERVATION_DUPLICATE,
            (
                f"พบการจองความเสี่ยงซ้ำซ้อนสำหรับคำสั่ง {exposure.duplicate_candidate_id} "
                "(Duplicate Active Reservations Detected)"
            ),
            False,
        )
    if exposure.reservation_integrity == ReservationIntegrityState.UNKNOWN:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.RESERVATION_INTEGRITY_UNKNOWN,
            "ไม่สามารถยืนยันความถูกต้องของการจองความเสี่ยงได้ (Fail-closed)",
            False,
        )

    if exposure.open_risk_pct > ZERO:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.UNATTRIBUTED_OPEN_RISK,
            (
                "ไม่อนุมัติเนื่องจากมีสถานะเปิดความเสี่ยงคงค้างที่ไม่สามารถแจกแจงสัญลักษณ์/ทิศทางได้ "
                "(Open Risk Breakdown Unavailable)"
            ),
            False,
        )

    total_concurrent = exposure.active_reservation_count + exposure.open_position_count
    if total_concurrent >= policy.max_concurrent_trades:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.CONCURRENT_LIMIT,
            f"จำนวนคำสั่งที่รอการดำเนินการเต็มโควตา ({policy.max_concurrent_trades} รายการ)",
            False,
        )

    available_account = policy.max_account_risk_pct - current_total
    if available_account < policy.min_risk_per_trade_pct:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.ACCOUNT_CAPACITY,
            (
                f"พอร์ตโฟลิโอมีความเสี่ยงรวม {current_total:.2f}% "
                f"เต็มเพดานสูงสุด {policy.max_account_risk_pct:.2f}%"
            ),
            False,
        )

    available_symbol = policy.max_symbol_risk_pct - exposure.symbol_risk_pct
    if available_symbol < policy.min_risk_per_trade_pct:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.SYMBOL_CAPACITY,
            (
                f"ความเสี่ยงสะสมใน {exposure.symbol} ({exposure.symbol_risk_pct:.2f}%) "
                f"เต็มเพดานสัญลักษณ์ {policy.max_symbol_risk_pct:.2f}%"
            ),
            False,
        )

    available_direction = policy.max_directional_risk_pct - exposure.directional_risk_pct
    if available_direction < policy.min_risk_per_trade_pct:
        return CapacityResult(
            False,
            ZERO,
            ZERO,
            current_total,
            current_total,
            PureRiskCode.DIRECTIONAL_CAPACITY,
            (
                f"ความเสี่ยงฝั่ง {exposure.direction} ({exposure.directional_risk_pct:.2f}%) "
                f"เต็มเพดานทิศทาง {policy.max_directional_risk_pct:.2f}%"
            ),
            False,
        )

    target_risk = min(requested_risk_pct, policy.max_risk_per_trade_pct)
    bottleneck = min(available_account, available_symbol, available_direction)
    code: PureRiskCode | None = None
    reduction_reason: str | None = None

    if bottleneck < target_risk:
        if bottleneck >= policy.min_risk_per_trade_pct:
            approved_pct = bottleneck.quantize(Decimal("0.0001"))
            code = PureRiskCode.PORTFOLIO_REDUCTION
            reduction_reason = (
                f"ปรับลดความเสี่ยงเหลือ {approved_pct:.2f}% "
                "เนื่องจากข้อจำกัดเพดานความเสี่ยงคงเหลือในพอร์ต"
            )
        else:
            return CapacityResult(
                False,
                ZERO,
                ZERO,
                current_total,
                current_total,
                PureRiskCode.ACCOUNT_CAPACITY,
                "วงเงินความเสี่ยงที่เหลืออยู่ไม่เพียงพอสำหรับขนาดความเสี่ยงขั้นต่ำ",
                False,
            )
    else:
        approved_pct = target_risk.quantize(Decimal("0.0001"))
        if approved_pct < requested_risk_pct:
            code = PureRiskCode.PER_TRADE_REDUCTION
            reduction_reason = f"ปรับลดความเสี่ยงตามเพดานต่อคำสั่ง {policy.max_risk_per_trade_pct:.2f}%"

    approved_amount = _risk_amount(approved_pct, account.equity)
    return CapacityResult(
        True,
        approved_pct,
        approved_amount,
        current_total,
        current_total + approved_pct,
        code,
        reduction_reason,
        code is not None,
    )


def _news_evaluation(
    evaluation_input: PureRiskEvaluationInput,
    target_risk_pct: Decimal,
    warnings_th: list[str],
    warning_codes: list[PureRiskCode],
    blocked_reasons_th: list[str],
    blocked_codes: list[PureRiskCode],
) -> tuple[Decimal, bool, NewsRiskProvenance | None]:
    policy = evaluation_input.policy
    news = evaluation_input.news
    as_of = evaluation_input.as_of
    if not policy.news_risk_enabled:
        return target_risk_pct, False, None

    if news.availability == NewsAvailability.UNAVAILABLE:
        description = "ไม่สามารถประเมินความเสี่ยงข่าวได้ (News Provider Unavailable / Stale)"
        blocked_reasons_th.append(description)
        blocked_codes.append(PureRiskCode.NEWS_UNAVAILABLE)
        return target_risk_pct, False, NewsRiskProvenance(
            news_state="UNAVAILABLE",
            in_blackout=False,
            in_pre_news_window=False,
            in_post_news_window=False,
            event_ids=(),
            description_th=description,
            provider=news.provider,
            source=news.source,
            revision_id=news.revision_id,
            revision_version=news.revision_version,
        )

    blackout_pre = dt.timedelta(minutes=policy.news_high_impact_blackout_pre_minutes)
    window_pre = dt.timedelta(minutes=policy.news_high_impact_pre_minutes)
    window_post = dt.timedelta(minutes=policy.news_high_impact_post_minutes)
    in_blackout = False
    in_pre = False
    in_post = False
    relevant_event_ids: list[str] = []

    for event in news.events:
        if event.impact != "HIGH":
            continue
        if event.scheduled_at - blackout_pre <= as_of <= event.scheduled_at:
            in_blackout = True
            relevant_event_ids.append(event.event_id)
        elif event.scheduled_at - window_pre <= as_of < event.scheduled_at:
            in_pre = True
            relevant_event_ids.append(event.event_id)
        elif event.scheduled_at < as_of <= event.scheduled_at + window_post:
            in_post = True
            relevant_event_ids.append(event.event_id)

    description = "สภาวะข่าวปกติ"
    news_reduced = False
    if in_blackout:
        description = "อยู่ในช่วงห้ามเทรดก่อนประกาศข่าวสำคัญ (News Blackout)"
        blocked_reasons_th.append(
            "ไม่อนุมัติแผนเทรดเนื่องจากอยู่ในช่วงเวลาก่อนประกาศข่าว High-Impact (Blackout Window)"
        )
        blocked_codes.append(PureRiskCode.NEWS_BLACKOUT)
    elif in_pre:
        reduction_pct = (policy.news_reduction_factor * Decimal("100")).quantize(Decimal("1"))
        description = f"ใกล้เวลาประกาศข่าวสำคัญ ปรับลดความเสี่ยงเหลือ {reduction_pct:.0f}%"
        warnings_th.append(description)
        warning_codes.append(PureRiskCode.NEWS_PRE_REDUCTION)
        target_risk_pct *= policy.news_reduction_factor
        news_reduced = True
    elif in_post:
        description = "ช่วงหลังข่าวประกาศ อยู่ระหว่างเฝ้าระวังสเปรดและความผันผวน"
        quote = evaluation_input.quote
        if quote.availability == QuoteAvailability.AVAILABLE and quote.spread > policy.max_spread_absolute * Decimal(
            "0.8"
        ):
            blocked_reasons_th.append("ไม่อนุมัติเนื่องจากสเปรดหลังประกาศข่าวยังไม่เสถียร")
            blocked_codes.append(PureRiskCode.NEWS_POST_SPREAD_BLOCKED)
        else:
            warnings_th.append(description)
            warning_codes.append(PureRiskCode.NEWS_POST_WARNING)

    events_audit = tuple(
        NewsEventAudit(
            event_id=event.event_id,
            event_name=event.event_name,
            currency=event.currency,
            impact=event.impact,
            scheduled_at=event.scheduled_at,
            available_at=event.available_at,
            window_state=(
                "BLACKOUT"
                if event.event_id in relevant_event_ids and in_blackout
                else (
                    "PRE"
                    if event.event_id in relevant_event_ids and in_pre
                    else ("POST" if event.event_id in relevant_event_ids and in_post else "CALM")
                )
            ),
            provider=event.provider or event.source or news.provider or news.source,
            source=event.source or event.provider or news.source or news.provider,
            revision_id=event.revision_id,
            revision_version=event.revision_version,
        )
        for event in news.events
    )
    if not news.events:
        description = "สภาวะข่าวปกติ ไม่มีเหตุการณ์สำคัญ"

    provenance = NewsRiskProvenance(
        news_state="EVENT_RISK_ACTIVE" if (in_blackout or in_pre or in_post) else "CALM",
        in_blackout=in_blackout,
        in_pre_news_window=in_pre,
        in_post_news_window=in_post,
        event_ids=tuple(relevant_event_ids),
        description_th=description,
        events=events_audit,
        provider=news.provider or news.source or (events_audit[0].provider if events_audit else ""),
        source=news.source or news.provider or (events_audit[0].source if events_audit else ""),
        revision_id=news.revision_id or (events_audit[0].revision_id if events_audit else ""),
        revision_version=news.revision_version or (events_audit[0].revision_version if events_audit else None),
    )
    return target_risk_pct, news_reduced, provenance


def evaluate_pure_risk(evaluation_input: PureRiskEvaluationInput) -> PureRiskResult:
    """Evaluate Risk policy using only explicit immutable input state."""
    account = evaluation_input.account
    policy = evaluation_input.policy
    spec = evaluation_input.symbol_specification
    plan = evaluation_input.trade_plan
    as_of = evaluation_input.as_of
    caller_requested = evaluation_input.caller_requested_risk_pct
    normalized_requested = (
        policy.max_risk_per_trade_pct if caller_requested is None or caller_requested == ZERO else caller_requested
    )
    target_risk = normalized_requested
    normalized_amount = _risk_amount(normalized_requested, account.equity)

    reasons_th: list[str] = []
    warnings_th: list[str] = []
    blocked_reasons_th: list[str] = []
    reason_codes: list[PureRiskCode] = []
    warning_codes: list[PureRiskCode] = []
    blocked_codes: list[PureRiskCode] = []

    market_provenance: MarketProvenance | None = None
    quote_is_stale = False
    quote_stale_reason = ""
    quote_safety_state = MarketSafetyState.AVAILABLE_SAFE
    quote = evaluation_input.quote
    if quote.availability == QuoteAvailability.UNAVAILABLE:
        quote_is_stale = True
        quote_safety_state = MarketSafetyState.UNAVAILABLE
        quote_stale_reason = "ไม่พบข้อมูลราคาตลาดล่าสุด (Market Quote Unavailable)"
    else:
        quote_age = (as_of - quote.timestamp).total_seconds()
        quote_is_stale = quote_age > policy.quote_freshness_seconds
        if quote_is_stale:
            quote_safety_state = MarketSafetyState.STALE
            quote_stale_reason = f"ราคาตลาดล้าสมัย ({quote_age:.1f}s > {policy.quote_freshness_seconds}s)"
        elif quote.spread > policy.max_spread_absolute:
            quote_is_stale = True
            quote_safety_state = MarketSafetyState.SPREAD_BLOCKED
            quote_stale_reason = f"ค่าสเปรด (${quote.spread:.2f}) สูงกว่าเพดาน (${policy.max_spread_absolute:.2f})"
        market_provenance = MarketProvenance(
            source=quote.source,
            mode=quote.mode,
            quote_timestamp=quote.timestamp,
            quote_bid=quote.bid,
            quote_ask=quote.ask,
            quote_spread=quote.spread,
            is_stale=quote_is_stale,
        )

    daily_loss_breach = False
    if account.daily_realized_pnl < ZERO:
        daily_loss_breach = abs(account.daily_realized_pnl) >= (
            policy.daily_loss_limit_pct / Decimal("100") * account.equity
        )
    weekly_loss_breach = False
    if account.weekly_realized_pnl < ZERO:
        weekly_loss_breach = abs(account.weekly_realized_pnl) >= (
            policy.weekly_loss_limit_pct / Decimal("100") * account.equity
        )
    drawdown_breach = False
    if account.peak_equity > ZERO and account.equity < account.peak_equity:
        drawdown_breach = (
            (account.peak_equity - account.equity) / account.peak_equity * Decimal("100")
            >= policy.max_drawdown_pct
        )

    if evaluation_input.kill_switch.state == KillSwitchInputState.ACTIVE:
        reason = "ไม่อนุมัติเนื่องจาก Kill Switch ทำงาน"
        if evaluation_input.kill_switch.reason_th:
            reason += f" ({evaluation_input.kill_switch.reason_th})"
        blocked_reasons_th.append(reason)
        blocked_codes.append(PureRiskCode.KILL_SWITCH_ACTIVE)
    elif evaluation_input.kill_switch.state == KillSwitchInputState.UNKNOWN:
        blocked_reasons_th.append("ไม่อนุมัติเนื่องจากไม่สามารถยืนยันสถานะ Kill Switch ได้ (Fail-closed)")
        blocked_codes.append(PureRiskCode.KILL_SWITCH_UNKNOWN)

    if evaluation_input.data_health.state == DataHealthInputState.TRIGGERED:
        blocked_reasons_th.append(
            evaluation_input.data_health.reason_th
            or "ไม่อนุมัติเนื่องจากสถานะสุขภาพข้อมูลถึงเกณฑ์ความปลอดภัย"
        )
        blocked_codes.append(PureRiskCode.DATA_HEALTH_TRIGGERED)
    elif evaluation_input.data_health.state == DataHealthInputState.UNKNOWN:
        blocked_reasons_th.append("ไม่อนุมัติเนื่องจากไม่สามารถยืนยันสถานะสุขภาพข้อมูลได้ (Fail-closed)")
        blocked_codes.append(PureRiskCode.DATA_HEALTH_UNKNOWN)

    target_risk, news_reduced, news_provenance = _news_evaluation(
        evaluation_input,
        target_risk,
        warnings_th,
        warning_codes,
        blocked_reasons_th,
        blocked_codes,
    )

    if news_provenance and news_provenance.in_post_news_window and not quote_is_stale:
        if quote.availability == QuoteAvailability.AVAILABLE and quote.spread > policy.max_spread_absolute * Decimal(
            "0.8"
        ):
            quote_safety_state = MarketSafetyState.POST_NEWS_SPREAD_BLOCKED

    effective_status = evaluation_input.candidate_lifecycle_status
    if effective_status in {"INVALIDATED", "EXPIRED", "SUPERSEDED"}:
        blocked_reasons_th.append(
            f"สถานะ Trade Candidate อยู่ในสถานะสิ้นสุด ({effective_status}) ไม่สามารถประเมินความเสี่ยงได้"
        )
        blocked_codes.append(PureRiskCode.CANDIDATE_TERMINAL)

    account_age = (as_of - account.as_of).total_seconds()
    if account_age > policy.account_freshness_seconds:
        blocked_reasons_th.append(
            f"ข้อมูลบัญชีล้าสมัย (Snapshot อายุ {account_age:.0f} วินาที "
            f"เกินเพดาน {policy.account_freshness_seconds} วินาที)"
        )
        blocked_codes.append(PureRiskCode.ACCOUNT_STALE)
    if account.equity <= ZERO:
        blocked_reasons_th.append("มูลค่าสุทธิของบัญชี (Equity) ต้องมากกว่า 0")
        blocked_codes.append(PureRiskCode.EQUITY_NON_POSITIVE)
    if daily_loss_breach:
        loss = abs(account.daily_realized_pnl)
        maximum = policy.daily_loss_limit_pct / Decimal("100") * account.equity
        blocked_reasons_th.append(
            f"การขาดทุนสะสมรายวัน (${loss:.2f}) ถึงเพดานจำกัดความเสี่ยง "
            f"({policy.daily_loss_limit_pct:.1f}% หรือ ${maximum:.2f})"
        )
        blocked_codes.append(PureRiskCode.DAILY_LOSS_LIMIT)
    if weekly_loss_breach:
        loss = abs(account.weekly_realized_pnl)
        maximum = policy.weekly_loss_limit_pct / Decimal("100") * account.equity
        blocked_reasons_th.append(
            f"การขาดทุนสะสมรายสัปดาห์ (${loss:.2f}) ถึงเพดานจำกัดความเสี่ยง "
            f"({policy.weekly_loss_limit_pct:.1f}% หรือ ${maximum:.2f})"
        )
        blocked_codes.append(PureRiskCode.WEEKLY_LOSS_LIMIT)
    if drawdown_breach:
        drawdown = (account.peak_equity - account.equity) / account.peak_equity * Decimal("100")
        blocked_reasons_th.append(
            f"ระดับ Drawdown ปัจจุบัน ({drawdown:.2f}%) ถึงเพดานสูงสุดที่อนุญาต "
            f"({policy.max_drawdown_pct:.1f}%)"
        )
        blocked_codes.append(PureRiskCode.DRAWDOWN_LIMIT)

    in_cooldown, _ = is_pure_cooldown_active(account, policy, as_of)
    if in_cooldown:
        blocked_reasons_th.append(
            f"บัญชีอยู่ในช่วงพักการเทรด (Cooldown) เนื่องจากขาดทุนต่อเนื่อง {account.consecutive_losses} ครั้ง"
        )
        blocked_codes.append(PureRiskCode.COOLDOWN_ACTIVE)

    if spec.tick_size <= ZERO or spec.tick_value <= ZERO or spec.contract_size <= ZERO:
        blocked_reasons_th.append("ข้อมูลสเปกสัญลักษณ์ (Symbol Specification) ไม่สมบูรณ์หรือไม่ถูกต้อง")
        blocked_codes.append(PureRiskCode.SYMBOL_SPEC_INVALID)
    spec_age = (as_of - spec.observed_at).total_seconds()
    if spec_age > policy.symbol_spec_freshness_seconds:
        blocked_reasons_th.append(
            f"ข้อมูลสเปกสัญลักษณ์ล้าสมัย (SymbolSpec อายุ {spec_age:.0f}s > "
            f"{policy.symbol_spec_freshness_seconds}s)"
        )
        blocked_codes.append(PureRiskCode.SYMBOL_SPEC_STALE)
    if account.open_risk_pct > ZERO:
        blocked_reasons_th.append(
            "ไม่อนุมัติเนื่องจากมีสถานะเปิดความเสี่ยงคงค้างที่ไม่สามารถแจกแจงสัญลักษณ์/ทิศทางได้ "
            "(Open Risk Breakdown Unavailable)"
        )
        blocked_codes.append(PureRiskCode.UNATTRIBUTED_OPEN_RISK)
    if quote_is_stale:
        blocked_reasons_th.append(quote_stale_reason)
        blocked_codes.append(
            PureRiskCode.QUOTE_UNAVAILABLE
            if quote.availability == QuoteAvailability.UNAVAILABLE
            else (
                PureRiskCode.QUOTE_STALE
                if quote_safety_state == MarketSafetyState.STALE
                else PureRiskCode.SPREAD_EXCESSIVE
            )
        )
    if plan.status != "SUGGESTION_ONLY":
        blocked_reasons_th.append("สถานะแผนเทรดไม่ถูกต้อง ต้องเป็น SUGGESTION_ONLY")
        blocked_codes.append(PureRiskCode.PLAN_STATUS_INVALID)
    if plan.expires_at <= as_of:
        blocked_reasons_th.append("แผนเทรดหมดอายุความถูกต้องแล้ว (Plan Expired)")
        blocked_codes.append(PureRiskCode.PLAN_EXPIRED)

    payload, semantic_fingerprint = compute_pure_risk_fingerprint(
        evaluation_input,
        normalized_requested,
        target_risk,
    )
    target_amount = _risk_amount(target_risk, account.equity)
    exposure_before = evaluation_input.portfolio.open_risk_pct + evaluation_input.portfolio.reserved_risk_pct
    safety_facts = SafetyTriggerFacts(
        daily_loss_breach=daily_loss_breach,
        weekly_loss_breach=weekly_loss_breach,
        drawdown_breach=drawdown_breach,
        quote_safety_state=quote_safety_state,
        data_health_state=evaluation_input.data_health.state,
    )

    def result(
        *,
        decision: str,
        approved_risk_pct: Decimal = ZERO,
        approved_risk_amount: Decimal = ZERO,
        position_size: Decimal = ZERO,
        stop_distance: Decimal | None = None,
        loss_per_lot: Decimal = ZERO,
        exposure_after: Decimal | None = None,
    ) -> PureRiskResult:
        output_exposure_before = account.open_risk_pct if decision == "BLOCKED" else exposure_before
        if stop_distance is None:
            stop_distance = (
                abs(Decimal(str(plan.entry_upper)) - Decimal(str(plan.stop_loss)))
                if plan.direction == "LONG"
                else abs(Decimal(str(plan.entry_lower)) - Decimal(str(plan.stop_loss)))
            )
        return PureRiskResult(
            decision=decision,
            caller_requested_risk_pct=caller_requested,
            normalized_requested_risk_pct=normalized_requested,
            target_risk_pct=target_risk,
            approved_risk_pct=approved_risk_pct if decision != "BLOCKED" else ZERO,
            normalized_requested_risk_amount=normalized_amount,
            target_risk_amount=target_amount,
            approved_risk_amount=approved_risk_amount if decision != "BLOCKED" else ZERO,
            position_size=position_size if decision != "BLOCKED" else ZERO,
            stop_distance=stop_distance,
            loss_per_lot=loss_per_lot,
            portfolio_exposure_before=output_exposure_before,
            portfolio_exposure_after=(
                output_exposure_before
                if exposure_after is None or decision == "BLOCKED"
                else exposure_after
            ),
            reason_codes=tuple(reason_codes),
            warning_codes=tuple(warning_codes),
            blocked_codes=tuple(blocked_codes),
            reasons_th=tuple(reasons_th),
            warnings_th=tuple(warnings_th),
            blocked_reasons_th=tuple(blocked_reasons_th),
            market_provenance=market_provenance,
            news_provenance=news_provenance,
            safety_trigger_facts=safety_facts,
            semantic_payload=payload,
            semantic_fingerprint=semantic_fingerprint,
        )

    if blocked_reasons_th:
        reasons_th.append("การตรวจสอบเบื้องต้นไม่ผ่านเกณฑ์ความปลอดภัยของ Risk Policy")
        return result(decision="BLOCKED")

    capacity = _portfolio_capacity(
        evaluation_input.portfolio,
        policy,
        account,
        target_risk,
        as_of,
    )
    exposure_before = capacity.exposure_before
    if not capacity.allowed:
        blocked_codes.append(capacity.code)
        blocked_reasons_th.append(capacity.reason_th or "วงเงินความเสี่ยงพอร์ตโฟลิโอไม่เพียงพอ")
        reasons_th.append("ความเสี่ยงรวมของพอร์ตโฟลิโอเกินเกณฑ์ที่กำหนด")
        return result(decision="BLOCKED")

    sizing: SizingResult = calculate_position_size(
        direction=plan.direction,
        entry_lower=Decimal(str(plan.entry_lower)),
        entry_upper=Decimal(str(plan.entry_upper)),
        stop_loss=Decimal(str(plan.stop_loss)),
        approved_risk_amount=capacity.approved_risk_amount,
        account_equity=account.equity,
        spec=spec,
    )
    if not sizing.is_valid:
        blocked_codes.append(PureRiskCode.POSITION_SIZING_FAILED)
        blocked_reasons_th.append(sizing.error_th or "การคำนวณขนาดสัญญาขั้นสุดท้ายไม่ผ่าน")
        reasons_th.append("ไม่สามารถจัดสรรขนาดสัญญาให้สอดคล้องกับงบความเสี่ยงที่ได้รับการอนุมัติ")
        return result(
            decision="BLOCKED",
            loss_per_lot=sizing.loss_per_lot,
        )

    decision = "REDUCED" if capacity.is_reduced or news_reduced else "APPROVED"
    if decision == "APPROVED":
        reason_codes.append(PureRiskCode.APPROVED)
        reasons_th.append(
            f"อนุมัติแผนเทรดตามปกติ ขนาดความเสี่ยง {capacity.approved_risk_pct:.2f}% "
            f"(${capacity.approved_risk_amount:.2f})"
        )
    else:
        reason_codes.append(PureRiskCode.APPROVED_REDUCED)
        reasons_th.append(
            f"อนุมัติแบบลดความเสี่ยงเหลือ {capacity.approved_risk_pct:.2f}% "
            f"(${capacity.approved_risk_amount:.2f})"
        )
        if capacity.reason_th:
            warnings_th.append(capacity.reason_th)
            warning_codes.append(capacity.code)
    reason_codes.append(PureRiskCode.POSITION_SIZED)
    reasons_th.append(f"ขนาดสัญญาที่ปลอดภัย: {sizing.position_size} lot (ระยะ Stop: {sizing.stop_distance:.2f})")
    return result(
        decision=decision,
        approved_risk_pct=capacity.approved_risk_pct,
        approved_risk_amount=capacity.approved_risk_amount,
        position_size=sizing.position_size,
        stop_distance=sizing.stop_distance,
        loss_per_lot=sizing.loss_per_lot,
        exposure_after=capacity.exposure_after,
    )
