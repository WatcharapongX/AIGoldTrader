"""Authoritative AI analysis input assembler.

Gathers authentic state from:
- Phase 2: Market quote & data services
- Phase 3: Market structure & SMC context
- Phase 4: Strategy evaluations & candidate plans
- Phase 5: Risk decisions, risk reservations & Kill Switch
Enforces user/account authorization and point-in-time consistency.
"""

import datetime as dt
import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.models import Role, User
from app.models.account import Account
from app.models.risk import (
    AccountSnapshotRecord,
    RiskDecisionRecord,
    RiskReservationRecord,
)
from app.models.strategy import StrategyEvaluationRecord, TradeCandidateRecord
from app.services.ai.domain import (
    VERSION,
    AIAnalysisInput,
    AIKillSwitchContext,
    AIMarketQuoteContext,
    AIMarketStructureContext,
    AINewsContext,
    AINewsEventContext,
    AIProvenance,
    AIRiskDecisionContext,
    AIStrategyContext,
    AITradePlanContext,
    compute_semantic_input_fingerprint,
)
from app.services.risk.kill_switch import kill_switch_manager

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
        settings = get_settings()
        if settings.trading_mode == "PAPER" or as_of is None:
            now = dt.datetime.now(dt.UTC)
        else:
            now = _to_utc_datetime(as_of) or dt.datetime.now(dt.UTC)

        # -------------------------------------------------------------
        # 1. ACCOUNT AUTHORIZATION & LOOKUP
        # -------------------------------------------------------------
        acc_row = None
        try:
            parsed_uuid = uuid.UUID(account_id)
            acc_row = await session.scalar(select(Account).where(Account.id == parsed_uuid))
        except (ValueError, TypeError):
            acc_row = await session.scalar(select(Account).where(Account.name == account_id))

        if acc_row is None:
            raise NotFoundError(f"Account '{account_id}' not found")

        if current_user.role != Role.ADMIN and str(acc_row.user_id) != str(current_user.id):
            raise ForbiddenError("User is not authorized to access this account")

        canonical_account_id = str(acc_row.id)

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

        cand_payload = dict(cand_record.payload)
        symbol = str(cand_payload.get("symbol") or "XAUUSD")

        # Retrieve evaluation context
        eval_record = await session.get(StrategyEvaluationRecord, cand_record.evaluation_id)
        eval_payload = dict(eval_record.payload) if eval_record is not None else {}
        eval_context = eval_payload.get("context") or {}

        # -------------------------------------------------------------
        # 3. MARKET STRUCTURE CONTEXT
        # -------------------------------------------------------------
        frames = eval_context.get("frames") or []
        primary_frame = frames[0] if frames else {}
        analysis_json_str = primary_frame.get("analysis_json")
        analysis_data: dict[str, Any] = {}
        if analysis_json_str:
            try:
                analysis_data = (
                    json.loads(analysis_json_str) if isinstance(analysis_json_str, str) else analysis_json_str
                )
            except Exception as exc:
                logger.debug("Failed to parse analysis_json: %s", exc)

        regime = analysis_data.get("regime") or eval_context.get("regime") or "UNKNOWN"
        raw_sessions = analysis_data.get("current_sessions") or eval_context.get("current_sessions")
        if raw_sessions is None:
            cs = eval_context.get("current_session")
            raw_sessions = [cs] if cs else []
        elif isinstance(raw_sessions, str):
            raw_sessions = [raw_sessions]

        struct_as_of = (
            _to_utc_datetime(analysis_data.get("as_of"))
            or _to_utc_datetime(eval_context.get("as_of"))
            or _to_utc_datetime(cand_record.as_of)
            or now
        )

        structure_context = AIMarketStructureContext(
            symbol=symbol,
            timeframe=str(primary_frame.get("timeframe") or "M15"),
            as_of=struct_as_of,
            internal_state=str(analysis_data.get("internal_state") or "UNKNOWN"),
            external_state=str(analysis_data.get("external_state") or "UNKNOWN"),
            regime=str(regime),
            current_sessions=tuple(str(s) for s in raw_sessions),
            swings=tuple(analysis_data.get("swings") or ()),
            events=tuple(analysis_data.get("events") or ()),
            liquidity=tuple(analysis_data.get("liquidity") or ()),
            zones=tuple(analysis_data.get("zones") or ()),
            dealing_range=analysis_data.get("dealing_range"),
        )

        # -------------------------------------------------------------
        # 4. NEWS CONTEXT
        # -------------------------------------------------------------
        news_json_str = eval_context.get("news_json")
        news_data: dict[str, Any] = {}
        if news_json_str:
            try:
                news_data = json.loads(news_json_str) if isinstance(news_json_str, str) else news_json_str
            except Exception as exc:
                logger.debug("Failed to parse news_json: %s", exc)

        cand_news_prov = cand_payload.get("news_provenance") or {}
        raw_events = news_data.get("events") or cand_news_prov.get("event_vintages") or ()
        news_events: list[AINewsEventContext] = []
        for ev in raw_events:
            ev_dict = ev if isinstance(ev, dict) else (ev.model_dump() if hasattr(ev, "model_dump") else {})
            sched_at = _to_utc_datetime(ev_dict.get("scheduled_at")) or now
            avail_at = _to_utc_datetime(ev_dict.get("available_at")) or sched_at
            news_events.append(
                AINewsEventContext(
                    id=str(ev_dict.get("id") or uuid.uuid4().hex[:16]),
                    title=str(ev_dict.get("title") or ev_dict.get("name") or ""),
                    currency=str(ev_dict.get("currency") or "USD"),
                    impact=str(ev_dict.get("impact") or "MEDIUM"),
                    scheduled_at=sched_at,
                    available_at=avail_at,
                    actual=str(ev_dict.get("actual")) if ev_dict.get("actual") is not None else None,
                    forecast=str(ev_dict.get("forecast")) if ev_dict.get("forecast") is not None else None,
                    previous=str(ev_dict.get("previous")) if ev_dict.get("previous") is not None else None,
                    revision_version=ev_dict.get("revision_version"),
                )
            )

        news_context = AINewsContext(
            news_state=str(news_data.get("news_state") or "CALM"),
            in_blackout=bool(news_data.get("in_blackout", False)),
            in_pre_news_window=bool(news_data.get("in_pre_news_window", False)),
            in_post_news_window=bool(news_data.get("in_post_news_window", False)),
            as_of=_to_utc_datetime(news_data.get("as_of")) or now,
            events=tuple(news_events),
            event_ids=tuple(e.id for e in news_events),
            description_th=str(news_data.get("description_th") or ""),
            source=str(cand_news_prov.get("source") or news_data.get("source") or "forex_factory"),
            revision_version=news_data.get("revision_version"),
        )

        # -------------------------------------------------------------
        # 5. MARKET QUOTE CONTEXT
        # -------------------------------------------------------------
        quote_obj = None
        if request is not None:
            try:
                from app.api.market import started

                market = await started(request)
                if market and market.quote:
                    quote_obj = market.quote
            except Exception as exc:
                logger.debug("Market service quote unavailable: %s", exc)

        if quote_obj is not None:
            q_ts = _to_utc_datetime(quote_obj.timestamp) or now
            is_stale = (now - q_ts).total_seconds() > 30 or getattr(quote_obj, "is_stale", False)
            quote_context = AIMarketQuoteContext(
                symbol=str(quote_obj.symbol),
                bid=Decimal(str(quote_obj.bid)),
                ask=Decimal(str(quote_obj.ask)),
                spread=Decimal(str(quote_obj.spread)),
                timestamp=q_ts,
                is_stale=is_stale,
                source=str(getattr(market, "provider", {}).get("source", "market_service")),
            )
        else:
            safety_ctx = eval_context.get("market_safety") or {}
            safety_ts = _to_utc_datetime(safety_ctx.get("quote_as_of")) or _to_utc_datetime(cand_record.as_of) or now
            is_stale = (now - safety_ts).total_seconds() > 30
            quote_context = AIMarketQuoteContext(
                symbol=symbol,
                bid=Decimal("0.0"),
                ask=Decimal("0.0"),
                spread=Decimal(str(safety_ctx.get("current_spread") or "0.0")),
                timestamp=safety_ts,
                is_stale=is_stale,
                source="context_snapshot",
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
                as_of=now,
                expires_at=now,
                reservation_id=None,
                reservation_status="NONE",
                blocked_reasons_th=("ยังไม่ได้ผ่านการประเมินความเสี่ยงจาก Risk Engine",),
            )
        else:
            snap = await session.get(AccountSnapshotRecord, decision_row.account_snapshot_id)
            decision_account_id = snap.account_id if snap is not None else None

            account_matched = decision_account_id is not None and (
                decision_account_id == canonical_account_id or decision_account_id == acc_row.name
            )

            dec_as_of = _to_utc_datetime(decision_row.as_of) or now
            dec_expires_at = _to_utc_datetime(decision_row.expires_at) or now
            is_expired = dec_expires_at <= now

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
                    res_stmt = (
                        select(RiskReservationRecord)
                        .where(
                            RiskReservationRecord.decision_id == decision_row.id,
                            RiskReservationRecord.account_id == decision_account_id,
                            RiskReservationRecord.candidate_id == candidate_id,
                            RiskReservationRecord.status == "ACTIVE",
                            RiskReservationRecord.reserved_until > now,
                        )
                        .limit(1)
                    )
                    res_row = (await session.scalars(res_stmt)).first()
                    if res_row is not None:
                        res_status = "ACTIVE"
                        res_id = res_row.id
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
        detected_at_dt = _to_utc_datetime(cand_payload.get("detected_at")) or _to_utc_datetime(cand_record.as_of) or now
        confirmed_at_dt = _to_utc_datetime(cand_payload.get("confirmed_at"))

        strategy_context = AIStrategyContext(
            candidate_id=candidate_id,
            strategy_id=str(cand_payload.get("strategy_id") or cand_record.strategy_id),
            strategy_version=str(cand_payload.get("strategy_version") or "1.0.0"),
            profile_id=resolved_profile_id,
            symbol=symbol,
            direction=str(cand_payload.get("direction") or "LONG"),
            score=int(cand_payload.get("score") or 0),
            detected_at=detected_at_dt,
            confirmed_at=confirmed_at_dt,
            status=str(cand_payload.get("status") or "PENDING"),
            evidence=tuple(cand_payload.get("evidence") or ()),
        )

        trade_plan_dict = cand_payload.get("plan") or {}
        plan_id = str(trade_plan_dict.get("id") or trade_plan_dict.get("plan_id") or f"plan_{candidate_id}")

        tp1 = None
        tp2 = None
        rr = None
        if "targets" in trade_plan_dict and isinstance(trade_plan_dict["targets"], list):
            targets = trade_plan_dict["targets"]
            if len(targets) >= 1 and isinstance(targets[0], dict):
                tp1 = Decimal(str(targets[0].get("price", "0.0")))
                rr = Decimal(str(targets[0].get("rr", "1.5")))
            if len(targets) >= 2 and isinstance(targets[1], dict):
                tp2 = Decimal(str(targets[1].get("price", "0.0")))
        else:
            if trade_plan_dict.get("take_profit_1") is not None:
                tp1 = Decimal(str(trade_plan_dict["take_profit_1"]))
            if trade_plan_dict.get("take_profit_2") is not None:
                tp2 = Decimal(str(trade_plan_dict["take_profit_2"]))
            if trade_plan_dict.get("risk_reward_ratio") is not None:
                rr = Decimal(str(trade_plan_dict["risk_reward_ratio"]))

        trade_plan_context = AITradePlanContext(
            plan_id=plan_id,
            entry_lower=Decimal(str(trade_plan_dict.get("entry_lower", "0.0"))),
            entry_upper=Decimal(str(trade_plan_dict.get("entry_upper", "0.0"))),
            stop_loss=Decimal(str(trade_plan_dict.get("stop_loss", "0.0"))),
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_reward_ratio=rr,
            invalidation_th=str(trade_plan_dict.get("invalidation_th", "")),
            expires_at=_to_utc_datetime(trade_plan_dict.get("expires_at")),
        )

        # -------------------------------------------------------------
        # 9. PROVENANCE TRACKING
        # -------------------------------------------------------------
        provenance = AIProvenance(
            market_source=str(eval_record.source if eval_record is not None else "simulated"),
            market_context_id=str(eval_context.get("market_context_id", "")),
            structure_context_id=str(eval_context.get("id", "")),
            news_provider=str(news_context.source or "forex_factory"),
            news_revision=str(news_context.revision_version or ""),
            strategy_candidate_id=candidate_id,
            strategy_evaluation_id=str(cand_record.evaluation_id),
            trade_plan_id=trade_plan_context.plan_id,
            risk_decision_id=str(risk_context.decision_id),
            risk_reservation_id=str(risk_context.reservation_id or ""),
            kill_switch_record_id=str(kill_switch_context.record_id),
            kill_switch_as_of=now,
        )

        # -------------------------------------------------------------
        # 10. SEMANTIC FINGERPRINT (EXCLUDES CLOCK JITTER)
        # -------------------------------------------------------------
        semantic_fp = compute_semantic_input_fingerprint(
            symbol=symbol,
            account_id=canonical_account_id,
            profile_id=resolved_profile_id,
            as_of=now,
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
            analysis_requested_at=now,
            as_of=now,
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
            input_versions={"ai_version": VERSION},
            input_fingerprint=semantic_fp,
        )
