"""Phase 5 Risk Engine: evaluates TradePlan against RiskPolicy, Account, Portfolio, and News.

Fail closed: missing/stale metadata or active Kill Switch always produces BLOCKED.
Never changes TradePlan geometry, Setup Score, or direction.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_data.domain import Quote
from app.services.news.domain import NewsStrategyContext
from app.services.risk.domain import (
    AccountSnapshot,
    Decision,
    Direction,
    MarketProvenance,
    NewsEventAudit,
    NewsRiskProvenance,
    RiskDecision,
    RiskPolicy,
    SymbolSpecification,
)
from app.services.risk.fingerprint import compute_risk_dependency_fingerprint
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.portfolio import portfolio_manager
from app.services.risk.repository import find_existing_decision
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
        reasons_th: list[str] = []
        warnings_th: list[str] = []
        blocked_reasons_th: list[str] = []

        direction: Direction = plan.direction
        entry_lower = Decimal(str(plan.entry_lower))
        entry_upper = Decimal(str(plan.entry_upper))
        stop_loss = Decimal(str(plan.stop_loss))

        # 0. Transaction-level advisory lock on account to prevent concurrency races across workers (SOL-P5-P1-004)
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy import text

            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"risk_account_{account.account_id}"},
            )

        # 1. Market quote provenance & staleness evaluation
        market_prov = None
        quote_is_stale = False
        quote_stale_reason = ""
        if quote is None:
            quote_is_stale = True
            quote_stale_reason = "ไม่พบข้อมูลราคาตลาดล่าสุด (Market Quote Unavailable)"
        else:
            quote_age = (now - quote.timestamp).total_seconds()
            quote_is_stale = quote_age > policy.quote_freshness_seconds
            if quote_is_stale:
                quote_stale_reason = f"ราคาตลาดล้าสมัย ({quote_age:.1f}s > {policy.quote_freshness_seconds}s)"
            elif quote.spread > policy.max_spread_absolute:
                quote_is_stale = True
                quote_stale_reason = f"ค่าสเปรด (${quote.spread:.2f}) สูงกว่าเพดาน (${policy.max_spread_absolute:.2f})"

            market_prov = MarketProvenance(
                source=quote.source,
                mode=quote.mode,
                quote_timestamp=quote.timestamp,
                quote_bid=quote.bid,
                quote_ask=quote.ask,
                quote_spread=quote.spread,
                is_stale=quote_is_stale,
            )

        # 2. Evaluate automatic safety triggers (daily loss, drawdown, data health)
        provider_name = "mt5" if (quote and quote.source.startswith("mt5")) else "market_data"
        source_name = quote.source if quote else "default"
        await kill_switch_manager.evaluate_automatic_triggers(
            session=session,
            account=account,
            policy=policy,
            quote_stale=quote_is_stale,
            quote_stale_reason=quote_stale_reason,
            provider=provider_name,
            source=source_name,
        )

        # 3. Kill Switch check (dominates all evaluations, fail-closed on UNKNOWN)
        ks_check = await kill_switch_manager.check(session)
        ks_state = ks_check.state or await kill_switch_manager.get_state(session)
        if ks_check.is_active:
            blocked_reasons_th.append(ks_check.blocked_reason_th or "ไม่อนุมัติเนื่องจาก Kill Switch ทำงาน")

        # 4. News Risk evaluation (Fail closed when enabled and unavailable/stale - SOL-P5-P1-009)
        news_prov = None
        news_reduced = False
        target_risk_pct = requested_risk_pct or policy.max_risk_per_trade_pct

        if policy.news_risk_enabled:
            if news_context is None or getattr(news_context, "calendar_state", "AVAILABLE") != "AVAILABLE":
                desc = "ไม่สามารถประเมินความเสี่ยงข่าวได้ (News Provider Unavailable / Stale)"
                blocked_reasons_th.append(desc)
                news_prov = NewsRiskProvenance(
                    news_state="UNAVAILABLE",
                    in_blackout=False,
                    in_pre_news_window=False,
                    in_post_news_window=False,
                    event_ids=(),
                    description_th=desc,
                )
            elif news_context.events:
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
                    blocked_reasons_th.append(
                        "ไม่อนุมัติแผนเทรดเนื่องจากอยู่ในช่วงเวลาก่อนประกาศข่าว High-Impact (Blackout Window)"
                    )
                elif in_pre:
                    reduction_pct = (policy.news_reduction_factor * Decimal("100")).quantize(Decimal("1"))
                    desc = f"ใกล้เวลาประกาศข่าวสำคัญ ปรับลดความเสี่ยงเหลือ {reduction_pct:.0f}%"
                    warnings_th.append(desc)
                    target_risk_pct = target_risk_pct * policy.news_reduction_factor
                    news_reduced = True
                elif in_post:
                    desc = "ช่วงหลังข่าวประกาศ อยู่ระหว่างเฝ้าระวังสเปรดและความผันผวน"
                    if quote and quote.spread > policy.max_spread_absolute * Decimal("0.8"):
                        blocked_reasons_th.append("ไม่อนุมัติเนื่องจากสเปรดหลังประกาศข่าวยังไม่เสถียร")
                    else:
                        warnings_th.append(desc)

                events_audit = [
                    NewsEventAudit(
                        event_id=ev.id,
                        event_name=ev.event_name,
                        currency=ev.currency,
                        impact=ev.impact,
                        scheduled_at=ev.scheduled_at,
                        available_at=getattr(ev, "available_at", None),
                        window_state=(
                            "BLACKOUT"
                            if ev.id in relevant_event_ids and in_blackout
                            else (
                                "PRE"
                                if ev.id in relevant_event_ids and in_pre
                                else ("POST" if ev.id in relevant_event_ids and in_post else "CALM")
                            )
                        ),
                        provider=getattr(ev, "source", "")
                        or getattr(ev, "provider", "")
                        or getattr(news_context, "source", "")
                        or getattr(news_context, "provider", ""),
                        source=getattr(ev, "source", "")
                        or getattr(ev, "provider", "")
                        or getattr(news_context, "source", "")
                        or getattr(news_context, "provider", ""),
                        revision_id=str(getattr(ev, "revision_version", ""))
                        if getattr(ev, "revision_version", None) is not None
                        else (
                            getattr(ev, "revision_id", "")
                            or str(getattr(news_context, "revision_version", ""))
                            if getattr(news_context, "revision_version", None) is not None
                            else getattr(news_context, "revision_id", "")
                        ),
                        revision_version=getattr(ev, "revision_version", None)
                        or getattr(news_context, "revision_version", None),
                    )
                    for ev in news_context.events
                ]
                news_prov = NewsRiskProvenance(
                    news_state="EVENT_RISK_ACTIVE" if (in_blackout or in_pre or in_post) else "CALM",
                    in_blackout=in_blackout,
                    in_pre_news_window=in_pre,
                    in_post_news_window=in_post,
                    event_ids=tuple(relevant_event_ids),
                    description_th=desc,
                    events=tuple(events_audit),
                    provider=getattr(news_context, "source", "")
                    or getattr(news_context, "provider", "")
                    or (events_audit[0].provider if events_audit else ""),
                    source=getattr(news_context, "source", "")
                    or getattr(news_context, "provider", "")
                    or (events_audit[0].source if events_audit else ""),
                    revision_id=str(getattr(news_context, "revision_version", ""))
                    if getattr(news_context, "revision_version", None) is not None
                    else (
                        getattr(news_context, "revision_id", "")
                        or (events_audit[0].revision_id if events_audit else "")
                    ),
                    revision_version=getattr(news_context, "revision_version", None)
                    or (events_audit[0].revision_version if events_audit else None),
                )
            else:
                news_prov = NewsRiskProvenance(
                    news_state="CALM",
                    in_blackout=False,
                    in_pre_news_window=False,
                    in_post_news_window=False,
                    event_ids=(),
                    description_th="สภาวะข่าวปกติ ไม่มีเหตุการณ์สำคัญ",
                    provider=getattr(news_context, "source", "") or getattr(news_context, "provider", ""),
                    source=getattr(news_context, "source", "") or getattr(news_context, "provider", ""),
                    revision_id=str(getattr(news_context, "revision_version", ""))
                    if getattr(news_context, "revision_version", None) is not None
                    else getattr(news_context, "revision_id", ""),
                    revision_version=getattr(news_context, "revision_version", None),
                )

        # 5. Evaluate temporal safety flags
        account_is_stale = (now - account.as_of).total_seconds() > policy.account_freshness_seconds
        plan_is_expired = plan.expires_at is not None and plan.expires_at <= now
        from app.services.risk.portfolio import is_cooldown_active

        cooldown_active, _ = is_cooldown_active(account, policy, now)

        # 6. Calculate current portfolio exposure for fingerprint (sole source: DB reservations)
        # Exclude candidate's own active reservation so baseline exposure and fingerprint
        # are deterministic across retries
        active_reservations = await portfolio_manager.get_active_reservations(session, account.account_id, now)
        current_reserved = sum(
            (
                Decimal(str(r.risk_pct))
                for r in active_reservations
                if getattr(r, "candidate_id", None) != candidate.id
            ),
            Decimal("0"),
        )
        current_exposure = account.open_risk_pct + current_reserved

        # 7. Compute canonical deterministic dependency fingerprint & ID
        fingerprint = compute_risk_dependency_fingerprint(
            candidate=candidate,
            plan=plan,
            profile_id=candidate.profile_id,
            account=account,
            policy=policy,
            spec=spec,
            kill_switch=ks_state,
            quote=quote,
            news_prov=news_prov,
            portfolio_exposure_before=current_exposure,
            requested_risk_pct=target_risk_pct,
            account_is_stale=account_is_stale,
            quote_is_stale=quote_is_stale,
            plan_is_expired=plan_is_expired,
            cooldown_active=cooldown_active,
        )
        decision_id = f"dec_{fingerprint[:24]}"

        # 8. Check idempotency cache with full dependency fingerprint inside lock (SOL-P5-P1-001, 004)
        existing_decision = await find_existing_decision(
            session=session,
            candidate_id=candidate.id,
            profile_id=candidate.profile_id,
            dependency_fingerprint=fingerprint,
            now=now,
        )
        if existing_decision is not None:
            return existing_decision

        # 8. Check gate conditions
        # Account Health & Freshness
        if (now - account.as_of).total_seconds() > policy.account_freshness_seconds:
            age_sec = (now - account.as_of).total_seconds()
            blocked_reasons_th.append(
                f"ข้อมูลบัญชีล้าสมัย (Snapshot อายุ {age_sec:.0f} วินาที เกินเพดาน {policy.account_freshness_seconds} วินาที)"
            )

        if account.equity <= Decimal("0"):
            blocked_reasons_th.append("มูลค่าสุทธิของบัญชี (Equity) ต้องมากกว่า 0")

        # Daily loss limit check
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

        # Cooldown check lifecycle (SOL-P5-P1-010, SOL-P5-P2-038)
        in_cooldown, _ = is_cooldown_active(account, policy, now)
        if in_cooldown:
            blocked_reasons_th.append(
                f"บัญชีอยู่ในช่วงพักการเทรด (Cooldown) เนื่องจากขาดทุนต่อเนื่อง {account.consecutive_losses} ครั้ง"
            )

        # Symbol Spec & Quote Gates
        if spec.tick_size <= Decimal("0") or spec.tick_value <= Decimal("0") or spec.contract_size <= Decimal("0"):
            blocked_reasons_th.append("ข้อมูลสเปกสัญลักษณ์ (Symbol Specification) ไม่สมบูรณ์หรือไม่ถูกต้อง")

        spec_age = (now - spec.observed_at).total_seconds()
        if spec_age > policy.symbol_spec_freshness_seconds:
            blocked_reasons_th.append(
                f"ข้อมูลสเปกสัญลักษณ์ล้าสมัย (SymbolSpec อายุ {spec_age:.0f}s > {policy.symbol_spec_freshness_seconds}s)"
            )

        # Open Position Risk check (SOL-P5-P2-012)
        if account.open_risk_pct > Decimal("0"):
            blocked_reasons_th.append(
                "ไม่อนุมัติเนื่องจากมีสถานะเปิดความเสี่ยงคงค้างที่ไม่สามารถแจกแจงสัญลักษณ์/ทิศทางได้ (Open Risk Breakdown Unavailable)"
            )

        if quote_is_stale:
            blocked_reasons_th.append(quote_stale_reason)

        # TradePlan Validation
        if plan.status != "SUGGESTION_ONLY":
            blocked_reasons_th.append("สถานะแผนเทรดไม่ถูกต้อง ต้องเป็น SUGGESTION_ONLY")

        if plan.expires_at <= now:
            blocked_reasons_th.append("แผนเทรดหมดอายุความถูกต้องแล้ว (Plan Expired)")

        # If any gate failed, fail closed (ZERO reservation created)
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
                news_prov=news_prov,
                dependency_fingerprint=fingerprint,
            )

        # 9. Portfolio budget capacity check (pure check, no reservation yet - SOL-P5-P1-008)
        # Excludes ONLY the exact reservation being canonically replaced (SOL-P5-P1-031)
        existing_candidate_res = [
            r for r in active_reservations if getattr(r, "candidate_id", None) == candidate.id
        ]
        exclude_res_id = existing_candidate_res[0].id if len(existing_candidate_res) == 1 else None

        budget_check = await portfolio_manager.check_budget_capacity(
            session=session,
            account=account,
            policy=policy,
            symbol=candidate.symbol,
            direction=direction,
            requested_risk_pct=target_risk_pct,
            now=now,
            exclude_reservation_id=exclude_res_id,
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
                dependency_fingerprint=fingerprint,
            )

        # 10. Position sizing with approved risk amount
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
                dependency_fingerprint=fingerprint,
            )

        # 11. Final Sizing Succeeded: Atomically create reservation in DB
        await portfolio_manager.create_reservation(
            session=session,
            decision_id=decision_id,
            account_id=account.account_id,
            profile_id=candidate.profile_id,
            symbol=candidate.symbol,
            direction=direction,
            risk_pct=approved_pct,
            risk_amount=approved_amount,
            position_size=final_sizing.position_size,
            policy=policy,
            now=now,
            candidate_id=candidate.id,
        )

        # 12. Construct APPROVED or REDUCED Decision
        decision_type: Decision = "REDUCED" if (budget_check.is_reduced or news_reduced) else "APPROVED"

        if decision_type == "APPROVED":
            reasons_th.append(f"อนุมัติแผนเทรดตามปกติ ขนาดความเสี่ยง {approved_pct:.2f}% (${approved_amount:.2f})")
        else:
            reasons_th.append(f"อนุมัติแบบลดความเสี่ยงเหลือ {approved_pct:.2f}% (${approved_amount:.2f})")
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
            dependency_fingerprint=fingerprint,
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
        dependency_fingerprint: str = "",
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
            requested_risk_amount=(policy.max_risk_per_trade_pct / Decimal("100") * account.equity).quantize(
                Decimal("0.01")
            ),
            approved_risk_amount=Decimal("0.00"),
            position_size=Decimal("0.0000"),
            entry_lower=entry_lower,
            entry_upper=entry_upper,
            stop_loss=stop_loss,
            stop_distance=stop_distance,
            portfolio_exposure_before=account.open_risk_pct,
            portfolio_exposure_after=account.open_risk_pct,
            account_snapshot_id=account.id,
            symbol_specification_id=spec.id,
            policy_version=policy.version,
            reasons_th=tuple(reasons),
            warnings_th=(),
            blocked_reasons_th=tuple(blocked_reasons),
            as_of=now,
            expires_at=now + dt.timedelta(seconds=policy.reservation_ttl_seconds),
            dependency_fingerprint=dependency_fingerprint,
            market_provenance=market_prov,
            news_provenance=news_prov,
            execution_blocked="NO_EXECUTION_ANALYSIS_ONLY",
        )


risk_engine = RiskEngine()
