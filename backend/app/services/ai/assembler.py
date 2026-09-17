"""Authoritative AI analysis input assembler.

Gathers authentic state from:
- Phase 2: Market quote & data services
- Phase 3: Market structure & SMC context
- Phase 4: Strategy evaluations & candidate plans
- Phase 5: Risk decisions, risk reservations & Kill Switch
Enforces user/account authorization and point-in-time consistency.
"""

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models import Role, User
from app.models.risk import (
    RiskDecisionRecord,
    RiskReservationRecord,
)
from app.models.strategy import StrategyEvaluationRecord, TradeCandidateRecord
from app.services.ai.domain import (
    VERSION,
    AIAnalysisInput,
    AIDealingRangeEvidence,
    AIKillSwitchContext,
    AILiquidityEvidence,
    AIMarketQuoteContext,
    AIMarketStructureContext,
    AINewsContext,
    AINewsEventContext,
    AIProvenance,
    AIRiskDecisionContext,
    AIStrategyContext,
    AIStrategyEvidence,
    AIStructureEvent,
    AISwingEvidence,
    AITradePlanContext,
    AIZoneEvidence,
    compute_semantic_input_fingerprint,
)
from app.services.analysis.domain import AnalysisSnapshot
from app.services.news.domain import NewsStrategyContext
from app.services.risk.account_resolver import resolve_canonical_account
from app.services.risk.kill_switch import kill_switch_manager
from app.services.strategy.domain import SetupCandidate, compute_trade_plan_fingerprint
from app.services.strategy.lifecycle import resolve_candidate_current_lifecycle

logger = logging.getLogger(__name__)


def _to_utc_datetime(val: Any) -> dt.datetime | None:
    """Safely convert any datetime/iso string to UTC aware datetime."""
    if val is None:
        return None
    if isinstance(val, dt.datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=dt.UTC)
    if isinstance(val, (int, float)):
        return dt.datetime.fromtimestamp(val, tz=dt.UTC)
    if isinstance(val, str):
        try:
            cleaned = val.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(cleaned)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.UTC)
        except Exception:
            return None
    return None


def _provider_source(provider: Any, quote: Any) -> str | None:
    """Extract source from the real quote/provider contracts without assuming a dict."""
    for value in (quote, provider):
        if value is None:
            continue
        if isinstance(value, dict):
            candidates = (value.get("source"), value.get("provider_id"), value.get("name"))
        else:
            candidates = (
                getattr(value, "source", None),
                getattr(value, "provider_id", None),
                getattr(value, "name", None),
            )
        source = next((str(item).strip() for item in candidates if item is not None and str(item).strip()), None)
        if source:
            return source
    return None


def _required_datetime(value: Any, field: str) -> dt.datetime:
    parsed = _to_utc_datetime(value)
    if parsed is None:
        raise ValueError(f"{field} must be a valid timezone-aware timestamp")
    return parsed


