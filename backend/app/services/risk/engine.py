"""Phase 5 Risk Engine: evaluates TradePlan against RiskPolicy, Account, Portfolio, and News.

Fail closed: missing/stale metadata or active Kill Switch always produces BLOCKED.
Never changes TradePlan geometry, Setup Score, or direction.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_data.domain import Quote
from app.services.news.domain import NewsStrategyContext
from app.services.risk.domain import (
    AccountSnapshot,
    Direction,
    MarketProvenance,
    NewsRiskProvenance,
    RiskDecision,
    RiskPolicy,
    SymbolSpecification,
)
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.portfolio import portfolio_manager
from app.services.risk.sizing import calculate_position_size
from app.services.strategy.domain import SetupCandidate, TradePlanSuggestion


class RiskEngine:
    async def evaluate_candidate(
        self,
        session: AsyncSession,
        candidate: SetupCandidate,
        plan: TradePlanSuggestion,
        account: AccountSnapshot,
        policy: RiskPolicy,
        spec: SymbolSpecification,
        quote: Quote | None,
        news_context: NewsStrategyContext | None = None,
        requested_risk_pct: Decimal | None = None,
        as_of: dt.datetime | None = None,
    ) -> RiskDecision:
        now = as_of or dt.datetime.now(dt.UTC)
        decision_id = f"dec_{uuid.uuid4().hex[:24]}"
        reasons_th: list[str] = []
        warnings_th: list[str] = []
        blocked_reasons_th: list[str] = []

        direction: Direction = plan.direction
        entry_lower = Decimal(str(plan.entry_lower))
        entry_upper = Decimal(str(plan.entry_upper))
        stop_loss = Decimal(str(plan.stop_loss))

        # Market provenance tracking
        market_prov = None
        if quote:
            market_prov = MarketProvenance(
                source=quote.source,
                mode=quote.mode,
                quote_timestamp=quote.timestamp,
                quote_bid=quote.bid,
                quote_ask=quote.ask,
                quote_spread=quote.spread,
                is_stale=(now - quote.timestamp).total_seconds() > policy.quote_freshness_seconds,
            )

        # -------------------------------------------------------------
        # 1. FAIL CLOSED GATE: Kill Switch
        # -------------------------------------------------------------
        ks_check = await kill_switch_manager.check(session)
        if ks_check.is_active:
            blocked_reasons_th.append(ks_check.blocked_reason_th or "ไม่อนุมัติเนื่องจาก Kill Switch ทำงาน")
            return self._blocked_decision(
                decision_id=decision_id,
                candidate=candidate,
                plan=plan,
                account=account,
                policy=policy,
                spec=spec,
                now=now,
                market_prov=market_prov,
                blocked_reasons=blocked_reasons_th,
                reasons=["การประเมินถูกปฏิเสธโดยระบบ Kill Switch ฉุกเฉิน"],
            )

        # -------------------------------------------------------------
        # 2. FAIL CLOSED GATE: Account Health & Freshness
        # -------------------------------------------------------------
        if (now - account.as_of).total_seconds() > policy.account_freshness_seconds:
            age_sec = (now - account.as_of).total_seconds()
            blocked_reasons_th.append(
                f"ข้อมูลบัญชีล้าสมัย (Snapshot อายุ {age_sec:.0f} วินาที เกินเพดาน {policy.account_freshness_seconds} วินาที)"
            )

        if account.equity <= Decimal("0"):
            blocked_reasons_th.append("มูลค่าสุทธิของบัญชี (Equity) ต้องมากกว่า 0")

        # Daily loss limit check
        daily_loss_amount = Decimal("0")
        if account.daily_realized_pnl < Decimal("0"):
            daily_loss_amount = abs(account.daily_realized_pnl)
            max_daily_loss = (policy.daily_loss_limit_pct / Decimal("100")) * account.equity
            if daily_loss_amount >= max_daily_loss:
                blocked_reasons_th.append(
                    f"การขาดทุนสะสมรายวัน (${daily_loss_amount:.2f}) ถึงเพดานจำกัดความเสี่ยง "
                    f"({policy.daily_loss_limit_pct:.1f}% หรือ ${max_daily_loss:.2f})"
                )

        # Weekly loss limit check
        if account.weekly_realized_pnl < Decimal("0"):
            weekly_loss_amount = abs(account.weekly_realized_pnl)
            max_weekly_loss = (policy.weekly_loss_limit_pct / Decimal("100")) * account.equity
            if weekly_loss_amount >= max_weekly_loss:
                blocked_reasons_th.append(
                    f"การขาดทุนสะสมรายสัปดาห์ (${weekly_loss_amount:.2f}) ถึงเพดานจำกัดความเสี่ยง "
                    f"({policy.weekly_loss_limit_pct:.1f}% หรือ ${max_weekly_loss:.2f})"
                )

        # Maximum drawdown check
        if account.peak_equity > Decimal("0") and account.equity < account.peak_equity:
            dd_pct = ((account.peak_equity - account.equity) / account.peak_equity) * Decimal("100")
            if dd_pct >= policy.max_drawdown_pct:
                blocked_reasons_th.append(
                    f"ระดับ Drawdown ปัจจุบัน ({dd_pct:.2f}%) ถึงเพดานสูงสุดที่อนุญาต ({policy.max_drawdown_pct:.1f}%)"
                )

        # Cooldown check
        if account.consecutive_losses >= policy.cooldown_consecutive_losses:
            blocked_reasons_th.append(
                f"บัญชีอยู่ในช่วงพักการเทรด (Cooldown) เนื่องจากขาดทุนต่อเนื่อง {account.consecutive_losses} ครั้ง"
            )

        # -------------------------------------------------------------
        # 3. FAIL CLOSED GATE: Symbol Spec & Market Quote
        # -------------------------------------------------------------
        if spec.tick_size <= Decimal("0") or spec.tick_value <= Decimal("0") or spec.contract_size <= Decimal("0"):
            blocked_reasons_th.append("ข้อมูลสเปกสัญลักษณ์ (Symbol Specification) ไม่สมบูรณ์หรือไม่ถูกต้อง")

        if quote is None:
            blocked_reasons_th.append("ไม่พบข้อมูลราคาตลาดล่าสุด (Market Quote Unavailable)")
        else:
            quote_age = (now - quote.timestamp).total_seconds()
            if quote_age > policy.quote_freshness_seconds:
                blocked_reasons_th.append(
                    f"ราคาตลาดล้าสมัย (Quote อายุ {quote_age:.1f} วินาที เกินเกณฑ์ {policy.quote_freshness_seconds} วินาที)"
                )
            if quote.spread > policy.max_spread_absolute:
                blocked_reasons_th.append(
                    f"ค่าสเปรด (${quote.spread:.2f}) สูงกว่าเพดานสูงสุด (${policy.max_spread_absolute:.2f})"
                )

        # -------------------------------------------------------------
        # 4. FAIL CLOSED GATE: TradePlan Validation
        # -------------------------------------------------------------
        if plan.status != "SUGGESTION_ONLY":
            blocked_reasons_th.append("สถานะแผนเทรดไม่ถูกต้อง ต้องเป็น SUGGESTION_ONLY")

        if plan.expires_at <= now:
            blocked_reasons_th.append("แผนเทรดหมดอายุความถูกต้องแล้ว (Plan Expired)")

        if blocked_reasons_th:
            return self._blocked_decision(
                decision_id=decision_id,
                candidate=candidate,
                plan=plan,
                account=account,
                policy=policy,
                spec=spec,
                now=now,
                market_prov=market_prov,
                blocked_reasons=blocked_reasons_th,
                reasons=["การตรวจสอบเบื้องต้นไม่ผ่านเกณฑ์ความปลอดภัยของ Risk Policy"],
            )

        # -------------------------------------------------------------
        # 5. INDEPENDENT NEWS RISK CHECK
        # -------------------------------------------------------------
        news_prov = None
        news_reduced = False
        target_risk_pct = requested_risk_pct or policy.max_risk_per_trade_pct

        if policy.news_risk_enabled and news_context and news_context.events:
            blackout_pre = dt.timedelta(minutes=policy.news_high_impact_blackout_pre_minutes)
            window_pre = dt.timedelta(minutes=policy.news_high_impact_pre_minutes)
            window_post = dt.timedelta(minutes=policy.news_high_impact_post_minutes)

            in_blackout = False
            in_pre = False
            in_post = False
            relevant_event_ids: list[str] = []

            for event in news_context.events:
                if event.impact == "HIGH":
                    # Blackout: e.g. 5m before release
                    if event.scheduled_at - blackout_pre <= now <= event.scheduled_at:
                        in_blackout = True
                        relevant_event_ids.append(event.id)
                    # Pre-news window: e.g. 15m before release
                    elif event.scheduled_at - window_pre <= now < event.scheduled_at:
                        in_pre = True
                        relevant_event_ids.append(event.id)
                    # Post-news window: e.g. 15m after release
                    elif event.scheduled_at < now <= event.scheduled_at + window_post:
                        in_post = True
                        relevant_event_ids.append(event.id)

            desc = "สภาวะข่าวปกติ"
            if in_blackout:
                desc = "อยู่ในช่วงห้ามเทรดก่อนประกาศข่าวสำคัญ (News Blackout)"
                blocked_reasons_th.append("ไม่อนุมัติแผนเทรดเนื่องจากอยู่ในช่วงเวลาก่อนประกาศข่าว High-Impact (Blackout Window)")
            elif in_pre:
                desc = f"ใกล้เวลาประกาศข่าวสำคัญ ปรับลดความเสี่ยงเหลือ {policy.news_reduction_factor * Decimal('100'):.0f}%"
                warnings_th.append(desc)
                target_risk_pct = target_risk_pct * policy.news_reduction_factor
                news_reduced = True
            elif in_post:
                desc = "ช่วงหลังข่าวประกาศ อยู่ระหว่างเฝ้าระวังสเปรดและความผันผวน"
                if quote and quote.spread > policy.max_spread_absolute * Decimal("0.8"):
                    blocked_reasons_th.append("ไม่อนุมัติเนื่องจากสเปรดหลังประกาศข่าวยังไม่เสถียร")
                else:
                    warnings_th.append(desc)

            news_prov = NewsRiskProvenance(
                news_state="EVENT_RISK_ACTIVE" if (in_blackout or in_pre or in_post) else "CALM",
                in_blackout=in_blackout,
                in_pre_news_window=in_pre,
                in_post_news_window=in_post,
                event_ids=tuple(relevant_event_ids),
                description_th=desc,
            )

            if blocked_reasons_th:
                return self._blocked_decision(
                    decision_id=decision_id,
                    candidate=candidate,
                    plan=plan,
                    account=account,
                    policy=policy,
                    spec=spec,
                    now=now,
                    market_prov=market_prov,
                    news_prov=news_prov,
                    blocked_reasons=blocked_reasons_th,
                    reasons=["การอนุมัติถูกระงับเนื่องจากความเสี่ยงทางเศรษฐกิจ/ข่าวสาร"],
                )

        # -------------------------------------------------------------
        # 6. PORTFOLIO BUDGET & ATOMIC RESERVATION
        # -------------------------------------------------------------
        # Preliminary position sizing with requested risk to test sizing feasibility
        initial_risk_amount = (target_risk_pct / Decimal("100") * account.equity).quantize(Decimal("0.01"))
        prelim_sizing = calculate_position_size(
            direction=direction,
            entry_lower=entry_lower,
            entry_upper=entry_upper,
            stop_loss=stop_loss,
            approved_risk_amount=initial_risk_amount,
            account_equity=account.equity,
            spec=spec,
        )
        if not prelim_sizing.is_valid:
            blocked_reasons_th.append(prelim_sizing.error_th or "การคำนวณขนาดสัญญาเบื้องต้นไม่ผ่านเกณฑ์")
            return self._blocked_decision(
                decision_id=decision_id,
                candidate=candidate,
                plan=plan,
                account=account,
                policy=policy,
                spec=spec,
                now=now,
                market_prov=market_prov,
                news_prov=news_prov,
                blocked_reasons=blocked_reasons_th,
                reasons=["ไม่สามารถกำหนดขนาดสัญญาที่ปลอดภัยได้"],
            )

        budget_check = await portfolio_manager.check_budget_and_reserve(
            session=session,
            account=account,
            policy=policy,
            symbol=candidate.symbol,
            direction=direction,
            requested_risk_pct=target_risk_pct,
            profile_id=candidate.profile_id,
            decision_id=decision_id,
            position_size=prelim_sizing.position_size,
            now=now,
        )

        if not budget_check.allowed:
            blocked_reasons_th.append(budget_check.reason_th or "วงเงินความเสี่ยงพอร์ตโฟลิโอไม่เพียงพอ")
            return self._blocked_decision(
                decision_id=decision_id,
                candidate=candidate,
                plan=plan,
                account=account,
                policy=policy,
                spec=spec,
                now=now,
                market_prov=market_prov,
                news_prov=news_prov,
                blocked_reasons=blocked_reasons_th,
                reasons=["ความเสี่ยงรวมของพอร์ตโฟลิโอเกินเกณฑ์ที่กำหนด"],
            )

        # Recalculate exact position size with the final approved risk amount
        approved_pct = budget_check.approved_risk_pct
        approved_amount = budget_check.approved_risk_amount

        final_sizing = calculate_position_size(
            direction=direction,
            entry_lower=entry_lower,
            entry_upper=entry_upper,
            stop_loss=stop_loss,
            approved_risk_amount=approved_amount,
            account_equity=account.equity,
            spec=spec,
        )

        if not final_sizing.is_valid:
            blocked_reasons_th.append(final_sizing.error_th or "การคำนวณขนาดสัญญาขั้นสุดท้ายไม่ผ่าน")
            return self._blocked_decision(
                decision_id=decision_id,
                candidate=candidate,
                plan=plan,
                account=account,
                policy=policy,
                spec=spec,
                now=now,
                market_prov=market_prov,
                news_prov=news_prov,
                blocked_reasons=blocked_reasons_th,
                reasons=["ไม่สามารถจัดสรรขนาดสัญญาให้สอดคล้องกับงบความเสี่ยงที่ได้รับการอนุมัติ"],
            )

        # Successful decision (APPROVED or REDUCED)
        decision_type = "REDUCED" if (budget_check.is_reduced or news_reduced) else "APPROVED"

        if decision_type == "APPROVED":
            reasons_th.append(
                f"อนุมัติแผนเทรดตามปกติ ขนาดความเสี่ยง {approved_pct:.2f}% (${approved_amount:.2f})"
            )
        else:
            reasons_th.append(
                f"อนุมัติแบบลดความเสี่ยงเหลือ {approved_pct:.2f}% (${approved_amount:.2f})"
            )
            if budget_check.reason_th:
                warnings_th.append(budget_check.reason_th)

        reasons_th.append(
            f"ขนาดสัญญาที่ปลอดภัย: {final_sizing.position_size} lot (ระยะ Stop: {final_sizing.stop_distance:.2f})"
        )

        return RiskDecision(
            id=decision_id,
            candidate_id=candidate.id,
            plan_id=plan.id,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            profile_id=candidate.profile_id,
            symbol=candidate.symbol,
            direction=direction,
            decision=decision_type,
            requested_risk_pct=requested_risk_pct or policy.max_risk_per_trade_pct,
            approved_risk_pct=approved_pct,
            requested_risk_amount=(
                (requested_risk_pct or policy.max_risk_per_trade_pct) / Decimal("100") * account.equity
            ).quantize(Decimal("0.01")),
            approved_risk_amount=approved_amount,
            position_size=final_sizing.position_size,
            entry_lower=entry_lower,
            entry_upper=entry_upper,
            stop_loss=stop_loss,
            stop_distance=final_sizing.stop_distance,
            portfolio_exposure_before=budget_check.portfolio_exposure_before,
            portfolio_exposure_after=budget_check.portfolio_exposure_after,
            account_snapshot_id=account.id,
            symbol_specification_id=spec.id,
            policy_version=policy.version,
            reasons_th=tuple(reasons_th),
            warnings_th=tuple(warnings_th),
            blocked_reasons_th=(),
            as_of=now,
            expires_at=min(plan.expires_at, now + dt.timedelta(seconds=policy.reservation_ttl_seconds)),
            market_provenance=market_prov,
            news_provenance=news_prov,
            execution_blocked="NO_EXECUTION_ANALYSIS_ONLY",
        )

    def _blocked_decision(
        self,
        decision_id: str,
        candidate: SetupCandidate,
        plan: TradePlanSuggestion,
        account: AccountSnapshot,
        policy: RiskPolicy,
        spec: SymbolSpecification,
        now: dt.datetime,
        market_prov: MarketProvenance | None,
        blocked_reasons: list[str],
        reasons: list[str],
        news_prov: NewsRiskProvenance | None = None,
    ) -> RiskDecision:
        entry_lower = Decimal(str(plan.entry_lower))
        entry_upper = Decimal(str(plan.entry_upper))
        stop_loss = Decimal(str(plan.stop_loss))
        stop_distance = abs(entry_upper - stop_loss) if plan.direction == "LONG" else abs(entry_lower - stop_loss)

        return RiskDecision(
            id=decision_id,
            candidate_id=candidate.id,
            plan_id=plan.id,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            profile_id=candidate.profile_id,
            symbol=candidate.symbol,
            direction=plan.direction,
            decision="BLOCKED",
            requested_risk_pct=policy.max_risk_per_trade_pct,
            approved_risk_pct=Decimal("0.0000"),
            requested_risk_amount=(
                policy.max_risk_per_trade_pct / Decimal("100") * account.equity
            ).quantize(Decimal("0.01")),
            approved_risk_amount=Decimal("0.00"),
            position_size=Decimal("0.0000"),
            entry_lower=entry_lower,
            entry_upper=entry_upper,
            stop_loss=stop_loss,
            stop_distance=stop_distance,
            portfolio_exposure_before=account.open_risk_pct + account.reserved_risk_pct,
            portfolio_exposure_after=account.open_risk_pct + account.reserved_risk_pct,
            account_snapshot_id=account.id,
            symbol_specification_id=spec.id,
            policy_version=policy.version,
            reasons_th=tuple(reasons),
            warnings_th=(),
            blocked_reasons_th=tuple(blocked_reasons),
            as_of=now,
            expires_at=now + dt.timedelta(seconds=policy.reservation_ttl_seconds),
            market_provenance=market_prov,
            news_provenance=news_prov,
            execution_blocked="NO_EXECUTION_ANALYSIS_ONLY",
        )


risk_engine = RiskEngine()