class AIAnalysisInputAssembler:
    """Assembles authoritative AIAnalysisInput from authentic Phase 2–5 domain records."""

    @classmethod
    async def assemble(
        cls,
        session: AsyncSession,
        *,
        candidate_id: str,
        account_id: str,
        profile_id: str | None = None,
        current_user: User,
        request: Request | None = None,
        as_of: dt.datetime | None = None,
    ) -> AIAnalysisInput:
        """Construct authoritative, safety-gated AIAnalysisInput.

        Raises:
            ForbiddenError: User is not authorized for the requested account.
            NotFoundError: Account or candidate does not exist.
            ValidationError: Input fails domain constraints (e.g. profile mismatch).
        """
        if as_of is not None:
            raise ValidationError("AI analysis is current-only; historical as_of is not supported in Phase 6.1")
        requested_at = dt.datetime.now(dt.UTC)
        analysis_as_of = requested_at

        # -------------------------------------------------------------
        # 1. ACCOUNT AUTHORIZATION & LOOKUP
        # -------------------------------------------------------------
        acc_row, canonical_account_id = await resolve_canonical_account(
            session=session,
            account_ref=account_id,
            user=current_user,
            is_admin=(current_user.role == Role.ADMIN),
        )

        # -------------------------------------------------------------
        # 2. TRADE CANDIDATE & STRATEGY EVALUATION LOOKUP
        # -------------------------------------------------------------
        cand_record = await session.get(TradeCandidateRecord, candidate_id)
        if cand_record is None:
            raise NotFoundError(f"TradeCandidate '{candidate_id}' not found")

        resolved_profile_id = cand_record.profile_id
        if profile_id is not None and profile_id != resolved_profile_id:
            raise ValidationError(
                f"Candidate profile mismatch: candidate belongs to '{resolved_profile_id}', requested '{profile_id}'"
            )

        # Retrieve evaluation context
        eval_record = await session.get(StrategyEvaluationRecord, cand_record.evaluation_id)
        eval_payload = dict(eval_record.payload) if eval_record is not None else {}
        eval_context = eval_payload.get("context") or {}
        cand_payload = dict(cand_record.payload)
        symbol_value = cand_payload.get("symbol") or (eval_record.symbol if eval_record is not None else None)
        if not symbol_value:
            raise ValidationError("Candidate symbol authority is unavailable")
        symbol = str(symbol_value)

        # -------------------------------------------------------------
        # 3. MARKET STRUCTURE CONTEXT
        # -------------------------------------------------------------
        frames = eval_context.get("frames") or []
        primary_frame = frames[0] if frames and isinstance(frames[0], dict) else {}
        try:
            analysis_json = primary_frame.get("analysis_json")
            if not analysis_json:
                raise ValueError("Phase 3 analysis snapshot is absent")
            analysis = (
                AnalysisSnapshot.model_validate_json(analysis_json)
                if isinstance(analysis_json, str)
                else AnalysisSnapshot.model_validate(analysis_json)
            )
            structure_context = AIMarketStructureContext(
                availability="AVAILABLE",
                symbol=analysis.symbol,
                timeframe=analysis.timeframe.value,
                as_of=_required_datetime(analysis.as_of, "structure.as_of"),
                source=analysis.source,
                context_id=analysis.input_id,
                algorithm_version=analysis.algorithm_version,
                internal_state=analysis.internal_state,
                external_state=analysis.external_state,
                regime=analysis.regime,
                current_sessions=tuple(analysis.current_sessions),
                swings=tuple(AISwingEvidence.model_validate(item.model_dump()) for item in analysis.swings),
                events=tuple(AIStructureEvent.model_validate(item.model_dump()) for item in analysis.events),
                liquidity=tuple(AILiquidityEvidence.model_validate(item.model_dump()) for item in analysis.liquidity),
                zones=tuple(AIZoneEvidence.model_validate(item.model_dump()) for item in analysis.zones),
                dealing_range=(
                    AIDealingRangeEvidence.model_validate(analysis.dealing_range.model_dump())
                    if analysis.dealing_range is not None
                    else None
                ),
            )
            if structure_context.symbol != symbol:
                raise ValueError("Structure symbol does not match candidate")
        except Exception as exc:
            logger.info("Authoritative structure unavailable: %s", exc)
            structure_context = AIMarketStructureContext(
                availability="UNAVAILABLE",
                symbol=symbol,
                unavailable_reason=str(exc),
            )

        # -------------------------------------------------------------
        # 4. NEWS CONTEXT
        # -------------------------------------------------------------
        try:
            news_json = eval_context.get("news_json")
            if not news_json:
                raise ValueError("News context is absent")
            authoritative_news = (
                NewsStrategyContext.model_validate_json(news_json)
                if isinstance(news_json, str)
                else NewsStrategyContext.model_validate(news_json)
            )
            if authoritative_news.calendar_state == "CALENDAR_UNAVAILABLE":
                raise ValueError("News calendar is unavailable")
            news_events: list[AINewsEventContext] = []
            for event in authoritative_news.events:
                news_events.append(
                    AINewsEventContext(
                        id=event.id,
                        title=event.event_name,
                        currency=event.currency,
                        impact=event.impact,
                        scheduled_at=event.scheduled_at,
                        available_at=event.available_at,
                        updated_at=event.updated_at,
                        released_at=event.released_at,
                        actual=str(event.actual) if event.actual is not None else None,
                        forecast=str(event.forecast) if event.forecast is not None else None,
                        previous=str(event.previous) if event.previous is not None else None,
                        revision_version=event.revision_version,
                    )
                )
            revision = max((event.revision_version or 0 for event in news_events), default=0) or None
            news_context = AINewsContext(
                availability="AVAILABLE",
                news_state=authoritative_news.news_regime,
                in_blackout=authoritative_news.trade_policy_state == "RESTRICTED",
                in_pre_news_window=authoritative_news.view == "pre",
                in_post_news_window=authoritative_news.view == "post",
                as_of=authoritative_news.as_of,
                events=tuple(news_events),
                event_ids=tuple(event.id for event in news_events),
                source=authoritative_news.source,
                revision_version=revision,
                context_fingerprint=authoritative_news.fingerprint,
            )
        except Exception as exc:
            logger.info("Authoritative news unavailable: %s", exc)
            news_context = AINewsContext(
                availability="UNAVAILABLE",
                unavailable_reason=str(exc),
            )

        # -------------------------------------------------------------
        # 5. MARKET QUOTE CONTEXT
        # -------------------------------------------------------------
        quote_obj = None
        market = None
        if request is not None:
            try:
                from app.api.market import started

                market = await started(request)
                if market and market.quote:
                    quote_obj = market.quote
            except Exception as exc:
                logger.info("Market service quote unavailable: %s", exc)

        if quote_obj is not None:
            try:
                q_ts = _required_datetime(getattr(quote_obj, "timestamp", None), "quote.timestamp")
                bid = Decimal(str(quote_obj.bid))
                ask = Decimal(str(quote_obj.ask))
                raw_spread = getattr(quote_obj, "spread", None)
                spread = ask - bid if raw_spread is None else Decimal(str(raw_spread))
                quote_source = _provider_source(getattr(market, "provider", None), quote_obj)
                is_stale = (
                    (analysis_as_of - q_ts).total_seconds() > 30
                    or bool(getattr(quote_obj, "is_stale", False))
                    or str(getattr(quote_obj, "status", "")).upper() in {"STALE", "DISCONNECTED", "ERROR"}
                )
                quote_context = AIMarketQuoteContext(
                    availability="STALE" if is_stale else "AVAILABLE",
                    symbol=str(quote_obj.symbol),
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    timestamp=q_ts,
                    is_stale=is_stale,
                    source=quote_source or "",
                )
                if quote_context.symbol != symbol:
                    raise ValueError("Quote symbol does not match candidate")
            except Exception as exc:
                logger.info("Authoritative market quote invalid: %s", exc)
                quote_context = AIMarketQuoteContext(
                    availability="UNAVAILABLE",
                    symbol=symbol,
                    unavailable_reason=str(exc),
                )
        else:
            quote_context = AIMarketQuoteContext(
                availability="UNAVAILABLE",
                symbol=symbol,
                unavailable_reason="No live quote or complete persisted observed quote is available",
            )

        # -------------------------------------------------------------
        # 6. KILL SWITCH CONTEXT
        # -------------------------------------------------------------
        ks_current = await kill_switch_manager.get_state(session)
        if ks_current is None:
            kill_switch_context = AIKillSwitchContext(
                record_id="",
                state="UNKNOWN",
                trigger_type="NONE",
                reason_th="Kill Switch state unavailable",
                policy_version="",
            )
        else:
            ks_id = getattr(ks_current, "record_id", None) or getattr(ks_current, "id", "")
            kill_switch_context = AIKillSwitchContext(
                record_id=str(ks_id or ""),
                state=str(ks_current.state),
                trigger_type=str(ks_current.trigger_type or "NONE"),
                reason_th=str(ks_current.reason_th or ""),
                activated_at=_to_utc_datetime(ks_current.activated_at),
                cleared_at=_to_utc_datetime(ks_current.cleared_at),
                policy_version=str(getattr(ks_current, "policy_version", "risk-policy-1.0.0")),
            )

        # -------------------------------------------------------------
        # 7. RISK DECISION & RESERVATION CONTEXT
        # -------------------------------------------------------------
        stmt = (
            select(RiskDecisionRecord)
            .where(
                RiskDecisionRecord.candidate_id == candidate_id,
                RiskDecisionRecord.profile_id == resolved_profile_id,
                RiskDecisionRecord.account_id == acc_row.id,
            )
            .order_by(RiskDecisionRecord.as_of.desc())
            .limit(1)
        )
        decision_row = (await session.scalars(stmt)).first()

        if decision_row is None:
            risk_context = AIRiskDecisionContext(
                decision_id="",
                decision="RISK_NOT_EVALUATED",
                account_id=canonical_account_id,
                profile_id=resolved_profile_id,
                requested_risk_pct=Decimal("0.0"),
                approved_risk_pct=Decimal("0.0"),
                requested_risk_amount=Decimal("0.0"),
                approved_risk_amount=Decimal("0.0"),
                position_size=Decimal("0.0"),
                policy_version="",
                as_of=analysis_as_of,
                expires_at=analysis_as_of,
                reservation_id=None,
                reservation_status="NONE",
                blocked_reasons_th=("ยังไม่ได้ผ่านการประเมินความเสี่ยงจาก Risk Engine",),
            )
        else:
            account_matched = (str(decision_row.account_id) == canonical_account_id)

            dec_as_of = _required_datetime(decision_row.as_of, "risk.as_of")
            dec_expires_at = _required_datetime(decision_row.expires_at, "risk.expires_at")
            is_expired = dec_expires_at <= analysis_as_of

            if not account_matched:
                risk_context = AIRiskDecisionContext(
                    decision_id=str(decision_row.id),
                    decision="BLOCKED",
                    account_id=canonical_account_id,
                    profile_id=resolved_profile_id,
                    requested_risk_pct=decision_row.requested_risk_pct,
                    approved_risk_pct=Decimal("0.0"),
                    requested_risk_amount=decision_row.requested_risk_amount,
                    approved_risk_amount=Decimal("0.0"),
                    position_size=Decimal("0.0"),
                    policy_version=str(decision_row.policy_version),
                    as_of=dec_as_of,
                    expires_at=dec_expires_at,
                    reservation_id=None,
                    reservation_status="INACTIVE",
                    blocked_reasons_th=("Risk decision belongs to a different account",),
                )
            elif is_expired:
                risk_context = AIRiskDecisionContext(
                    decision_id=str(decision_row.id),
                    decision="EXPIRED",
                    account_id=canonical_account_id,
                    profile_id=resolved_profile_id,
                    requested_risk_pct=decision_row.requested_risk_pct,
                    approved_risk_pct=decision_row.approved_risk_pct,
                    requested_risk_amount=decision_row.requested_risk_amount,
                    approved_risk_amount=decision_row.approved_risk_amount,
                    position_size=decision_row.position_size,
                    policy_version=str(decision_row.policy_version),
                    as_of=dec_as_of,
                    expires_at=dec_expires_at,
                    reservation_id=None,
                    reservation_status="INACTIVE",
                    blocked_reasons_th=("Risk decision has expired",),
                )
            else:
                res_status = "NONE"
                res_id = None
                if decision_row.decision in ("APPROVED", "REDUCED"):
                    reservation_rows = list(
                        (
                            await session.scalars(
                                select(RiskReservationRecord).where(
                                    RiskReservationRecord.decision_id == decision_row.id,
                                )
                            )
                        ).all()
                    )
                    if len(reservation_rows) > 1:
                        res_status = "MISMATCHED"
                    elif len(reservation_rows) == 1:
                        res_row = reservation_rows[0]
                        res_id = str(res_row.id)
                        reserved_until = _required_datetime(
                            res_row.reserved_until,
                            "reservation.reserved_until",
                        )
                        exact_match = (
                            str(res_row.decision_id) == str(decision_row.id)
                            and str(res_row.account_id) == canonical_account_id
                            and str(res_row.candidate_id) == candidate_id
                            and str(res_row.profile_id) == resolved_profile_id
                            and str(res_row.symbol) == str(decision_row.symbol) == symbol
                            and str(res_row.direction) == str(decision_row.direction)
                            and Decimal(res_row.risk_pct) == Decimal(decision_row.approved_risk_pct)
                            and Decimal(res_row.risk_amount) == Decimal(decision_row.approved_risk_amount)
                            and Decimal(res_row.position_size) == Decimal(decision_row.position_size)
                        )
                        if not exact_match:
                            res_status = "MISMATCHED"
                        elif str(res_row.status).upper() != "ACTIVE":
                            res_status = "INACTIVE"
                        elif reserved_until <= analysis_as_of:
                            res_status = "EXPIRED"
                        else:
                            res_status = "ACTIVE"
                    else:
                        res_status = "INACTIVE"

                payload_reasons = tuple(decision_row.payload.get("blocked_reasons_th") or ())
                risk_context = AIRiskDecisionContext(
                    decision_id=str(decision_row.id),
                    decision=str(decision_row.decision),
                    account_id=canonical_account_id,
                    profile_id=resolved_profile_id,
                    requested_risk_pct=decision_row.requested_risk_pct,
                    approved_risk_pct=decision_row.approved_risk_pct,
                    requested_risk_amount=decision_row.requested_risk_amount,
                    approved_risk_amount=decision_row.approved_risk_amount,
                    position_size=decision_row.position_size,
                    policy_version=str(decision_row.policy_version),
                    as_of=dec_as_of,
                    expires_at=dec_expires_at,
                    reservation_id=res_id,
                    reservation_status=res_status,
                    blocked_reasons_th=payload_reasons,
                )

        # -------------------------------------------------------------
        # 8. STRATEGY CONTEXT & TRADE PLAN CONTEXT
        # -------------------------------------------------------------
        candidate_domain: SetupCandidate | None = None
        try:
            candidate_domain = SetupCandidate.model_validate(cand_payload)
            if (
                candidate_domain.id != candidate_id
                or candidate_domain.profile_id != resolved_profile_id
                or candidate_domain.strategy_id != str(cand_record.strategy_id)
                or candidate_domain.symbol != symbol
            ):
                raise ValueError("Candidate payload identity does not match its persisted record")

            # Check authoritative candidate lifecycle state (AUD-P1-001)
            lifecycle = await resolve_candidate_current_lifecycle(
                session=session,
                candidate_id=candidate_id,
                profile_id=resolved_profile_id,
            )
            if lifecycle.is_terminal:
                raise ValueError(f"Candidate lifecycle is terminal ({lifecycle.current_status})")

            strategy_context = AIStrategyContext(
                availability="AVAILABLE",
                candidate_id=candidate_domain.id,
                strategy_id=candidate_domain.strategy_id,
                strategy_version=candidate_domain.strategy_version,
                profile_id=candidate_domain.profile_id,
                symbol=candidate_domain.symbol,
                direction=candidate_domain.direction,
                score=candidate_domain.score,
                detected_at=candidate_domain.detected_at,
                confirmed_at=candidate_domain.confirmed_at,
                status=lifecycle.current_status,
                evidence=tuple(
                    AIStrategyEvidence.model_validate(item.model_dump()) for item in candidate_domain.evidence
                ),
            )
        except Exception as exc:
            logger.info("Authoritative strategy candidate unavailable: %s", exc)
            strategy_context = AIStrategyContext(
                availability="UNAVAILABLE",
                candidate_id=candidate_id,
                strategy_id=str(cand_record.strategy_id),
                profile_id=resolved_profile_id,
                symbol=symbol,
                unavailable_reason=str(exc),
            )

        current_plan_fingerprint = ""
        try:
            if candidate_domain is None or candidate_domain.plan is None:
                raise ValueError("TradePlan is absent")
            plan = candidate_domain.plan
            current_plan_fingerprint = compute_trade_plan_fingerprint(candidate_domain, plan)
            trade_plan_context = AITradePlanContext(
                availability="AVAILABLE",
                plan_id=plan.id,
                entry_lower=plan.entry_lower,
                entry_upper=plan.entry_upper,
                stop_loss=plan.stop_loss,
                take_profit_1=plan.targets[0].price,
                take_profit_2=plan.targets[1].price,
                risk_reward_ratio=plan.targets[0].rr,
                invalidation_th=plan.invalidation_th,
                as_of=plan.as_of,
                expires_at=plan.expires_at,
                evidence=tuple(AIStrategyEvidence.model_validate(item.model_dump()) for item in plan.evidence),
            )
        except Exception as exc:
            logger.info("Authoritative TradePlan unavailable: %s", exc)
            trade_plan_context = AITradePlanContext(
                availability="UNAVAILABLE",
                unavailable_reason=str(exc),
            )

        if (
            risk_context.decision in ("APPROVED", "REDUCED")
            and (
                not current_plan_fingerprint
                or decision_row is None
                or not str(decision_row.payload.get("trade_plan_fingerprint") or "")
                or str(decision_row.payload.get("trade_plan_fingerprint")) != current_plan_fingerprint
                or strategy_context.availability != "AVAILABLE"
                or trade_plan_context.availability != "AVAILABLE"
                or (decision_row is not None and str(decision_row.plan_id) != trade_plan_context.plan_id)
                or (decision_row is not None and str(decision_row.strategy_id) != strategy_context.strategy_id)
                or (decision_row is not None and str(decision_row.direction) != strategy_context.direction)
                or (decision_row is not None and decision_row.entry_lower != trade_plan_context.entry_lower)
                or (decision_row is not None and decision_row.entry_upper != trade_plan_context.entry_upper)
                or (decision_row is not None and decision_row.stop_loss != trade_plan_context.stop_loss)
            )
        ):
            risk_context = risk_context.model_copy(update={"reservation_status": "MISMATCHED"})

        # -------------------------------------------------------------
        # 9. PROVENANCE TRACKING
        # -------------------------------------------------------------
        provenance = AIProvenance(
            market_source=quote_context.source,
            market_context_id=str(eval_context.get("market_context_id", "")),
            structure_context_id=structure_context.context_id,
            news_provider=news_context.source,
            news_revision=str(news_context.revision_version or ""),
            strategy_candidate_id=candidate_id,
            strategy_evaluation_id=str(cand_record.evaluation_id),
            trade_plan_id=trade_plan_context.plan_id,
            risk_decision_id=str(risk_context.decision_id),
            risk_reservation_id=str(risk_context.reservation_id or ""),
            kill_switch_record_id=str(kill_switch_context.record_id),
            kill_switch_as_of=kill_switch_context.cleared_at or kill_switch_context.activated_at,
        )

        # -------------------------------------------------------------
        # 10. SEMANTIC FINGERPRINT (EXCLUDES CLOCK JITTER)
        # -------------------------------------------------------------
        semantic_fp = compute_semantic_input_fingerprint(
            symbol=symbol,
            account_id=canonical_account_id,
            profile_id=resolved_profile_id,
            as_of=analysis_as_of,
            quote_context=quote_context,
            structure_context=structure_context,
            news_context=news_context,
            strategy_context=strategy_context,
            trade_plan_context=trade_plan_context,
            risk_context=risk_context,
            kill_switch_context=kill_switch_context,
            provenance=provenance,
        )

        # -------------------------------------------------------------
        # 11. CONSTRUCT FROZEN AIAnalysisInput
        # -------------------------------------------------------------
        return AIAnalysisInput(
            analysis_id=f"ai_req_{uuid.uuid4().hex[:24]}",
            trace_id=f"tr_{uuid.uuid4().hex[:16]}",
            analysis_requested_at=requested_at,
            as_of=analysis_as_of,
            symbol=symbol,
            account_id=canonical_account_id,
            profile_id=resolved_profile_id,
            quote_context=quote_context,
            structure_context=structure_context,
            news_context=news_context,
            strategy_context=strategy_context,
            trade_plan_context=trade_plan_context,
            risk_context=risk_context,
            kill_switch_context=kill_switch_context,
            provenance=provenance,
            input_versions=(("ai_version", VERSION),),
            input_fingerprint=semantic_fp,
        )
